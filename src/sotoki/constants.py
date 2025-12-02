#!/usr/bin/env python3

import pathlib

import requests

from sotoki.__about__ import __version__

ROOT_DIR = pathlib.Path(__file__).parent


NAME = "sotoki"
VERSION = __version__

UTF8 = "utf-8"
SCRAPER = f"{NAME} v{VERSION}"
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

HTTP_REQUEST_TIMEOUT = 30
