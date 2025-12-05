#!/usr/bin/env python

import hashlib
import io
import re
import urllib.parse
from typing import Any

import requests
from kiwixstorage import KiwixStorage, NotFoundError
from PIL import Image
from resizeimage.imageexceptions import ImageSizeError
from zimscraperlib.download import stream_file
from zimscraperlib.image.optimization import OptimizeWebpOptions, optimize_webp
from zimscraperlib.image.probing import format_for
from zimscraperlib.image.transformation import resize_image
from zimscraperlib.typing import Callback

from sotoki.constants import (
    HTTP_REQUEST_TIMEOUT,
    IMAGES_ENCODER_VERSION,
    POSTS_IMAGE_SIZE,
    USER_AGENT,
)
from sotoki.utils.misc import web_backoff
from sotoki.utils.shared import context, logger, shared


class Imager:
    def __init__(self):
        # list of source URLs that we've processed and added to ZIM
        self.aborted = False
        self.handled = []
        self.nb_requested = 0
        self.nb_done = 0
        shared.img_executor.start()

    def abort(self):
        """request imager to cancel processing of futures"""
        self.aborted = True

    @web_backoff
    def get_image_data(self, url: str, **resize_args: Any) -> tuple[io.BytesIO, str]:
        """Bytes stream of an optimized, resized WebP of the source image"""
        src, webp = io.BytesIO(), io.BytesIO()
        stream_file(url=url, byte_stream=src)
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

    @web_backoff
    def get_version_ident_for(self, url: str) -> str | None:
        """~version~ of the URL data to use for comparisons. Built from headers"""
        try:
            resp = requests.head(
                url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_REQUEST_TIMEOUT
            )
            headers = resp.headers
        except Exception:
            logger.warning(f"Unable to HEAD {url}")
            try:
                _, headers = stream_file(
                    url=url,
                    headers={"User-Agent": USER_AGENT},
                    byte_stream=io.BytesIO(),
                    block_size=1,
                    only_first_block=True,
                )
            except Exception:
                logger.warning(f"Unable to query image at {url}")
                return

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

        # skip processing if we already processed it or have it in pipe
        digest = self.get_digest_for(parsed_url.geturl())
        if path is None:
            path = f"images/{digest}"

        if digest in self.handled:
            logger.debug(f"URL `{parsed_url.geturl()}` already processed.")
            return path

        # record that we are processing this one
        self.handled.append(digest)

        self.nb_requested += 1

        shared.img_executor.submit(
            self.process_image,
            parsed_url=parsed_url,
            path=path,
            dont_release=True,
        )

        return path

    def once_done(self):
        """default callback for single image processing"""
        self.nb_done += 1
        shared.progresser.update()

    def process_image(
        self,
        *,
        parsed_url: urllib.parse.ParseResult,
        path: str,
    ) -> str | None:
        """download image from url or S3 and add to Zim at path. Upload if req."""

        if self.aborted:
            return

        # setup resizing based on request
        resize_args = {"width": POSTS_IMAGE_SIZE}

        # just download, optimize and add to ZIM if not using S3
        if not context.s3_url_with_credentials:
            image_content, image_mimetype = self.get_image_data(
                parsed_url.geturl(), **resize_args
            )
            with shared.lock:
                shared.creator.add_item_for(
                    path=path,
                    content=image_content.getvalue(),
                    mimetype=image_mimetype,
                    is_front=False,
                    callbacks=[Callback(func=self.once_done)],
                )
            return path

        # we are using S3 cache
        ident = self.get_version_ident_for(parsed_url.geturl())
        if ident is None:
            logger.error(f"Unable to query {parsed_url.geturl()}. Skipping")
            return path

        key = self.get_s3_key_for(parsed_url.geturl())
        s3_storage = KiwixStorage(context.s3_url_with_credentials)
        meta = {"ident": ident, "encoder_version": str(IMAGES_ENCODER_VERSION)}

        download_failed = False  # useful to trigger reupload or not
        try:
            logger.debug(f"Attempting download of S3::{key} into ZIM::{path}")
            image_content = io.BytesIO()
            s3_storage.download_matching_fileobj(key, image_content, meta=meta)
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
                    path=path,
                    content=image_content.getvalue(),
                    mimetype=image_mimetype,
                    is_front=False,
                    callbacks=[Callback(func=self.once_done)],
                )
            return path

        # we're using S3 but don't have it or failed to download
        try:
            image_content, image_mimetype = self.get_image_data(
                parsed_url.geturl(), **resize_args
            )
        except Exception as exc:
            logger.error(
                f"Failed to download/convert/optim source  at {parsed_url.geturl()}"
            )
            logger.exception(exc)
            return path

        with shared.lock:
            shared.creator.add_item_for(
                path=path,
                content=image_content.getvalue(),
                mimetype=image_mimetype,
                is_front=False,
                callbacks=[Callback(func=self.once_done)],
            )

        # only upload it if we didn't have it in cache
        if not download_failed:
            logger.debug(f"Uploading {parsed_url.geturl()} to S3::{key} with {meta}")
            try:
                s3_storage.upload_fileobj(fileobj=image_content, key=key, meta=meta)
            except Exception as exc:
                logger.error(f"{key} failed to upload to cache: {exc}")

        return path
