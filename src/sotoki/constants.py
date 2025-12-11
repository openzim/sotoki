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
MAX_FILE_DOWNLOAD_RETRIES = 5
# minimum number of files failing download before starting to consider for failing
# the scrape
FILES_DOWNLOAD_FAILURE_MINIMUM_FOR_CHECK = 50
FILES_DOWNLOAD_FAILURE_TRESHOLD_PER_TEN_THOUSAND = 1000  # 10 = 0.1% ; 1000 = 10%
# 60000 = 60s max between file download attempts
FILES_DOWNLOAD_MAX_INTERVAL = 60000
# 10 = 10ms min between file download attempts
FILES_DOWNLOAD_MIN_INTERVAL = 10
# consider speeding download a bit once this amount of files have succeeded to download
FILES_DOWNLOAD_SPEED_UP_AFTER = 10
FILES_DOWNLOAD_SPEED_UP_FACTOR = 1.1
FILES_DOWNLOAD_SLOW_DOWN_FACTOR = 1.2
