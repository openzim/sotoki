#!/usr/bin/env python

import hashlib
import io
import re
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from time import sleep
from typing import Any

import requests
from kiwixstorage import NotFoundError
from PIL import Image
from resizeimage.imageexceptions import ImageSizeError
from zimscraperlib.download import stream_file
from zimscraperlib.image.optimization import OptimizeWebpOptions, optimize_webp
from zimscraperlib.image.probing import format_for
from zimscraperlib.image.transformation import resize_image

from sotoki.constants import (
    FILES_DOWNLOAD_FAILURE_MINIMUM_FOR_CHECK,
    FILES_DOWNLOAD_FAILURE_TRESHOLD_PER_TEN_THOUSAND,
    FILES_DOWNLOAD_MAX_INTERVAL,
    HTTP_REQUEST_TIMEOUT,
    IMAGES_ENCODER_VERSION,
    MAX_FILE_DOWNLOAD_RETRIES,
    POSTS_IMAGE_SIZE,
    USER_AGENT,
)
from sotoki.utils.database.files import File, FileDatabase
from sotoki.utils.html import parse_retry_after_header
from sotoki.utils.shared import context, logger, shared


@dataclass(kw_only=True)
class HostData:
    files_to_download: FileDatabase
    last_request_date: datetime | None = None
    request_interval_milliseconds: float = 10
    not_before_date: datetime | None = None
    download_success: int = 0
    download_failure: int = 0
    downloads_complete: bool = False


@dataclass(kw_only=True)
class FileToDownload(File):
    host_data: HostData
    hostname: str


