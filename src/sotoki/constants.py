#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import pathlib
import datetime
import re
import tempfile
import urllib.parse
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

import bs4
import requests
from zimscraperlib.i18n import get_language_details, NotFound
from urllib.parse import urlparse

ROOT_DIR = pathlib.Path(__file__).parent
NAME = ROOT_DIR.name

with open(ROOT_DIR.joinpath("VERSION"), "r") as fh:
    VERSION = fh.read().strip()

UTF8 = "utf-8"
SCRAPER = f"{NAME} {VERSION}"
USER_AGENT = (
    f"{NAME}/{VERSION} (https://github.com/openzim/sotoki; "
    f"contact+crawl@kiwix.org) requests/{requests.__version__}"
)
PROFILE_IMAGE_SIZE = 128
POSTS_IMAGE_SIZE = 540
IMAGES_ENCODER_VERSION = 1
NB_QUESTIONS_PER_TAG_PAGE = 15
NB_PAGES_PER_TAG = 100
NB_PAGINATED_QUESTIONS_PER_TAG = NB_QUESTIONS_PER_TAG_PAGE * NB_PAGES_PER_TAG
NB_QUESTIONS_PER_PAGE = 15
NB_QUESTIONS_PAGES = 100
NB_PAGINATED_QUESTIONS = NB_QUESTIONS_PER_PAGE * NB_QUESTIONS_PAGES
NB_USERS_PER_PAGE = 36
NB_USERS_PAGES = 100
NB_PAGINATED_USERS = NB_USERS_PER_PAGE * NB_USERS_PAGES


def langs_for_domain(domain: str) -> Tuple[List[str], List[str]]:
    """(ISO-639-1 lang codes, ISO-639-3 lang codes) for a domain"""
    iso_langs_1, iso_langs_3 = ["en"], ["eng"]
    match = re.match(r"^(?P<lang>[a-z]+)\.(stackexchange|stackoverflow)\.com$", domain)
    if match:
        so_code = match.groupdict()["lang"]
        if so_code not in (
            "meta",
            "diy",
            "sqa",
            "tor",
            "dba",
            "tex",
            "law",
            "ham",
            "gis",
            "ell",
            "or",
            "vi",
            "cs",
        ):
            try:
                lang = get_language_details(so_code)
                if not lang["iso-639-1"] or not lang["iso-639-3"]:
                    raise NotFound("Might be an abbreviation")
                if lang["iso-639-1"] not in iso_langs_1:
                    iso_langs_1.append(lang["iso-639-1"])
                if lang["iso-639-3"] not in iso_langs_3:
                    iso_langs_3.append(lang["iso-639-3"])
            except NotFound:
                ...
    return iso_langs_1, iso_langs_3


@dataclass
class Sotoconf:
    required = [
        "domain",
        "name",
        "output_dir",
        "keep_build_dir",
        "nb_threads",
        "title",
        "description"
    ]

    domain: str
    redis_url: str

    # zim params
    name: str
    title: str = ""
    description: str = ""
    long_description: Optional[str] = ""
    illustration: str = ""
    big_favicon: Optional[str] = ""
    small_favicon: Optional[str] = ""
    author: Optional[str] = ""
    publisher: Optional[str] = ""
    fname: Optional[str] = ""
    tag: List[str] = field(default_factory=list)
    flavour: Optional[str] = ""
    iso_langs_1: List[str] = field(default_factory=list)  # ISO-639-1
    iso_langs_3: List[str] = field(default_factory=list)  # ISO-639-3

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
    keep_redis: Optional[bool] = False
    debug: Optional[bool] = False
    prepare_only: Optional[bool] = False
    keep_intermediate_files: Optional[bool] = False
    stats_filename: Optional[str] = None
    build_dir_is_tmp_dir: Optional[bool] = False
    defrag_redis: Optional[str] = ""
    open_shell: Optional[bool] = False
    skip_tags_meta: Optional[bool] = False
    skip_questions_meta: Optional[bool] = False
    skip_users: Optional[bool] = False

    @property
    def tags(self):
        return list(set(self.tag))

    @property
    def s3_url(self):
        return self.s3_url_with_credentials

    @property
    def with_user_identicons(self):
        return not self.without_images and not self.without_user_identicons

    @property
    def redis_pid(self):
        if not self.defrag_redis:
            return
        if self.defrag_redis == "service":
            return self.defrag_redis
        if self.defrag_redis.isnumeric():
            return int(self.defrag_redis)
        m = re.match(r"^ENV:(?P<name>.+)", self.defrag_redis)
        if m and m.groupdict().get("name"):
            try:
                return int(os.getenv(m.groupdict().get("name")))
            except Exception:
                return

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

    def _get_site_details(self):
        resp = requests.get(f"https://{self.domain}")
        resp.raise_for_status()
        soup = bs4.BeautifulSoup(resp.text, "lxml")
        site_title = soup.title.string
        if not site_title:
            raise Exception("Failed to extract site title from homepage")
        primary_css = str(soup.find('link', href=lambda href: href and 'primary.css' in href)["href"])
        if not primary_css:
            raise Exception("Failed to extract primary CSS from homepage")
        self.site_details = {
            "mathjax": '<script type="text/x-mathjax-config">' in resp.text,
            "highlight": '"styleCodeWithHighlightjs":true' in resp.text,
            "domain": urlparse(resp.url).netloc,
            "site_title": site_title,
            "primary_css": primary_css,
            "secondary_css": primary_css.replace("primary", "secondary")
        }

    def __post_init__(self):
        self.dump_domain = self.domain  # dumps are named after unfixed domains
        self._get_site_details()
        self.domain = self.site_details.get("domain") # real domain as found online after potential redirection for fixed domains
        self.iso_langs_1, self.iso_langs_3 = langs_for_domain(self.domain)
        self.flavour = "nopic" if self.without_images else ""
        lang_in_name = self.iso_langs_1[0] if len(self.iso_langs_1) == 1 else "mul"
        self.name = self.name or f"{self.domain}_{lang_in_name}_all_{self.flavour}" if self.flavour else f"{self.domain}_{lang_in_name}_all"
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
        if self.stats_filename:
            self.stats_filename = pathlib.Path(self.stats_filename).expanduser()
            self.stats_filename.parent.mkdir(parents=True, exist_ok=True)

        redis_url = urllib.parse.urlparse(self.redis_url)
        if redis_url and redis_url.scheme not in ("unix", "redis"):
            raise ValueError(
                f"Unknown scheme `{redis_url.scheme}` for redis. "
                "Use redis:// or unix://"
            )

        self.tag += [
            "_category:stack_exchange",
            "stack_exchange",
            "_videos:no",
            "_details:no",
        ]

        if self.without_images:
            self.tag.append("_pictures:no")

        # shell implies debug
        if self.open_shell:
            self.debug = True
