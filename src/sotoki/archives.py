#!/usr/bin/env python

import concurrent.futures as cf

from zimscraperlib.download import save_large_file, stream_file

from sotoki.utils.misc import has_binary
from sotoki.utils.preparation import (
    count_xml_rows,
    merge_posts_with_answers_comments,
    merge_users_with_badges,
)
from sotoki.utils.sevenzip import extract_7z
from sotoki.utils.shared import context, logger, shared


class ArchiveManager:
    """Handle retrieval and processing of StackExchange dump files

    Each website is available as a single 7z archive.

    7z files extracts to a number of XML files. We are interested in a few
    that we need to read and combine (and thus sort).

    Manipulations of the XML files is done in preparation module.

    As this is a lenghty process (several hours for SO) and the output doesn't
    change until next dump (twice a year), this handles reusing existing files"""

    @property
    def dump_parts(self):
        """XML Dump files we're interested in"""
        return ("Badges", "Comments", "PostLinks", "Posts", "Tags", "Users")

    @property
    def archives(self):
        """list of 7z archive files

        Scraper is capable to download multiple archives per domain. This was used for
        stackoverflow.com which was split with one 7z per dump part. This is not the
        case anymore but scraper capability has not been removed for now.
        """
        return [shared.build_dir / f"{shared.dump_domain}.7z"]

    def download_and_extract_archives(self):
        logger.info("Downloading archive(s)…")

        # use wget for downloading 7z files if available
        download = save_large_file if has_binary("wget") else stream_file

        def _run(url, fpath):
            if not fpath.exists():
                logger.info(f"Downloading {fpath.name}")
                download(url, fpath)
            shared.progresser.update(incr=1)

            logger.info(f"Extracting {fpath.name}")
            extract_7z(
                fpath, shared.build_dir, delete_src=not context.keep_intermediate_files
            )
            shared.progresser.update(incr=1)

            # remove other files from ark that we won't need
            for fp in shared.build_dir.iterdir():
                if fp.suffix != ".xml" or fp.stem not in self.dump_parts:
                    fp.unlink()

        futures = {}
        executor = cf.ThreadPoolExecutor(max_workers=len(self.archives))

        for ark in self.archives:
            url = f"{context.mirror}/{ark.name}"
            kwargs = {"url": url, "fpath": ark}
            future = executor.submit(_run, **kwargs)
            futures.update({future: kwargs})

        result = cf.wait(futures.keys(), return_when=cf.FIRST_EXCEPTION)
        executor.shutdown()

        failed = False
        for future in result.done:
            exc = future.exception()
            if exc:
                item = futures.get(future)
                logger.error(
                    f"Error processing {item['fpath'].name}: {exc}" if item else ""
                )
                logger.exception(exc)
                failed = True

        if not failed and result.not_done:
            logger.error(
                "Some not_done futures: \n - "
                + "\n - ".join(
                    [
                        futures.get(future) for future in result.not_done
                    ]  # pyright: ignore[reportCallIssue, reportArgumentType]
                )
            )
            failed = True

        if failed:
            raise Exception("Unable to complete download and extraction")

    def check_and_prepare_dumps(self):

        # Dumps preparation progress:
        # 1pt for each archive to download
        # 1pt for 7z extraction
        # 3pt for users XML computation
        # 5pt for posts XML computation
        shared.progresser.start(
            shared.progresser.PREPARATION_STEP, nb_total=len(self.archives) * 2 + 3 + 5
        )

        tags = shared.build_dir / "Tags.xml"
        users = shared.build_dir / "users_with_badges.xml"
        posts = shared.build_dir / "posts_complete.xml"

        # check what needs to be done for each substep in order to reuse existing files
        if not tags.exists() or not users.exists() or not posts.exists():
            if not all(
                shared.build_dir.joinpath(f"{part}.xml").exists()
                for part in self.dump_parts
            ):
                self.download_and_extract_archives()
            else:
                logger.info("Extracted parts present; reusing")
        else:
            logger.info("Prepared dumps already present; reusing.")
            self.count_items(users, posts, tags)
            shared.progresser.update(nb_done=1, nb_total=1)
            return

        if not tags.exists():
            raise OSError(f"Missing {tags.name} while we should not.")

        merge_users_with_badges(
            workdir=shared.build_dir, delete_src=not context.keep_intermediate_files
        )
        if not users.exists():
            raise OSError(f"Missing {users.name} while we should not.")
        shared.progresser.update(incr=3)

        merge_posts_with_answers_comments(
            workdir=shared.build_dir, delete_src=not context.keep_intermediate_files
        )
        if not posts.exists():
            raise OSError(f"Missing {posts.name} while we should not.")
        shared.progresser.update(incr=5)

        self.count_items(users, posts, tags)
        logger.info("Prepared dumps completed.")

    def count_items(self, users, questions, tags):

        shared.total_tags = count_xml_rows(tags, "row")
        logger.info(f"{shared.total_tags} tags found")

        shared.total_users = count_xml_rows(users, "row")
        logger.info(f"{shared.total_users} users found")

        shared.total_questions = count_xml_rows(questions, "post")
        logger.info(f"{shared.total_questions} questions found")