class Imager:
    def __init__(self):
        # list of source URLs that we've processed and added to ZIM
        self.aborted = False
        self.handled = []
        self.nb_requested = 0
        self.nb_failed = 0
        self.nb_done = 0
        self.filesDatabases: list[FileDatabase] = []
        self.hosts: dict[str, HostData] = {}
        self.hosts_with_bad_retry_after: set[str] = set()

    def abort(self):
        """request imager to cancel processing of futures"""
        self.aborted = True

    def get_image_data(self, url: str, **resize_args: Any) -> tuple[io.BytesIO, str]:
        """Bytes stream of an optimized, resized WebP of the source image"""
        src, webp = io.BytesIO(), io.BytesIO()
        stream_file(url=url, byte_stream=src, headers={"User-Agent": USER_AGENT})
        if format_for(src, from_suffix=False) == "SVG":
            return src, "image/svg+xml"
        # first resize then convert to webp and optimize, because conversion to webp
        # proved to consume lots of memory ; a smaller image obviously consumes less
        resize_args = resize_args or {}
        try:
            resize_image(
                src,
                **resize_args,
                allow_upscaling=False,
            )
        except ImageSizeError:
            # ignore issues about image being too small, this is not an issue but a
            # expected behavior (rather than querying for image size and resizing
            # only if needed on our own, we let the library do it better than we
            # would do)
            pass
        with Image.open(src) as img:
            img.save(webp, format="WEBP")
        return (
            optimize_webp(  # pyright: ignore[reportReturnType]
                src=webp,
                options=OptimizeWebpOptions(lossless=False, quality=60, method=6),
            ),
            "image/webp",
        )

    def get_s3_key_for(self, url: str) -> str:
        """S3 key to use for that url"""
        return re.sub(r"^(https?)://", r"\1/", url)

    def get_digest_for(self, url: str) -> str:
        """Unique identifier of that url"""
        return hashlib.md5(url.encode("UTF-8")).hexdigest()  # nosec # noqa: S324

    def get_version_ident_for(self, url: str) -> str | None:
        """~version~ of the URL data to use for comparisons. Built from headers"""
        try:
            resp = requests.head(
                url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_REQUEST_TIMEOUT
            )
            headers = resp.headers
        except Exception:
            logger.warning(f"Unable to HEAD {url}")
            _, headers = stream_file(
                url=url,
                headers={"User-Agent": USER_AGENT},
                byte_stream=io.BytesIO(),
                block_size=1,
                only_first_block=True,
            )

        for header in ("ETag", "Last-Modified", "Content-Length"):
            if headers.get(header):
                return headers.get(header)

        return "-1"

    def defer(
        self,
        url: str,
        path: str | None = None,
    ) -> str | None:
        """request full processing of url, returning in-zim path immediately"""

        # find actual URL should it be from a provider
        try:
            parsed_url = urllib.parse.urlparse(url)
        except Exception:
            logger.warning(f"Can't parse image URL `{url}`. Skipping")
            return

        if parsed_url.scheme not in ("http", "https"):
            logger.warning(
                f"Not supporting image URL `{parsed_url.geturl()}`. Skipping"
            )
            return

        if not parsed_url.hostname:
            logger.warning(
                f"Not supporting empty image hostname `{parsed_url.geturl()}`. Skipping"
            )
            return

        digest = self.get_digest_for(parsed_url.geturl())
        if path is None:
            path = f"images/{digest}"

        # do not add same image to process twice
        if digest in self.handled:
            return path

        # record that we are processing this one
        self.handled.append(digest)

        self.nb_requested += 1

        if parsed_url.hostname not in self.hosts:
            files_to_download = FileDatabase(parsed_url.hostname)
            self.filesDatabases.append(files_to_download)
            files_to_download.flush()
            self.hosts[parsed_url.hostname] = HostData(
                files_to_download=files_to_download
            )
        self.hosts[parsed_url.hostname].files_to_download.push(
            File(url=parsed_url.geturl(), zim_path=path, download_attempts=0)
        )

        return path

    def once_done(self):
        """default callback for single image processing"""
        # logger.debug("Once DONE")
        self.nb_done += 1
        shared.progresser.update(incr=1)

    def process_images(self):
        logger.info("Starting images download")
        for hostname, host_data in self.hosts.items():
            logger.info(f"- {hostname}: {host_data.files_to_download.len()}")
        shared.progresser.start(
            shared.progresser.IMAGES_STEP, nb_total=self.nb_requested
        )
        shared.img_executor.start()
        for _ in range(shared.img_executor.nb_workers):
            shared.img_executor.submit(self.worker_loop)
        while not self.aborted and (self.nb_done + self.nb_failed) < self.nb_requested:
            sleep(2)

    def _get_next_file_to_download(self) -> FileToDownload | None:
        while not self.aborted:
            now = datetime.now(UTC)

            # check if all downloads have completed and exit
            if all(host.downloads_complete for host in self.hosts.values()):
                logger.debug("all hosts have done all downloads")
                return None

            for hostname, host_data in self.hosts.items():
                # check for conditions which leads to ignore current host
                if (
                    host_data.downloads_complete
                    or (
                        host_data.not_before_date is not None
                        and host_data.not_before_date > now
                    )
                    or (
                        host_data.last_request_date is not None
                        and host_data.last_request_date
                        + timedelta(
                            milliseconds=host_data.request_interval_milliseconds
                        )
                        > now
                    )
                ):
                    continue

                # grab new file from Redis queue
                file_to_download = host_data.files_to_download.pop()
                if file_to_download is None:
                    logger.debug(f"{hostname} has completed all its downloads")
                    host_data.downloads_complete = True
                    continue

                # modify lastRequestDate immediately so that all workers are aware
                host_data.last_request_date = now
                return FileToDownload(
                    url=file_to_download.url,
                    zim_path=file_to_download.zim_path,
                    download_attempts=file_to_download.download_attempts,
                    host_data=host_data,
                    hostname=hostname,
                )

            # pause few milliseconds, no host has something to process yet (just to not
            # burn CPU)
            sleep(0.01)

    def worker_loop(self):
        try:
            while not self.aborted:
                with shared.lock:
                    next_file = self._get_next_file_to_download()
                if next_file is None:
                    break
                self.process_image(next_file)
            logger.debug("worker loop completed")
        except Exception:
            self.abort()

    def process_image(
        self,
        file: FileToDownload,
    ):
        """download image from url or S3 and add to Zim at path. Upload if req."""

        if (
            self.nb_failed > FILES_DOWNLOAD_FAILURE_MINIMUM_FOR_CHECK
            and (self.nb_failed * 10000) / self.nb_requested
            > FILES_DOWNLOAD_FAILURE_TRESHOLD_PER_TEN_THOUSAND
        ):
            raise Exception(
                f"Too many files failed to download: [{self.nb_failed}/"
                f"{self.nb_requested}]"
            )

        try:
            self.download_image(file)
        except requests.exceptions.RequestException as exc:
            if isinstance(exc, requests.HTTPError):
                err_details = f"HTTP error code {exc.response.status_code}"
                err_status_code = exc.response.status_code
            else:
                err_details = str(exc)
                err_status_code = None
            if file.download_attempts > MAX_FILE_DOWNLOAD_RETRIES:
                logger.warning(
                    f"Error downloading file {file.url}, too many attempts failed, last"
                    f" one failed with '{err_details}', skipping"
                )
                file.host_data.download_failure += 1
                self.nb_failed += 1
                return
            if err_status_code == HTTPStatus.NOT_FOUND:
                logger.warning(
                    f"Error downloading file {file.url}, received a 404, skipping"
                )
                file.host_data.download_failure += 1
                self.nb_failed += 1
                return

            if isinstance(exc, requests.HTTPError):
                retry_after_header = exc.response.headers.get("Retry-After")
                # ignore Retry-After header of some hosts giving bad values
                if retry_after_header and file.hostname not in ["i.imgur.com"]:
                    retry_date = parse_retry_after_header(retry_after_header)
                    if retry_date:
                        file.host_data.not_before_date = retry_date
                        logger.info(
                            f"Received a [Retry-After={retry_after_header}], pausing "
                            f"down {file.hostname} until {retry_date}"
                        )
                    elif file.hostname not in self.hosts_with_bad_retry_after:
                        self.hosts_with_bad_retry_after.add(file.hostname)
                        logger.warning(
                            f"Received a [Retry-After={retry_after_header}] from "
                            f"{file.hostname} but failed to interpret it (other 'bad'"
                            "Retry-After from this host will not issue a warning log)"
                        )

                if exc.response.status_code in [
                    HTTPStatus.TOO_MANY_REQUESTS,
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    524,
                ]:
                    # 1.2 is arbitrary value to progressively slow requests to host down
                    file.host_data.request_interval_milliseconds = min(
                        FILES_DOWNLOAD_MAX_INTERVAL,
                        file.host_data.request_interval_milliseconds * 1.2,
                    )
                    logger.info(
                        f"Received a {exc.response.status_code} HTTP status for "
                        f"{file.url}. Slowing down {file.hostname} to"
                        f" {file.host_data.request_interval_milliseconds}ms interval"
                        f" ({file.host_data.files_to_download.len()} files remaining"
                        " to download from host)"
                    )

            # put file back in the queue
            file.host_data.files_to_download.push(file)
        except Exception:
            logger.exception(f"Error downloading file {file.url}, skipping")
            file.host_data.download_failure += 1
            self.nb_failed += 1
        else:
            file.host_data.download_success += 1

    def download_image(self, file: FileToDownload):
        if self.aborted:
            return

        # setup resizing based on request
        resize_args = {"width": POSTS_IMAGE_SIZE}

        parsed_url = urllib.parse.urlparse(file.url)

        # just download, optimize and add to ZIM if not using S3
        if not context.s3_url_with_credentials:
            file.download_attempts += 1
            image_content, image_mimetype = self.get_image_data(
                parsed_url.geturl(), **resize_args
            )
            with shared.lock:
                shared.creator.add_item_for(
                    path=file.zim_path,
                    content=image_content.getvalue(),
                    mimetype=image_mimetype,
                    is_front=False,
                    # callbacks=Callback(func=self.once_done),
                )
            self.once_done()
            return

        if not shared.s3_storage:
            raise Exception("S3 storage should already have been initialized")

        # we are using S3 cache
        ident = self.get_version_ident_for(parsed_url.geturl())
        if ident is None:
            logger.error(f"Unable to query {parsed_url.geturl()}. Skipping")
            return

        key = self.get_s3_key_for(parsed_url.geturl())
        meta = {"ident": ident, "encoder_version": str(IMAGES_ENCODER_VERSION)}

        download_failed = False  # useful to trigger reupload or not
        try:
            logger.debug(f"Attempting download of S3::{key} into ZIM::{file.zim_path}")
            image_content = io.BytesIO()
            shared.s3_storage.download_matching_fileobj(key, image_content, meta=meta)
        except NotFoundError:
            # don't have it, not a donwload error. we'll upload after processing
            pass
        except Exception as exc:
            logger.error(f"failed to download {key} from cache: {exc}")
            logger.exception(exc)
            download_failed = True
        else:
            image_mimetype = format_for(image_content, from_suffix=False)
            with shared.lock:
                shared.creator.add_item_for(
                    path=file.zim_path,
                    content=image_content.getvalue(),
                    mimetype=image_mimetype,
                    is_front=False,
                    # callbacks=Callback(func=self.once_done),
                )
            self.once_done()
            return

        if not key or not meta:
            raise Exception("s3_key and s3_meta should have been populated")

        # we're using S3 but don't have it or failed to download
        file.download_attempts += 1
        image_content, image_mimetype = self.get_image_data(
            parsed_url.geturl(), **resize_args
        )

        with shared.lock:
            shared.creator.add_item_for(
                path=file.zim_path,
                content=image_content.getvalue(),
                mimetype=image_mimetype,
                is_front=False,
                # callbacks=Callback(func=self.once_done),
            )
        self.once_done()

        # only upload it if we didn't have it in cache
        if not download_failed:
            logger.debug(f"Uploading {parsed_url.geturl()} to S3::{key} with {meta}")
            try:
                shared.s3_storage.upload_fileobj(
                    fileobj=image_content, key=key, meta=meta
                )
            except Exception as exc:
                logger.error(f"{key} failed to upload to cache: {exc}")

        return
