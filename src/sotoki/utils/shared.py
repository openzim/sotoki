#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu
# pylint: disable=cyclic-import

import gc
import datetime
import threading
import logging

from zimscraperlib.zim.creator import Creator
from zimscraperlib.logging import getLogger as lib_getLogger
from zimscraperlib.inputs import handle_user_provided_file
from zimscraperlib.image.convertion import convert_image
from zimscraperlib.image.transformation import resize_image

from ..constants import NAME, SCRAPER


class Global:
    """Shared context accross all scraper components"""

    class DatabaseException(Exception):
        pass

    debug = False
    logger = lib_getLogger(
        NAME,
        level=logging.INFO,
        log_format="[%(threadName)s::%(asctime)s] %(levelname)s:%(message)s",
    )
    conf = None

    site = None
    progresser = None

    database = None
    creator = None
    imager = None
    renderer = None
    rewriter = None
    total_tags = 0
    total_questions = 0
    total_users = 0
    lock = threading.Lock()

    @staticmethod
    def collect():
        logger.debug(f"Collecting {gc.get_count()}… {gc.collect()} collected.")

    @staticmethod
    def set_debug(value):
        Global.debug = value
        level = logging.DEBUG if value else logging.INFO
        Global.logger.setLevel(level)
        for handler in Global.logger.handlers:
            handler.setLevel(level)

    @staticmethod
    def init():
        from .progress import Progresser

        Global.progresser = Progresser(Global.total_questions)

    @staticmethod
    def setup():
        # order matters are there are references between them

        from .database import get_database

        try:
            Global.database = get_database()
        except Exception as exc:
            raise Global.DatabaseException(exc)

        # all tasks added to a bound queue processed by workers
        from .executor import SotokiExecutor

        # mostly transforms HTML and sends to zim.
        # tests show no speed improv. beyond 3 workers.
        Global.executor = SotokiExecutor(
            queue_size=10,
            nb_workers=3,
        )

        # images handled on a different queue.
        # mostly network I/O to retrieve and/or upload image.
        # if not in S3 bucket, resize/optimize webp image
        # we should consider using coroutines instead of threads
        Global.img_executor = SotokiExecutor(
            queue_size=200,
            nb_workers=100,
            prefix="IMG-T-",
        )

        from .imager import Imager

        Global.imager = Imager()

        from .html import Rewriter

        Global.rewriter = Rewriter()

        from ..renderer import Renderer

        Global.renderer = Renderer()

        # load illustration data, required for creator metadata setup
        # the following code section is taken from sotoki.scraper.add_illustrations()
        illus_nosuffix_fpath = Global.conf.build_dir / "illustration"
        handle_user_provided_file(source=Global.conf.illustration, dest=illus_nosuffix_fpath)

        # convert to PNG (might already be PNG but it's OK)
        illus_fpath = illus_nosuffix_fpath.with_suffix(".png")
        convert_image(illus_nosuffix_fpath, illus_fpath)

        # resize to appropriate size
        resize_image(illus_fpath, width=48, height=48, method="thumbnail")
        with open(illus_fpath, "rb") as fh:
            illustration_data = fh.read()

        Global.creator = Creator(
            filename=Global.conf.output_dir.joinpath(Global.conf.fname),
            main_path="questions",
       ).config_metadata(
            Name=Global.conf.name,
            Language=",".join(Global.conf.iso_langs_3),  # python-scraperlib needs language list as a single string
            Title=Global.conf.title,
            Description=Global.conf.description,
            LongDescription=Global.conf.long_description,
            Creator=Global.conf.author,
            Publisher=Global.conf.publisher,
            Date=datetime.date.today(),
            Illustration_48x48_at_1=illustration_data,
            Tags=Global.conf.tags,
            Scraper=SCRAPER,
            Flavour=Global.conf.flavour,
            # Source=,
            License="CC-BY-SA",  # as per stack exchange ToS, see about page in ZIM
            # Relation=,
        ).config_verbose(True)


class GlobalMixin:
    @property
    def conf(self):
        return Global.conf

    @property
    def site(self):
        return Global.conf.site_details

    @property
    def database(self):
        return Global.database

    @property
    def creator(self):
        return Global.creator

    @property
    def lock(self):
        return Global.lock

    @property
    def imager(self):
        return Global.imager

    @property
    def executor(self):
        return Global.executor

    @property
    def renderer(self):
        return Global.renderer

    @property
    def rewriter(self):
        return Global.rewriter

    @property
    def progresser(self):
        return Global.progresser


logger = Global.logger
