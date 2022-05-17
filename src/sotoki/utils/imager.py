#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import io
import re
import zlib
import urllib.parse
from typing import Optional

import requests
from PIL import Image
from resizeimage.imageexceptions import ImageSizeError
from zimscraperlib.download import stream_file
from zimscraperlib.image.optimization import optimize_webp
from zimscraperlib.image.transformation import resize_image
from kiwixstorage import KiwixStorage, NotFoundError

from ..constants import (
    PROFILE_IMAGE_SIZE,
    POSTS_IMAGE_SIZE,
    IMAGES_ENCODER_VERSION,
    USER_AGENT,
)
from .misc import rebuild_uri
from .shared import Global

logger = Global.logger


class GoogleImageProvider:
    def matches(self, url: str, for_profile: bool) -> bool:
        return for_profile and url.hostname.endswith(".googleusercontent.com")

    def get_source_url(self, url, for_profile: bool) -> str:
        if not for_profile:
            return url
        qs = urllib.parse.parse_qs(url.query)
        qs["sz"] = PROFILE_IMAGE_SIZE
        return rebuild_uri(url, query=urllib.parse.urlencode(qs, doseq=True))


class GravatarImageProvider:
    def matches(self, url: str, for_profile: bool) -> bool:
        return (
            for_profile
            and url.hostname == "www.gravatar.com"
            and "d=identicon" not in url.query
        )

    def get_source_url(self, url, for_profile: bool) -> str:
        if not for_profile:
            return url
        qs = urllib.parse.parse_qs(url.query)
        qs["s"] = PROFILE_IMAGE_SIZE
        return rebuild_uri(url, query=urllib.parse.urlencode(qs, doseq=True))


class GravatarIdenticonProvider:
    def matches(self, url: str, for_profile: bool) -> bool:
        return (
            for_profile
            and url.hostname == "www.gravatar.com"
            and "d=identicon" in url.query
        )

    def get_source_url(self, url, for_profile: bool) -> str:
        if not for_profile:
            return url
        qs = urllib.parse.parse_qs(url.query)
        qs["s"] = PROFILE_IMAGE_SIZE
        return rebuild_uri(url, query=urllib.parse.urlencode(qs, doseq=True))


class StackImgurProvider:
    """SE's used i.stack.imgur.com for both profile and post images

    For profile, it's an option next to several others.
    For Posts, it's the upload option and the only alternative is to
    provide an URL.

    i.stack.imgur.com provides on demand resizing based on ?s= param
    but this is usable only for profile picture as this does a square thumbnail
    and would break any non-square image.
    Also, it only works on powers of 2 sizes, up to the image's width."""

    def matches(self, url: str, for_profile: bool) -> bool:
        return for_profile and url.hostname == "i.stack.imgur.com"

    def get_source_url(self, url, for_profile: bool) -> str:
        if not for_profile:
            return url
        qs = urllib.parse.parse_qs(url.query)
        qs["s"] = PROFILE_IMAGE_SIZE
        return rebuild_uri(url, query=urllib.parse.urlencode(qs, doseq=True))


