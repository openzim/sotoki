#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
import sys
import argparse

from cli_formatter.table_builder import TableBuilderClassic

from .constants import NAME, SCRAPER, getLogger, setDebug
from .utils.sites import get_all_sites


class ListAllAction(argparse.Action):
    """argparse Action to list StackExchange domains and exit"""

    def __init__(
        self,
        option_strings,
        dest=argparse.SUPPRESS,
        default=argparse.SUPPRESS,
        help="Simply print the list of available domains and exit",
    ):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        def to_row(site):
            url = site.get("@Url", "").replace("https://", "")
            nb_questions = int(site.get("@TotalQuestions", 0))
            return (url, site.get("@Name"), "{:,}".format(nb_questions))

        builder = TableBuilderClassic()
        formatter = parser._get_formatter()
        formatter.add_text(
            builder.build_table(
                header=["Domain", "Name", "Nb. Questions"],
                data=sorted(
                    [to_row(site) for site in get_all_sites()], key=lambda r: r[0]
                ),
            ),
        )
        parser._print_message(formatter.format_help(), sys.stdout)
        parser.exit()


def main():
    parser = argparse.ArgumentParser(
        prog=NAME,
        description="Scraper to create ZIM files from Stack Exchange dumps",
    )

    parser.add_argument(
        "-d",
        "--domain",
        help="Domain name from StackExchange to scrape. Use --list-all for values",
        required=True,
    )

    parser.add_argument("-l", "--list-all", action=ListAllAction)
    # parser.add_argument("--sorted-by")

    metadata = parser.add_argument_group("Metadata")

    parser.add_argument(
        "--name",
        help="ZIM name. Used as identifier and filename (date will be appended). "
        "Constructed from domain if not supplied",
        required=False,
    )

    metadata.add_argument(
        "--title",
        help="Custom title for your ZIM. Site name otherwise",
    )

    metadata.add_argument(
        "--description",
        help="Custom description for your ZIM. Site tagline otherwise",
    )

    metadata.add_argument(
        "--favicon",
        help="URL/path for Zim Illustration. Site square logo otherwise",
    )

    metadata.add_argument(
        "--creator",
        help="Name of content creator. “Stack Exchange” otherwise",
        dest="author",
    )

    metadata.add_argument(
        "-p",
        "--publisher",
        help="Custom publisher name (ZIM metadata). “OpenZIM” otherwise",
        default="Kiwix",
    )
    metadata.add_argument(
        "--tag",
        help="Add tag to the ZIM file. "
        "category:stack_exchange and stack_exchange added automatically",
        default=["_category:stack_exchange", "stack_exchange"],
        action="append",
    )

    censored = parser.add_argument_group(
        "Censorship",
        "Options to strip-out some content for censorship or optimization reasons",
    )

    censored.add_argument(
        "--without-images",
        action="store_true",
        default=False,
        help="Don't include images (in-post images, user icons). Faster.",
    )
    censored.add_argument(
        "--without-user-profiles",
        action="store_true",
        default=False,
        help="Don't include user profile pages. Faster",
    )
    censored.add_argument(
        "--without-user-identicons",
        action="store_true",
        default=False,
        help="Don't include user's profile pictures. "
        "Replaced by generated ones. Faster",
    )
    censored.add_argument(
        "--without-external-links",
        action="store_true",
        default=False,
        help="Remove all external links from posts and user profiles. "
        "Link text is kept but not the address. Slower",
    )
    censored.add_argument(
        "--without-unanswered",
        action="store_true",
        default=False,
        help="Don't include posts that have zero answer. Faster",
    )
    censored.add_argument(
        "--without-users-links",
        action="store_true",
        default=False,
        help="Remove “user links” completely. Remove both url and text "
        "for a selected list of “social” websites. Slower",
    )
    censored.add_argument(
        "--without-names",
        action="store_true",
        default=False,
        help="Replace usernames in posts with generated ones",
    )
    censored.add_argument(
        "--censor-words-list",
        dest="censor_words_list",
        help="URL or path to a text file "
        "containing one word per line. Each of them to be removed from all content. "
        "Very slow. Sample list: https://raw.githubusercontent.com/RobertJGabriel/"
        "Google-profanity-words/master/list.txt",
    )

    advanced = parser.add_argument_group("Advanced")

    advanced.add_argument(
        "--output",
        help="Output folder for ZIM file",
        default="/output",
        dest="_output_dir",
    )

    advanced.add_argument(
        "--threads",
        help="Number of threads to use to handle tasks concurrently. "
        "Increase to speed-up I/O operations (disk, network). Default: 1",
        default=1,
        type=int,
        dest="nb_threads",
    )

    advanced.add_argument(
        "--tmp-dir",
        help="Path to create temp folder in. Used for building ZIM file. "
        "Receives all data (storage space). Defaults to TMPDIR or CWD",
        default=os.getenv("TMPDIR", "."),
        dest="_tmp_dir",
    )

    advanced.add_argument(
        "--zim-file",
        help="ZIM file name (based on --name if not provided)",
        dest="fname",
    )

    advanced.add_argument(
        "--optimization-cache",
        help="URL with credentials to S3 for use as optimization cache",
        dest="s3_url_with_credentials",
    )

    advanced.add_argument(
        "--mirror",
        help="URL from which to download compressed XML dumps",
        default="https://archive.org/download/stackexchange/",
        dest="mirror",
    )

    advanced.add_argument(
        "--redis-url",
        help="Redis URL to use as database. "
        "Must be redis://user?:pass?@host:port/dbnum. "
        "Use file:///path/to/redis.sock?db=dbnum for sockets",
        default="redis://localhost:6379",
        dest="_redis_url",
    )

    advanced.add_argument(
        "--debug", help="Enable verbose output", action="store_true", default=False
    )

    advanced.add_argument("--statsFilename")

    advanced.add_argument("--prepare-only", action="store_true", dest="prepare_only")

    advanced.add_argument(
        "--keep",
        help="Don't remove build folder on start (debug/devel)",
        default=False,
        action="store_true",
        dest="keep_build_dir",
    )

    advanced.add_argument(
        "--keep-intermediates",
        help="Don't remove intermediate files during prepare step (debug/devel)",
        default=False,
        action="store_true",
        dest="keep_intermediate_files",
    )

    advanced.add_argument(
        "--build-in-tmp",
        help="Use --tmp-dir value as workdir. Otherwise, a unique sub-folder "
        "is created inside it. Useful to reuse downloaded files (debug/devel)",
        default=False,
        action="store_true",
        dest="build_dir_is_tmp_dir",
    )

    parser.add_argument(
        "--version",
        help="Display scraper version and exit",
        action="version",
        version=SCRAPER,
    )

    args = parser.parse_args()
    setDebug(args.debug)
    logger = getLogger()

    from .scraper import StackExchangeToZim

    try:
        scraper = StackExchangeToZim(**dict(args._get_kwargs()))
        sys.exit(scraper.run())
    except Exception as exc:
        logger.error(f"FAILED. An error occurred: {exc}")
        if args.debug:
            logger.exception(exc)
        raise SystemExit(1)
    finally:
        try:
            scraper.cleanup()
        except UnboundLocalError:
            pass


if __name__ == "__main__":
    main()
