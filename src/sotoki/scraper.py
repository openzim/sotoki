#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import shutil
import pathlib
import datetime

from zimscraperlib.zim.items import URLItem
from zimscraperlib.inputs import handle_user_provided_file
from zimscraperlib.image.convertion import convert_image
from zimscraperlib.image.transformation import resize_image

from .constants import (
    Sotoconf,
    ROOT_DIR,
    NB_PAGINATED_QUESTIONS_PER_TAG,
    NB_USERS_PER_PAGE,
    NB_USERS_PAGES,
    NB_QUESTIONS_PER_PAGE,
    NB_QUESTIONS_PAGES,
)
from .archives import ArchiveManager
from .utils.s3 import setup_s3_and_check_credentials
from .utils.sites import get_site
from .utils.shared import Global, logger
from .users import UserGenerator
from .posts import PostGenerator, PostFirstPasser
from .tags import TagGenerator, TagFinder, TagExcerptRecorder, TagDescriptionRecorder


class StackExchangeToZim:
    def __init__(self, **kwargs):

        Global.conf = Sotoconf(**kwargs)
        for option in Global.conf.required:
            if getattr(Global.conf, option) is None:
                raise ValueError(f"Missing parameter `{option}`")

    @property
    def conf(self):
        return Global.conf

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

        if self.conf.censor_words_list:
            words_list_fpath = self.build_dir.joinpath("words.list")
            handle_user_provided_file(
                source=self.conf.censor_words_list, dest=words_list_fpath
            )

        period = datetime.datetime.now().strftime("%Y-%m")
        if self.conf.fname:
            # make sure we were given a filename and not a path
            self.conf.fname = pathlib.Path(self.conf.fname.format(period=period))
            if pathlib.Path(self.conf.fname.name) != self.conf.fname:
                raise ValueError(f"filename is not a filename: {self.conf.fname}")
        else:
            self.conf.fname = f"{self.conf.name}_{period}.zim"

        if not self.conf.title:
            self.conf.title = Global.site["LongName"]
        self.conf.title = self.conf.title.strip()

        if not self.conf.description:
            self.conf.description = Global.site["Tagline"]
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

    def add_illustrations(self):
        src_illus_fpath = self.build_dir / "illustration"

        # if user provided a custom favicon, retrieve that
        if not self.conf.favicon:
            self.conf.favicon = Global.site["BadgeIconUrl"]
        handle_user_provided_file(source=self.conf.favicon, dest=src_illus_fpath)

        # convert to PNG (might already be PNG but it's OK)
        illus_fpath = src_illus_fpath.with_suffix(".png")
        convert_image(src_illus_fpath, illus_fpath)

        # resize to appropriate size (ZIM uses 48x48 so we double for retina)
        for size in (96, 48):
            resize_image(illus_fpath, width=size, height=size, method="thumbnail")
            with open(illus_fpath, "rb") as fh:
                Global.creator.add_illustration(size, fh.read())

        # download and add actual favicon (ICO file)
        favicon_fpath = self.build_dir / "favicon.ico"
        handle_user_provided_file(source=Global.site["IconUrl"], dest=favicon_fpath)
        Global.creator.add_item_for("favicon.ico", fpath=favicon_fpath, is_front=False)

        # download apple-touch-icon
        Global.creator.add_item(
            URLItem(url=Global.site["BadgeIconUrl"], path="apple-touch-icon.png")
        )

    def add_assets(self):
        assets_root = ROOT_DIR.joinpath("assets")
        with Global.lock:
            for fpath in assets_root.glob("**/*"):
                if not fpath.is_file() or fpath.name == "README":
                    continue
                logger.debug(str(fpath.relative_to(assets_root)))
                Global.creator.add_item_for(
                    path=str(fpath.relative_to(assets_root)),
                    fpath=fpath,
                    is_front=False,
                )

        # download primary|secondary.css from target
        assets_base = Global.site["IconUrl"].rsplit("/", 2)[0]
        for css_fname in ("primary.css", "secondary.css"):
            logger.debug(f"adding {css_fname}")
            Global.creator.add_item(
                URLItem(
                    url=f"{assets_base}/{css_fname}", path=f"static/css/{css_fname}"
                )
            )

    def run(self):
        s3_storage = (
            setup_s3_and_check_credentials(self.conf.s3_url_with_credentials)
            if self.conf.s3_url_with_credentials
            else None
        )

        s3_msg = (
            f"  using cache: {s3_storage.url.netloc} "
            f"with bucket: {s3_storage.bucket_name}"
            if s3_storage
            else ""
        )
        logger.info(
            f"Starting scraper with:\n"
            f"  domain: {self.domain}\n"
            f"  lang: {self.conf.iso_lang_1} ({self.conf.iso_lang_3})\n"
            f"  build_dir: {self.build_dir}\n"
            f"  output_dir: {self.conf.output_dir}\n"
            f"{s3_msg}"
        )

        logger.debug("Fetching site details…")
        Global.init(get_site(self.domain))
        if not Global.site:
            logger.critical(
                f"Couldn't fetch detail for {self.domain}. Please check "
                "that it's a supported domain using --list-all."
            )
            return 1

        self.sanitize_inputs()

        logger.info("XML Dumps preparation")
        ark_manager = ArchiveManager()
        ark_manager.check_and_prepare_dumps()
        self.conf.dump_date = ark_manager.get_dump_date()
        del ark_manager

        if self.conf.prepare_only:
            logger.info("Requested preparation only; exiting")
            return

        Global.progresser.print()
        return self.start()

    def start(self):

        try:
            Global.setup()
        except Exception as exc:
            if isinstance(exc, Global.DatabaseException):
                logger.critical("Unable to initialize database. Check --redis-url")
            if Global.debug:
                logger.exception(exc)
            else:
                logger.error(str(exc))
            return 1

        # debug/devel mode to open a shell with the inited context
        if Global.conf.open_shell:
            try:
                from IPython import start_ipython
            except ImportError:
                logger.critical("You need ipython to use --shell")
                raise

            logger.debug(
                "Dropping into an ipython shell.\n"
                "Import `Global` var to retrieve context: "
                "from sotoki.utils.shared import Global\n"
                "Global.creator is ready but not started.\n"
                "Scraper execution will be halted once you exit the shell.\n"
            )

            start_ipython(argv=[])

            raise RuntimeError("End of debug shell session")

        Global.creator.start()

        try:
            self.add_illustrations()
            self.add_assets()

            self.process_tags_metadata()

            self.process_questions_metadata()

            self.process_indiv_users_pages()

            self.process_questions()

            self.process_tags()

            self.process_pages_lists()

            Global.executor.shutdown()
            Global.img_executor.shutdown()

            Global.database.teardown()
            Global.database.remove()
        except Exception as exc:
            # request Creator not to create a ZIM file on finish
            Global.creator.can_finish = False
            if isinstance(exc, KeyboardInterrupt):
                logger.error("KeyboardInterrupt, exiting.")
            else:
                logger.error(f"Interrupting process due to error: {exc}")
                logger.exception(exc)
            Global.imager.abort()
            Global.executor.shutdown(wait=False)
            Global.img_executor.shutdown(wait=False)
            return 1
        else:
            logger.info("Finishing ZIM file…")
            # we need to release libzim's resources.
            # currently does nothing but crash if can_finish=False but that's awaiting
            # impl. at libkiwix level
            with Global.lock:
                Global.creator.finish()
            logger.info(
                f"Finished Zim {Global.creator.filename.name} "
                f"in {Global.creator.filename.parent}"
            )
        finally:
            Global.progresser.print()

    def process_tags_metadata(self):
        # First, walk through Tags and record tags details in DB
        # Then walk through excerpts and record those in DB
        # Then do the same with descriptions
        # Clear the matching that was required for Excerpt/Desc filtering-in
        logger.info("Recording Tag metadata to Database")
        Global.progresser.start(
            Global.progresser.TAGS_METADATA_STEP,
            nb_total=int(Global.site["TotalTags"]) * 3,
        )
        if not self.conf.skip_tags_meta:
            TagFinder().run()
        Global.database.ack_tags_ids()
        if not self.conf.skip_tags_meta:
            TagExcerptRecorder().run()
            TagDescriptionRecorder().run()
        Global.database.clear_tags_mapping()
        Global.database.purge()

    def process_questions_metadata(self):
        # We walk through all Posts a first time to record question in DB
        # list of users that had interactions
        # list of PostId for all questions
        # list of PostId for all questions of all tags (incr. update)
        # Details for all questions: date, owner, title, excerpt, has_accepted
        logger.info("Recording questions metadata to Database")
        Global.progresser.start(
            Global.progresser.QUESTIONS_METADATA_STEP,
            nb_total=int(Global.site["TotalQuestions"]),
        )
        if not self.conf.skip_questions_meta:
            PostFirstPasser().run()
        Global.database.ack_users_ids()
        Global.database.clear_extra_tags_questions_list(NB_PAGINATED_QUESTIONS_PER_TAG)
        Global.database.purge()

    def process_indiv_users_pages(self):
        # We walk through all Users and skip all those without interactions
        # Others store basic details in Database
        # Then we create a page in Zim for each user
        # Eventually, we sort our list of users by Reputation
        logger.info("Generating individual Users pages")
        Global.progresser.start(
            Global.progresser.USERS_STEP,
            nb_total=int(Global.site["TotalUsers"]),
        )
        if not self.conf.skip_users:
            UserGenerator().run()
        logger.debug("Cleaning-up users list")
        Global.database.cleanup_users()
        Global.database.purge()
        if self.conf.redis_pid:
            Global.database.defrag_external()

    def process_questions(self):
        # We walk again through all Posts, this time to create indiv pages in Zim
        # for each.
        logger.info("Generating Questions pages")
        Global.progresser.start(
            Global.progresser.QUESTIONS_STEP,
            nb_total=int(Global.site["TotalQuestions"]),
        )
        PostGenerator().run()
        Global.database.purge()

    def process_tags(self):
        # We walk on Tags again, this time creating indiv pages for each Tag.
        # Each tag is actually a number of paginated pages with a list of questions
        logger.info("Generating Tags pages")
        Global.progresser.start(
            Global.progresser.TAGS_STEP, nb_total=int(Global.site["TotalTags"])
        )
        TagGenerator().run()

    def process_pages_lists(self):
        # compute expected number of items to add to Zim (for progress)
        nb_user_pages = Global.database.nb_users / NB_USERS_PER_PAGE
        nb_user_pages = int(
            nb_user_pages if nb_user_pages < NB_USERS_PAGES else NB_USERS_PAGES
        )
        nb_question_pages = int(
            Global.database.get_set_count(Global.database.questions_key())
            / NB_QUESTIONS_PER_PAGE
        )
        nb_question_pages = (
            nb_question_pages
            if nb_question_pages < NB_QUESTIONS_PAGES
            else NB_QUESTIONS_PAGES
        )
        Global.progresser.start(
            Global.progresser.LISTS_STEP,
            nb_total=nb_user_pages + nb_question_pages + 1,
        )

        logger.info("Generating Users page")
        UserGenerator().generate_users_page()
        Global.progresser.update(incr=nb_user_pages)
        logger.info(".. done")

        Global.progresser.print()

        # build home page in ZIM using questions list
        logger.info("Generating Questions page (homepage)")

        PostGenerator().generate_questions_page()
        Global.progresser.update(incr=nb_question_pages)

        with Global.lock:
            Global.creator.add_item_for(
                path="about",
                title="About",
                content=Global.renderer.get_about_page(),
                mimetype="text/html",
                is_front=True,
            )
            Global.creator.add_redirect(path="", target_path="questions")
        Global.progresser.update(incr=True)
        logger.info(".. done")

        Global.progresser.print()