class Imager:
    def __init__(self):
        # list of source URLs that we've processed and added to ZIM
        self.aborted = False
        self.handled = []
        self.nb_requested = 0
        self.nb_done = 0

        self.providers = [
            StackImgurProvider(),
            GravatarIdenticonProvider(),
            GravatarImageProvider(),
            GoogleImageProvider(),
        ]

        Global.img_executor.start()

    def abort(self):
        """request imager to cancel processing of futures"""
        self.aborted = True

    def get_source_url(self, url: str, for_profile: bool = False) -> str:
        """Actual source URL to use. Might be changed by a Provider"""
        for provider in self.providers:
            if provider.matches(url, for_profile=for_profile):
                return provider.get_source_url(url, for_profile=for_profile)
        # no provider
        return url

    def get_image_data(self, url: str, **resize_args: dict) -> io.BytesIO:
        """Bytes stream of an optimized, resized WebP of the source image"""
        src, webp = io.BytesIO(), io.BytesIO()
        stream_file(url=url, byte_stream=src)
        with Image.open(src) as img:
            img.save(webp, format="WEBP")
        del src
        resize_args = resize_args or {}
        try:
            resize_image(
                src=webp,
                **resize_args,
                allow_upscaling=False,
            )
        except ImageSizeError as exc:
            logger.debug(f"Resize Error for {url}: {exc}")
        return optimize_webp(
            src=webp,
            lossless=False,
            quality=60,
            method=6,
        )

    def get_s3_key_for(self, url: str) -> str:
        """S3 key to use for that url"""
        return re.sub(r"^(https?)://", r"\1/", url)

    def get_digest_for(self, url: str) -> str:
        """Unique identifier of that url"""
        return zlib.adler32(url.encode("UTF-8"))

    def get_version_ident_for(self, url: str) -> str:
        """~version~ of the URL data to use for comparisons. Built from headers"""
        try:
            resp = requests.head(url, headers={"User-Agent": USER_AGENT})
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
        path: Optional[str] = None,
        is_profile: bool = False,
        once_done: Optional[callable] = None,
    ) -> str:
        """request full processing of url, returning in-zim path immediately"""

        # find actual URL should it be from a provider
        logger.debug(f"deferring {url=} {path=} {is_profile=}")
        try:
            url = urllib.parse.urlparse(url)
            url = self.get_source_url(url, for_profile=is_profile)
        except Exception:
            logger.warning(f"Can't parse image URL `{url}`. Skipping")
            return

        if url.scheme not in ("http", "https"):
            logger.warning(f"Not supporting image URL `{url.geturl()}`. Skipping")
            return

        # skip processing if we already processed it or have it in pipe
        digest = self.get_digest_for(url.geturl())
        if path is None:
            path = f"images/{digest}.webp"

        if digest in self.handled:
            logger.debug(f"URL `{url.geturl()}` already processed.")
            return path

        # record that we are processing this one
        self.handled.append(digest)

        self.nb_requested += 1

        Global.img_executor.submit(
            self.process_image,
            url=url,
            path=path,
            is_profile=is_profile,
            dont_release=True,
        )

        return path

    def once_done(self):
        """default callback for single image processing"""
        self.nb_done += 1
        Global.progresser.update()

    def process_image(self, url: str, path, is_profile: bool = False) -> str:
        """download image from url or S3 and add to Zim at path. Upload if req."""

        if self.aborted:
            return

        # setup resizing based on request
        resize_args = (
            {
                "width": PROFILE_IMAGE_SIZE,
                "height": PROFILE_IMAGE_SIZE,
                "method": "thumbnail",
            }
            if is_profile
            else {"width": POSTS_IMAGE_SIZE}
        )

        # just download, optimize and add to ZIM if not using S3
        if not Global.conf.s3_url:
            with Global.lock:
                Global.creator.add_item_for(
                    path=path,
                    content=self.get_image_data(url.geturl(), **resize_args).getvalue(),
                    mimetype="image/webp",
                    is_front=False,
                    callback=self.once_done,
                )
            return path

        # we are using S3 cache
        ident = self.get_version_ident_for(url.geturl())
        if ident is None:
            logger.error(f"Unable to query {url.geturl()}. Skipping")
            return path

        key = self.get_s3_key_for(url.geturl())
        s3_storage = KiwixStorage(Global.conf.s3_url)
        meta = {"ident": ident, "encoder_version": str(IMAGES_ENCODER_VERSION)}

        download_failed = False  # useful to trigger reupload or not
        try:
            logger.debug(f"Attempting download of S3::{key} into ZIM::{path}")
            fileobj = io.BytesIO()
            s3_storage.download_matching_fileobj(key, fileobj, meta=meta)
        except NotFoundError:
            # don't have it, not a donwload error. we'll upload after processing
            pass
        except Exception as exc:
            logger.error(f"failed to download {key} from cache: {exc}")
            logger.exception(exc)
            download_failed = True
        else:
            with Global.lock:
                Global.creator.add_item_for(
                    path=path,
                    content=fileobj.getvalue(),
                    mimetype="image/webp",
                    is_front=False,
                    callback=self.once_done,
                )
            return path

        # we're using S3 but don't have it or failed to download
        try:
            fileobj = self.get_image_data(url.geturl(), **resize_args)
        except Exception as exc:
            logger.error(f"Failed to download/convert/optim source  at {url.geturl()}")
            logger.exception(exc)
            return path

        with Global.lock:
            Global.creator.add_item_for(
                path=path,
                content=fileobj.getvalue(),
                mimetype="image/webp",
                is_front=False,
                callback=self.once_done,
            )

        # only upload it if we didn't have it in cache
        if not download_failed:
            logger.debug(f"Uploading {url.geturl()} to S3::{key} with {meta}")
            try:
                s3_storage.upload_fileobj(fileobj=fileobj, key=key, meta=meta)
            except Exception as exc:
                logger.error(f"{key} failed to upload to cache: {exc}")

        return path
