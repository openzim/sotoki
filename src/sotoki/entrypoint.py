#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import os
from pathlib import Path
import sys
import argparse

from cli_formatter.table_builder import TableBuilderClassic

from .constants import NAME, SCRAPER
from .utils.shared import Global, logger


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

    metadata = parser.add_argument_group("Metadata")

    parser.add_argument(
        "--name",
        help="ZIM name. Used as identifier and filename (date will be appended). "
        "Constructed from domain if not supplied",
        required=False,
    )

    metadata.add_argument(
        "--title",
        help="Title for your ZIM, no longer than 30 chars",
        required=True,
    )

    metadata.add_argument(
        "--description",
        help="Description for your ZIM, no longer than 80 chars",
        required=True,
    )

    metadata.add_argument(
        "--long-description",
        help="Long description for your ZIM, no longer than 4000 chars",
        required=False,
    )

    metadata.add_argument(
        "--favicon",
        help="URL/path to ZIM illustration ; fallbacks to a online icon if not provided",
    )

    metadata.add_argument(
        "--creator",
        help="Name of content creator. “Stack Exchange” otherwise",
        dest="author",
    )

    metadata.add_argument(
        "-p",
        "--publisher",
        help="Custom publisher name (ZIM metadata). “openZIM” otherwise"
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
        dest="mirror",
        required=True
    )

    advanced.add_argument(
        "--redis-url",
        help="Redis URL to use as database. "
        "Defaults to the REDIS_URL environment variable if set, otherwise to redis://localhost:6379. "
        "Use redis://user:pass@host:port/db for TCP connections, or "
        "unix:///path/to/redis.sock?db=dbnum for Unix socket connections.",
        default=os.getenv("REDIS_URL","redis://localhost:6379"),
        dest="redis_url",
    )

    advanced.add_argument(
        "--debug", help="Enable verbose output", action="store_true", default=False
    )

    advanced.add_argument(
        "--stats-filename",
        help="Path to store the progress JSON file to.",
        dest="stats_filename",
    )

    advanced.add_argument("--prepare-only", action="store_true", dest="prepare_only")

    advanced.add_argument(
        "--keep",
        help="Don't remove build folder on start (debug/devel)",
        default=False,
        action="store_true",
        dest="keep_build_dir",
    )

    advanced.add_argument(
        "--keep-redis",
        help="Don't flush redis DB on exit. Useful to debug redis content "
        "or to save time. FLUSHDB takes time while restarting redis process is faster.",
        default=False,
        action="store_true",
        dest="keep_redis",
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

    advanced.add_argument(
        "--defrag-redis",
        help="Restart Redis after Users cleanup to remove fragmentation. "
        "On large domains, redis fragmentation can represent 25%% (several GB) of RAM. "
        "This initiate a SAVE once DB is filled, then restart redis so that "
        "it will restore the dump without fragmentation. "
        "Expects “service” string as param to restart using `service` command (linux) "
        "or brew (macos). If your redis-server is started differently, pass it a redis "
        "PID or an `ENV:` prefixed-environ name containing PID and place a "
        "`redis-restart` named script (taking PID as arg) in PATH",
        dest="defrag_redis",
    )

    advanced.add_argument(
        "--shell",
        help="Initialize context then open a shell (developers only). Requires ipython",
        default=False,
        action="store_true",
        dest="open_shell",
    )

    advanced.add_argument(
        "--dev-skip-tags-meta",
        help="Dev only. don't run tag metadata. assumes redis and dumps",
        default=False,
        action="store_true",
        dest="skip_tags_meta",
    )

    advanced.add_argument(
        "--dev-skip-questions-meta",
        help="Dev only. don't run questions first-pass. assumes redis and dumps",
        default=False,
        action="store_true",
        dest="skip_questions_meta",
    )

    advanced.add_argument(
        "--dev-skip-users",
        help="Dev only. don't read users file. assumes redis and dumps",
        default=False,
        action="store_true",
        dest="skip_users",
    )

    parser.add_argument(
        "--version",
        help="Display scraper version and exit",
        action="version",
        version=SCRAPER,
    )

    args = parser.parse_args()
    Global.set_debug(args.debug)

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
