#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import pathlib
import logging
import datetime
import tempfile
import threading
import urllib.parse
from typing import Optional, List
from dataclasses import dataclass, field

from zimscraperlib.logging import getLogger as lib_getLogger

ROOT_DIR = pathlib.Path(__file__).parent
NAME = ROOT_DIR.name

with open(ROOT_DIR.joinpath("VERSION"), "r") as fh:
    VERSION = fh.read().strip()

UTF8 = "utf-8"
SCRAPER = f"{NAME} {VERSION}"
DOWNLOAD_ROOT = "https://archive.org/download/stackexchange"
PROFILE_IMAGE_SIZE = 128
POSTS_IMAGE_SIZE = 540
IMAGES_ENCODER_VERSION = 1


class Global:
    """Shared context accross all scraper components"""

    debug = False
    conf = None  # main scraper configuration
    site = None
    database = None
    creator = None  # zim Creator
    imager = None  # image downloader/optimizer/uploader
    renderer = None  # HTML page renderer
    rewriter = None  # HTML content rewriter
    lock = threading.Lock()  # saves importing threading everywhere

    @staticmethod
    def setup(**kwargs):
        for name, value in kwargs.items():
            setattr(Global, name, value)


def setDebug(debug):
    """toggle constants global DEBUG flag (used by getLogger)"""
    Global.debug = bool(debug)


def getLogger():
    """configured logger respecting DEBUG flag"""
    return lib_getLogger(NAME, level=logging.DEBUG if Global.debug else logging.INFO)


@dataclass
class Sotoconf:
    required = [
        "domain",
        "name",
        "output_dir",
        "keep_build_dir",
        "nb_threads",
    ]

    domain: str
    _redis_url: str

    # zim params
    name: str
    title: Optional[str] = ""
    description: Optional[str] = ""
    author: Optional[str] = ""
    publisher: Optional[str] = ""
    fname: Optional[str] = ""
    tag: List[str] = field(default_factory=list)

    # customization
    favicon: Optional[str] = ""

    # filesystem
    _output_dir: Optional[str] = "."
    _tmp_dir: Optional[str] = "."
    output_dir: Optional[pathlib.Path] = None
    tmp_dir: Optional[pathlib.Path] = None
    build_dir: Optional[pathlib.Path] = None

    # performances
    nb_threads: Optional[int] = -1
    s3_url_with_credentials: Optional[str] = ""
    mirror: Optional[str] = ""

    # censorship
    censor_words_list: Optional[str] = ""
    without_images: Optional[bool] = False
    without_user_profiles: Optional[bool] = False
    without_user_identicons: Optional[bool] = False
    without_external_links: Optional[bool] = False
    without_unanswered: Optional[bool] = False
    without_users_links: Optional[bool] = False
    without_names: Optional[bool] = False

    # debug/devel
    keep_build_dir: Optional[bool] = False
    debug: Optional[bool] = False
    prepare_only: Optional[bool] = False
    keep_intermediate_files: Optional[bool] = False
    statsFilename: Optional[str] = None
    #
    build_dir_is_tmp_dir: Optional[bool] = False
    dump_date: Optional[datetime.date] = datetime.date.today()

    @property
    def s3_url(self):
        return self.s3_url_with_credentials

    @property
    def is_stackO(self):
        return self.domain == "stackoverflow.com"

    @property
    def with_user_identicons(self):
        return not self.without_images and not self.without_user_identicons

    @property
    def any_restriction(self):
        return any(
            (
                self.without_unanswered,
                self.without_user_identicons,
                self.without_external_links,
                self.without_user_profiles,
                self.without_images,
                self.without_names,
                self.without_users_links,
                self.censor_words_list,
            )
        )

    def __post_init__(self):
        self.name = self.domain.replace(".", "_")
        self.output_dir = pathlib.Path(self._output_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir = pathlib.Path(self._tmp_dir).expanduser().resolve()
        if self.tmp_dir:
            self.tmp_dir.mkdir(parents=True, exist_ok=True)
        if self.build_dir_is_tmp_dir:
            self.build_dir = self.tmp_dir
        else:
            self.build_dir = pathlib.Path(
                tempfile.mkdtemp(prefix=f"{self.domain}_", dir=self.tmp_dir)
            )

        self.redis_url = urllib.parse.urlparse(self._redis_url)
        if self.redis_url and self.redis_url.scheme not in ("file", "redis"):
            raise ValueError(
                f"Unknown scheme `{self.redis_url.scheme}` for redis. "
                "Use redis:// or file://"
            )
