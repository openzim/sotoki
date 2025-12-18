#!/usr/bin/env python3

import datetime
import logging
import pathlib
import re
import shutil
import tempfile
from urllib.parse import urlparse

import bs4
import requests
from kiwixstorage import KiwixStorage
from zimscraperlib.i18n import NotFoundError, get_language
from zimscraperlib.image.conversion import convert_image
from zimscraperlib.image.transformation import resize_image
from zimscraperlib.inputs import handle_user_provided_file
from zimscraperlib.zim import Creator, metadata

from sotoki.archives import ArchiveManager
from sotoki.constants import (
    HTTP_REQUEST_TIMEOUT,
    NAME,
    NB_PAGINATED_QUESTIONS_PER_TAG,
    NB_QUESTIONS_PAGES,
    NB_QUESTIONS_PER_PAGE,
    NB_USERS_PAGES,
    NB_USERS_PER_PAGE,
    ROOT_DIR,
    VERSION,
)
from sotoki.css import process_css
from sotoki.models import SiteDetails
from sotoki.posts import PostFirstPasser, PostGenerator
from sotoki.renderer import Renderer
from sotoki.tags import (
    TagDescriptionRecorder,
    TagExcerptRecorder,
    TagFinder,
    TagGenerator,
)
from sotoki.users import UserGenerator
from sotoki.utils.database.posts import PostsDatabase
from sotoki.utils.database.redisdb import RedisDatabase
from sotoki.utils.database.tags import TagsDatabase
from sotoki.utils.database.users import UsersDatabase
from sotoki.utils.exceptions import DatabaseError
from sotoki.utils.executor import SotokiExecutor
from sotoki.utils.html import Rewriter
from sotoki.utils.imager import Imager
from sotoki.utils.misc import web_backoff
from sotoki.utils.progress import Progresser
from sotoki.utils.s3 import setup_s3_and_check_credentials
from sotoki.utils.shared import context, logger, shared


