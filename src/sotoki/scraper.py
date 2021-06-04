#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import shutil
import pathlib
import datetime
import threading
import concurrent.futures as cf

from zimscraperlib.zim.creator import Creator
from zimscraperlib.inputs import handle_user_provided_file
from zimscraperlib.image.convertion import convert_image
from zimscraperlib.image.transformation import resize_image

from .constants import getLogger, Sotoconf
from .archives import ArchiveManager
from .utils.s3 import setup_s3_and_check_credentials
from .utils.sites import get_site
from .utils.database import get_database
from .users import UserGenerator
from .posts import PostGenerator
from .tags import TagGenerator

logger = getLogger()


class StackExchangeToZim:
    def __init__(self, **kwargs):

        self.conf = Sotoconf(**kwargs)
        for option in self.conf.required:
            if getattr(self.conf, option) is None:
                raise ValueError(f"Missing parameter `{option}`")

        self.s3_storage = None

    @property
    def domain(self):
        return self.conf.domain

    @property
    def build_dir(self):
        return self.conf.build_dir

    def cleanup(self):
        """Remove temp files and release resources before exiting"""
        if not self.conf.keep_build_dir:
            logger.debug(f"Removing {self.build_dir}")
            shutil.rmtree(self.build_dir, ignore_errors=True)

    def sanitize_inputs(self):
        """input & metadata sanitation"""
        period = datetime.datetime.now().strftime("%Y-%m")
        if self.conf.fname:
            # make sure we were given a filename and not a path
            self.conf.fname = pathlib.Path(self.conf.fname.format(period=period))
            if pathlib.Path(self.conf.fname.name) != self.conf.fname:
                raise ValueError(f"filename is not a filename: {self.conf.fname}")
        else:
            self.conf.fname = f"{self.conf.name}_{period}.zim"

        if not self.conf.title:
            self.conf.title = self.site["LongName"]
        self.conf.title = self.conf.title.strip()

        if not self.conf.description:
            self.conf.description = self.site["Tagline"]
        self.conf.description = self.conf.description.strip()

        if not self.conf.author:
            self.conf.author = "Stack Exchange"
        self.conf.author = self.conf.author.strip()

        if not self.conf.publisher:
            self.conf.publisher = "Openzim"
        self.conf.publisher = self.conf.publisher.strip()

        self.conf.tags = list(
            set(self.conf.tag + ["_category:stack_exchange", "stack_exchange"])
        )

    def add_favicon(self):
        favicon_orig = self.build_dir / "favicon"

        # if user provided a custom favicon, retrieve that
        if not self.conf.favicon:
            self.conf.favicon = self.site["BadgeIconUrl"]
        handle_user_provided_file(source=self.conf.favicon, dest=favicon_orig)

        # convert to PNG (might already be PNG but it's OK)
        favicon_fpath = favicon_orig.with_suffix(".png")
        convert_image(favicon_orig, favicon_fpath)

        # resize to appropriate size (ZIM uses 48x48 so we double for retina)
        resize_image(favicon_fpath, width=96, height=96, method="thumbnail")

        self.creator.add_item_for("-/favicon", fpath=favicon_fpath)

    def run(self):
        if self.conf.s3_url_with_credentials:
            self.s3_storage = setup_s3_and_check_credentials(
                self.conf.s3_url_with_credentials
            )

        s3_msg = (
            f"  using cache: {self.s3_storage.url.netloc} "
            f"with bucket: {self.s3_storage.bucket_name}"
            if self.s3_storage
            else ""
        )
        logger.info(
            f"Starting scraper with:\n"
            f"  domain: {self.domain}\n"
            f"  build_dir: {self.build_dir}\n"
            f"  output_dir: {self.conf.output_dir}\n"
            f"{s3_msg}"
        )

        logger.debug("Fetching site details…")
        self.site = get_site(self.domain)
        if not self.site:
            logger.critical(
                f"Couldn't fetch detail for {self.domain}. Please check "
                "that it's a supported domain using --list-all."
            )
            return 1

        self.sanitize_inputs()

        logger.info("XML Dumps preparation")
        ark_manager = ArchiveManager(self.conf)
        ark_manager.check_and_prepare_dumps()
        del ark_manager

        if self.conf.prepare_only:
            logger.info("Requested preparation only; exiting")
            return

        self.start()

    def start(self):

        # all operations spread accross an nb_threads executor
        executor = cf.ThreadPoolExecutor(max_workers=self.conf.nb_threads)

        self.creator_lock = threading.Lock()
        self.creator = (
            Creator(
                filename=self.conf.output_dir.joinpath(self.conf.fname),
                main_path="home",
                favicon_path="-/favicon",
                language="eng",
                title=self.conf.title,
                description=self.conf.description,
                creator=self.conf.author,
                publisher=self.conf.publisher,
                name=self.conf.name,
                tags=";".join(self.conf.tags),
            )
            .config_nbworkers(self.conf.nb_threads)
            .start()
        )

        succeeded = False
        try:
            self.add_favicon()
            self.creator.add_item_for(
                path="home", title="Home", content="<h1>Home</h1>", mimetype="text/html"
            )
            logger.info("Generating Users pages and recording details in DB")

            database = get_database(self.conf)
            user_gen = UserGenerator(
                conf=self.conf,
                creator=self.creator,
                creator_lock=self.creator_lock,
                executor=executor,
                database=database,
            )
            user_gen.run()
            logger.info("Users step done")

            logger.info("Generating Posts pages and recording tag-questions in DB")
            post_gen = PostGenerator(
                conf=self.conf,
                creator=self.creator,
                creator_lock=self.creator_lock,
                executor=executor,
                database=database,
            )
            post_gen.run()
            logger.info("Posts step done")

            logger.info("Generating Tags pages")
            tag_gen = TagGenerator(
                conf=self.conf,
                creator=self.creator,
                creator_lock=self.creator_lock,
                executor=executor,
                database=database,
            )
            tag_gen.run()
            logger.info("Tags step done")

            database.teardown()
            database.remove()

            executor.shutdown()

        except KeyboardInterrupt:
            self.creator.can_finish = False
            logger.error("KeyboardInterrupt, exiting.")
        except Exception as exc:
            # request Creator not to create a ZIM file on finish
            self.creator.can_finish = False
            logger.error(f"Interrupting process due to error: {exc}")
            logger.exception(exc)
        finally:
            if succeeded:
                logger.info("Finishing ZIM file…")
            # we need to release libzim's resources.
            # currently does nothing but crash if can_finish=False but that's awaiting
            # impl. at libkiwix level
            with self.creator_lock:
                self.creator.finish()
            if succeeded:
                logger.info("Zim finished")
