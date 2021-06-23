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
from zimscraperlib.download import stream_file
from zimscraperlib.image.optimization import optimize_webp
from zimscraperlib.image.transformation import resize_image
from kiwixstorage import KiwixStorage

from ..constants import (
    getLogger,
    PROFILE_IMAGE_SIZE,
    POSTS_IMAGE_SIZE,
    IMAGES_ENCODER_VERSION,
    Global,
)

logger = getLogger()


def rebuild_uri(
    uri,
    scheme=None,
    username=None,
    password=None,
    hostname=None,
    port=None,
    path=None,
    params=None,
    query=None,
    fragment=None,
):
    """new named tuple from uri with request part updated"""
    scheme = scheme or uri.scheme
    username = username or uri.username
    password = password or uri.password
    hostname = hostname or uri.hostname
    port = port or uri.port
    path = path or uri.path
    netloc = ""
    if username:
        netloc += username
    if password:
        netloc += f":{password}"
    if username or password:
        netloc += "@"
    netloc += hostname
    if port:
        netloc += f":{port}"
    params = params or uri.params
    query = query or uri.query
    fragment = fragment or uri.fragment
    return urllib.parse.urlparse(
        urllib.parse.urlunparse([scheme, netloc, path, fragment, query, fragment])
    )


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
        self.handled = []
        self.nb_done = 0

        self.providers = [
            StackImgurProvider(),
            GravatarIdenticonProvider(),
            GravatarImageProvider(),
            GoogleImageProvider(),
        ]

    def get_source_url(self, url: str, for_profile: bool = False) -> str:
        """Actual source URL to use. Might be changed by a Provider"""
        for provider in self.providers:
            if provider.matches(url, for_profile=for_profile):
                return provider.get_source_url(url, for_profile=for_profile)
        # no provider
        logger.warning(f"No provider for {url.geturl()}")
        return url

    def get_image_data(self, url: str, **resize_args: dict) -> io.BytesIO:
        """Bytes stream of an optimized, resized WebP of the source image"""
        src, webp = io.BytesIO(), io.BytesIO()
        stream_file(url=url, byte_stream=src)
        with Image.open(src) as img:
            img.save(webp, format="WEBP")
        del src
        resize_args = resize_args or {}
        resize_image(
            src=webp,
            **resize_args,
            allow_upscaling=False,
        )
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
            resp = requests.head(url)
            headers = resp.headers
        except Exception:
            logger.warning(f"Unable to HEAD {url}")
            _, headers = stream_file(
                url=url, byte_stream=io.BytesIO(), block_size=1, only_first_block=True
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
            path = f"images/{digest}"

        if digest in self.handled:
            logger.debug(f"URL `{url}` already processed.")
            return path

        # record that we are processing this one
        self.handled.append(digest)

        future = Global.executor.submit(self.process_image, url=url, path=path)
        future.add_done_callback(once_done or self.once_done)

        return path

    def once_done(self, future):
        """default callback for single image processing"""
        self.nb_done += 1
        logger.debug(f"An image completed… ({self.nb_done}/{len(self.handled)})")
        return

    def process_image(self, url: str, path, is_profile: bool = False) -> str:
        """download image from url or S3 and add to Zim at path. Upload if req."""

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
                )
            return path

        # we are using S3 cache
        ident = self.get_version_ident_for(url.geturl())
        key = self.get_s3_key_for(url.geturl())
        s3_storage = KiwixStorage(Global.conf.s3_url)
        meta = {"ident": ident, "encoder_version": str(IMAGES_ENCODER_VERSION)}

        download_failed = False  # useful to trigger reupload or not
        if s3_storage.has_object_matching(key, meta=meta):
            logger.debug(f"Downloading S3::{key} into ZIM::{path}")
            # download file into memory
            fileobj = io.BytesIO()
            try:
                s3_storage.download_fileobj(key, fileobj)
            except Exception as exc:
                logger.error(f"failed to download {key} from cache: {exc}")
                logger.exception(exc)
                download_failed = True
            # make sure we fallback to re-encode
            else:
                with Global.lock:
                    Global.creator.add_item_for(
                        path=path,
                        title="",
                        content=fileobj.getvalue(),
                        mimetype="image/webp",
                    )
                return path

        # we're using S3 but don't have it or failed to download
        fileobj = self.get_image_data(url.geturl(), **resize_args)

        # only upload it if we didn't have it in cache
        if not download_failed:
            logger.debug(f"Uploading {url.geturl()} to S3::{key} with {meta}")
            try:
                s3_storage.upload_fileobj(fileobj=fileobj, key=key, meta=meta)
            except Exception as exc:
                logger.error(f"{key} failed to upload to cache: {exc}")

        return path