class StackExchangeToZim:
    def __init__(self):
        level = logging.DEBUG if context.debug else logging.INFO
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)

        # dumps are named after unfixed domains, so we need to keep that input
        shared.dump_domain = context.domain
        self._get_site_details()
        # real domain as found online after potential redirection for fixed domains
        shared.online_domain = shared.site_details.domain
        self.iso_langs_1, self.iso_langs_3 = self.langs_for_domain(shared.online_domain)
        self.flavour = "nopic" if context.without_images else ""
        lang_in_name = self.iso_langs_1[0] if len(self.iso_langs_1) == 1 else "mul"
        context.name = (
            context.name or f"{shared.online_domain}_{lang_in_name}_all_{self.flavour}"
            if self.flavour
            else f"{shared.online_domain}_{lang_in_name}_all"
        )
        context.output_dir.mkdir(parents=True, exist_ok=True)
        context.tmp_dir.mkdir(parents=True, exist_ok=True)
        if context.build_dir_is_tmp_dir:
            shared.build_dir = context.tmp_dir
        else:
            shared.build_dir = pathlib.Path(
                tempfile.mkdtemp(prefix=f"{shared.online_domain}_", dir=context.tmp_dir)
            )
        if context.stats_filename:
            context.stats_filename.parent.mkdir(parents=True, exist_ok=True)

    @web_backoff(base=10, max_tries=10)
    def _get_site_details(self):
        resp = requests.get(f"https://{context.domain}", timeout=HTTP_REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = bs4.BeautifulSoup(resp.text, "lxml")
        domain = urlparse(resp.url).netloc
        title_tag = soup.title
        if not title_tag or not title_tag.string:
            raise Exception("Failed to extract site title from homepage")
        site_title = title_tag.string
        if "stackexchange" in context.domain:
            # For "regular" stackexchange domains, use the whole header
            header_tag = soup.find("header", class_="site-header")
            if not header_tag:
                raise Exception("Failed to extract header HTML from homepage")
            header_html = str(header_tag)
        else:
            # For stackoverflow domains, build custom header with logo since there is
            # no real header on these domains
            a_header_tag = soup.find("a", class_="s-topbar--logo")
            if not a_header_tag:
                raise Exception("Failed to extract header HTML from homepage")
            header_html = f"""
<header class="s-topbar z-minus-1">
	<div class="s-topbar--container">
        {a_header_tag}
	</div>
</header>
"""
        primary_css_tag = soup.find(
            "link", href=lambda href: bool(href and "primary.css" in href)
        )
        if not primary_css_tag or not primary_css_tag.get("href"):
            raise Exception("Failed to extract primary CSS from homepage")
        primary_css = str(primary_css_tag["href"])
        small_favicon_tag = soup.find("link", rel="icon")
        if not small_favicon_tag or not small_favicon_tag.get("href"):
            raise Exception("Failed to extract small favicon URL from homepage")
        small_favicon = str(small_favicon_tag["href"])
        big_favicon_tag = soup.find("link", rel="apple-touch-icon")
        if not big_favicon_tag or not big_favicon_tag.get("href"):
            raise Exception("Failed to extract big favicon URL from homepage")
        big_favicon = str(big_favicon_tag["href"])
        shared.site_details = SiteDetails(
            mathjax='<script type="text/x-mathjax-config">' in resp.text,
            highlight='"styleCodeWithHighlightjs":true' in resp.text,
            domain=domain,
            site_title=site_title,
            primary_css=primary_css,
            secondary_css=primary_css.replace("primary", "secondary"),
            small_favicon=small_favicon,
            big_favicon=big_favicon,
            header_html=header_html,
        )

    def langs_for_domain(self, domain: str) -> tuple[list[str], list[str]]:
        """(ISO-639-1 lang codes, ISO-639-3 lang codes) for a domain"""
        iso_langs_1, iso_langs_3 = ["en"], ["eng"]
        match = re.match(
            r"^(?P<lang>[a-z]+)\.(stackexchange|stackoverflow)\.com$", domain
        )
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
                    lang = get_language(so_code)
                    if not lang.iso_639_1 or not lang.iso_639_3:
                        raise NotFoundError("Might be an abbreviation")
                    if lang.iso_639_1 not in iso_langs_1:
                        iso_langs_1.append(lang.iso_639_1)
                    if lang.iso_639_3 not in iso_langs_3:
                        iso_langs_3.append(lang.iso_639_3)
                except NotFoundError:
                    ...
        return iso_langs_1, iso_langs_3

    @property
    def tags(self) -> list[str]:
        return list(
            {
                *context.tags,
                *[
                    "_category:stack_exchange",
                    "stack_exchange",
                    "_videos:no",
                    "_details:no",
                ],
                *(["_pictures:no"] if context.without_images else []),
            }
        )

    def cleanup(self):
        """Remove temp files and release resources before exiting"""
        if not context.keep_build_dir:
            logger.debug(f"Removing {shared.build_dir}")
            shutil.rmtree(shared.build_dir, ignore_errors=True)

    def sanitize_inputs(self):
        """input & metadata sanitation"""

        if context.censor_words_list:
            words_list_fpath = shared.build_dir.joinpath("words.list")
            handle_user_provided_file(
                source=context.censor_words_list, dest=words_list_fpath
            )

        period = datetime.datetime.now(tz=datetime.UTC).strftime("%Y-%m")
        if context.fname:
            # make sure we were given a filename and not a path
            self.fname = pathlib.Path(context.fname.format(period=period))
            if pathlib.Path(context.fname) != self.fname:
                raise ValueError(f"--zim-file is not a filename: {context.fname}")
        else:
            self.fname = pathlib.Path(f"{context.name}_{period}.zim")

    def add_illustrations(self):
        # download and add actual favicon (ICO file)
        small_favicon_fpath = shared.build_dir / "favicon.ico"
        handle_user_provided_file(
            source=shared.site_details.small_favicon, dest=small_favicon_fpath
        )
        shared.creator.add_item_for(
            "favicon.ico", fpath=small_favicon_fpath, is_front=False
        )

        # download apple-touch-icon
        big_favicon_fpath = shared.build_dir / "apple-touch-icon.png"
        handle_user_provided_file(
            source=shared.site_details.big_favicon, dest=big_favicon_fpath
        )
        shared.creator.add_item_for(
            "apple-touch-icon.png", fpath=big_favicon_fpath, is_front=False
        )

    def add_assets(self):
        assets_root = ROOT_DIR.joinpath("assets")
        with shared.lock:
            for fpath in assets_root.glob("**/*"):
                if not fpath.is_file() or fpath.name == "README":
                    continue
                logger.debug(str(fpath.relative_to(assets_root)))
                shared.creator.add_item_for(
                    path=str(fpath.relative_to(assets_root)),
                    fpath=fpath,
                    is_front=False,
                )

        # download primary|secondary.css from target
        process_css(shared.site_details.primary_css, "primary.css")
        process_css(shared.site_details.secondary_css, "secondary.css")

    def run(self):

        redis_url = urlparse(context.redis_url)
        if redis_url and redis_url.scheme not in ("unix", "redis"):
            raise ValueError(
                f"Unknown scheme `{redis_url.scheme}` for redis. "
                "Use redis:// or unix://"
            )

        # shell implies debug
        if context.open_shell:
            context.debug = True

        try:
            shared.database = RedisDatabase(initialize=True)
        except Exception as exc:
            raise DatabaseError(exc) from exc

        # Individual classes to handle each object type storage in Redis
        shared.tagsdatabase = TagsDatabase()
        shared.postsdatabase = PostsDatabase()
        shared.usersdatabase = UsersDatabase()

        # manipulate S3 objects
        shared.s3_storage = (
            KiwixStorage(context.s3_url_with_credentials)
            if context.s3_url_with_credentials
            else None
        )

        # mostly transforms HTML and sends to zim.
        # tests show no speed improv. beyond 3 workers.
        shared.executor = SotokiExecutor(
            queue_size=10,
            nb_workers=3,
        )

        # images handled on a different queue.
        # mostly network I/O to retrieve and/or upload image.
        # if not in S3 bucket, resize/optimize webp image
        # we should consider using coroutines instead of threads
        shared.img_executor = SotokiExecutor(
            queue_size=200,
            nb_workers=10,
            prefix="IMG-T-",
        )

        shared.imager = Imager()
        shared.rewriter = Rewriter()
        shared.renderer = Renderer()

        s3_storage = (
            setup_s3_and_check_credentials(context.s3_url_with_credentials)
            if context.s3_url_with_credentials
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
            f"  dump domain: {shared.dump_domain}\n"
            f"  online domain: {shared.online_domain}\n"
            f"  lang: {self.iso_langs_1} ({self.iso_langs_3})\n"
            f"  build_dir: {shared.build_dir}\n"
            f"  output_dir: {context.output_dir}\n"
            f"{s3_msg}"
        )

        shared.progresser = Progresser(shared.total_questions)

        self.sanitize_inputs()

        # load illustration data, required for creator metadata setup
        illus_nosuffix_fpath = shared.build_dir / "illustration"
        handle_user_provided_file(
            source=context.favicon or shared.site_details.big_favicon,
            dest=illus_nosuffix_fpath,
        )

        # convert to PNG (might already be PNG but it's OK)
        illus_fpath = illus_nosuffix_fpath.with_suffix(".png")
        convert_image(illus_nosuffix_fpath, illus_fpath)

        # resize to appropriate size
        resize_image(illus_fpath, width=48, height=48, method="thumbnail")
        with open(illus_fpath, "rb") as fh:
            illustration_data = fh.read()

        if not context.name:
            raise Exception(f"ZIM name cannot be None or empty: '{context.name}'")

        shared.creator = (
            Creator(
                filename=context.output_dir.joinpath(self.fname),
                main_path="questions",
            )
            .config_metadata(
                metadata.StandardMetadataList(
                    Name=metadata.NameMetadata(context.name),
                    Language=metadata.LanguageMetadata(
                        self.iso_langs_3
                    ),  # python-scraperlib needs language list as a single string
                    Title=metadata.TitleMetadata(context.title),
                    Description=metadata.DescriptionMetadata(context.description),
                    LongDescription=(
                        metadata.LongDescriptionMetadata(context.long_description)
                        if context.long_description
                        else None
                    ),
                    Creator=metadata.CreatorMetadata(context.creator),
                    Publisher=metadata.PublisherMetadata(context.publisher),
                    Date=metadata.DateMetadata(datetime.date.today()),
                    Illustration_48x48_at_1=metadata.DefaultIllustrationMetadata(
                        illustration_data
                    ),
                    Tags=metadata.TagsMetadata(self.tags) if self.tags else None,
                    Scraper=metadata.ScraperMetadata(f"{NAME} v{VERSION}"),
                    Flavour=(
                        metadata.FlavourMetadata(self.flavour) if self.flavour else None
                    ),
                    # Source=,
                    License=metadata.LicenseMetadata(
                        "CC-BY-SA"
                    ),  # as per stack exchange ToS, see about page in ZIM
                    # Relation=,
                )
            )
            .config_verbose(context.debug)
        )

        logger.info("XML Dumps preparation")
        ark_manager = ArchiveManager()
        ark_manager.check_and_prepare_dumps()
        del ark_manager

        if context.prepare_only:
            logger.info("Requested preparation only; exiting")
            return

        shared.progresser.print()
        return self.start()

    def start(self):

        # debug/devel mode to open a shell with the inited context
        if context.open_shell:
            try:
                from IPython import (  # noqa: PLC0415  # pyright: ignore[reportMissingImports]
                    start_ipython,
                )
            except ImportError:
                logger.critical("You need ipython to use --shell")
                raise

            logger.debug(
                "Dropping into an ipython shell.\n"
                "Import `Global` var to retrieve context: "
                "from sotoki.utils.shared import Global\n"
                "shared.creator is ready but not started.\n"
                "Scraper execution will be halted once you exit the shell.\n"
            )

            start_ipython(argv=[])

            raise RuntimeError("End of debug shell session")

        shared.creator.start()

        try:
            self.add_illustrations()
            self.add_assets()

            self.process_tags_metadata()

            self.process_questions_metadata()

            self.process_indiv_users_pages()

            self.process_questions()

            self.process_tags()

            self.process_pages_lists()

            shared.imager.process_images()
            shared.img_executor.join()

            shared.executor.shutdown()
            shared.img_executor.shutdown()

            shared.database.teardown()
            shared.database.remove()
        except Exception as exc:
            # request Creator not to create a ZIM file on finish
            shared.creator.can_finish = False
            if isinstance(exc, KeyboardInterrupt):
                logger.error("KeyboardInterrupt, exiting.")
            else:
                logger.error(f"Interrupting process due to error: {exc}")
                logger.exception(exc)
            shared.imager.abort()
            shared.executor.shutdown(wait=False)
            shared.img_executor.shutdown(wait=False)
            return 1
        else:
            logger.info("Finishing ZIM file…")
            # we need to release libzim's resources.
            # currently does nothing but crash if can_finish=False but that's awaiting
            # impl. at libkiwix level
            with shared.lock:
                shared.creator.finish()
            logger.info(
                f"Finished Zim {shared.creator.filename.name} "
                f"in {shared.creator.filename.parent}"
            )
        finally:
            shared.progresser.print()

    def process_tags_metadata(self):
        # First, walk through Tags and record tags details in DB
        # Then walk through excerpts and record those in DB
        # Then do the same with descriptions
        # Clear the matching that was required for Excerpt/Desc filtering-in
        logger.info("Recording Tag metadata to Database")
        shared.progresser.start(
            shared.progresser.TAGS_METADATA_STEP,
            nb_total=shared.total_tags * 3,
        )
        if not context.skip_tags_meta:
            TagFinder().run()
        shared.tagsdatabase.ack_tags_ids()
        if not context.skip_tags_meta:
            TagExcerptRecorder().run()
            TagDescriptionRecorder().run()
        shared.tagsdatabase.clear_tags_mapping()
        shared.database.purge()

    def process_questions_metadata(self):
        # We walk through all Posts a first time to record question in DB
        # list of users that had interactions
        # list of PostId for all questions
        # list of PostId for all questions of all tags (incr. update)
        # Details for all questions: date, owner, title, excerpt, has_accepted
        logger.info("Recording questions metadata to Database")
        shared.progresser.start(
            shared.progresser.QUESTIONS_METADATA_STEP,
            nb_total=shared.total_questions,
        )
        if not context.skip_questions_meta:
            PostFirstPasser().run()
        shared.usersdatabase.ack_users_ids()
        shared.tagsdatabase.clear_extra_tags_questions_list(
            NB_PAGINATED_QUESTIONS_PER_TAG
        )
        shared.database.purge()

    def process_indiv_users_pages(self):
        # We walk through all Users and skip all those without interactions
        # Others store basic details in Database
        # Then we create a page in Zim for each user
        # Eventually, we sort our list of users by Reputation
        logger.info("Generating individual Users pages")
        shared.progresser.start(
            shared.progresser.USERS_STEP,
            nb_total=shared.total_users,
        )
        if not context.skip_users:
            UserGenerator().run()
        logger.debug("Cleaning-up users list")
        shared.usersdatabase.cleanup_users()
        shared.database.purge()
        if context.redis_pid:
            shared.database.defrag_external()

    def process_questions(self):
        # We walk again through all Posts, this time to create indiv pages in Zim
        # for each.
        logger.info("Generating Questions pages")
        shared.progresser.start(
            shared.progresser.QUESTIONS_STEP,
            nb_total=shared.total_questions,
        )
        PostGenerator().run()
        shared.database.purge()

    def process_tags(self):
        # We walk on Tags again, this time creating indiv pages for each Tag.
        # Each tag is actually a number of paginated pages with a list of questions
        logger.info("Generating Tags pages")
        shared.progresser.start(shared.progresser.TAGS_STEP, nb_total=shared.total_tags)
        TagGenerator().run()

    def process_pages_lists(self):
        # compute expected number of items to add to Zim (for progress)
        nb_user_pages = shared.usersdatabase.nb_users / NB_USERS_PER_PAGE
        nb_user_pages = int(
            nb_user_pages if nb_user_pages < NB_USERS_PAGES else NB_USERS_PAGES
        )
        nb_question_pages = int(
            shared.database.get_set_count(shared.postsdatabase.questions_key())
            / NB_QUESTIONS_PER_PAGE
        )
        nb_question_pages = (
            nb_question_pages
            if nb_question_pages < NB_QUESTIONS_PAGES
            else NB_QUESTIONS_PAGES
        )
        shared.progresser.start(
            shared.progresser.LISTS_STEP,
            nb_total=nb_user_pages + nb_question_pages + 1,
        )

        logger.info("Generating Users page")
        UserGenerator().generate_users_page()
        shared.progresser.update(incr=nb_user_pages)
        logger.info(".. done")

        shared.progresser.print()

        # build home page in ZIM using questions list
        logger.info("Generating Questions page (homepage)")

        PostGenerator().generate_questions_page()
        shared.progresser.update(incr=nb_question_pages)

        with shared.lock:
            shared.creator.add_item_for(
                path="about",
                title="About",
                content=shared.renderer.get_about_page(),
                mimetype="text/html",
                is_front=True,
            )
            shared.creator.add_redirect(path="", target_path="questions")
        shared.progresser.update(incr=True)
        logger.info(".. done")

        shared.progresser.print()
