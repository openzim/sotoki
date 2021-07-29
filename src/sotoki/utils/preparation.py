#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

""" StackExchange Dumps preparation utils

    Main goal is to prepare combined XML dumps that gets all required data on a
    single node when traversing the document using SAX """

import os
import re
import pathlib
import xml.sax
import subprocess
from typing import Union

from .shared import logger
from .misc import has_binary, get_available_memory
from ..constants import UTF8

has_gnusort = has_binary("sort")


def get_within_chars(nb_chars_glue: int, nb_ids: int) -> int:
    """nb of chars to combine `nb_ids`'s values with `nb_chars_glue`

    Used to compute `within` value for get_id_in()"""
    max_id_len = 8  # 8 chars can contain up to 99M ids
    return nb_chars_glue + (max_id_len * nb_ids)


def get_id_in(
    line: Union[bytes, str],
    index: int,
    sep: Union[bytes, str] = b'"',
    within: int = 30,
) -> int:
    """ID from an attribute on a line, based on ~field's index

    within is a number of chars within to look for the ID. This allows to drop
    most of the line out of memory and the split.

    IDs can take up to 8 chars (99M entries) usually."""
    return int(line[0:within].split(sep, index + 2)[index])


def get_index_in(src: pathlib.Path, id_attr: str) -> int:
    """compute an XML field's ID from a file to use as split index"""
    with open(src, "rb") as srch:
        line = srch.readline()
        return re.split(rb'\s([a-zA-Z]+)="', line).index(id_attr.encode(UTF8))


def remove_xml_headers(src: pathlib.Path, dst: pathlib.Path, delete_src: bool = True):
    """removes XML header (<?xml />) and root tag of a dump

    Consists in removing first two and last line of XML file

    Alternative: sed -e '1d' -e '2d' -e '$d' src.xml > dst.xml
    This impl. is _slightly_ slower than sed."""
    with open(src, "rb") as srch, open(dst, "wb") as dsth:
        srch.readline()  # read XML header

        # xml root node opening
        root_open = srch.readline().decode(UTF8).strip()
        # guess expected ending
        root_end = f"{root_open[0]}/{root_open[1:]}".encode(UTF8)
        root_end_len = len(root_end)

        for line in srch:
            try:
                if line[0:root_end_len] == root_end:  # reached EOD
                    break
            except IndexError:
                # line could be shorter than closing node
                pass
            dsth.write(line)

    if delete_src:
        src.unlink()


def sort_dump_by_id(
    src: pathlib.Path,
    dst: pathlib.Path,
    id_attr: str,
    delete_src: bool = True,
):
    """Sort an header-stripped XML dump by a node ID

    Uses GNU sort if available, falling back to python impl otherwise"""

    func = sort_dump_by_id_gnusort if has_gnusort else sort_dump_by_id_nodep
    func(src=src, dst=dst, field_num=get_index_in(src, id_attr), delete_src=delete_src)


def sort_dump_by_id_gnusort(
    src: pathlib.Path, dst: pathlib.Path, field_num: int, delete_src: bool
):
    """Sort an header-stripped XML dump by a node ID using GNU sort

    Way faster than naive impl (~x7). Consumes _a lot_ of RAM (90% of avail)"""

    args = [
        "/usr/bin/env",
        "sort",
        "--buffer-size",
        f"{int(get_available_memory() * .9)}b",
        '--field-separator="',
        f"--key={field_num + 1},{field_num + 1}n",  # from nth field to nth field, num
        f"--output={dst}",
        str(src),
    ]
    sort = subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env={"LC_ALL": "C"}
    )
    if not sort.returncode == 0:
        logger.error(f"Error running {args}: returned {sort.returncode}\n{sort.stdout}")
        raise subprocess.CalledProcessError(sort.returncode, args)

    if delete_src:
        src.unlink()


def sort_dump_by_id_nodep(
    src: pathlib.Path, dst: pathlib.Path, field_num: int, delete_src: bool
):
    """Sort an header-stripped XML dump by a node ID using a naive pure-python impl.

    While fecthing and sorting offsets/IDs is fast, randomly reading all those
    offsets one by one from the fs is not effiscient.

    Faster alternative in sort_dump_by_id_gnusort()"""

    with open(src, "rb") as srch, open(dst, "wb") as dsth:
        # record each line offset and corresponding ID in a list
        pattern_len = get_within_chars(22, field_num)

        lines = []
        while True:
            offset = srch.tell()
            try:
                pattern = srch.readline()[0:pattern_len]
                found_id = int(pattern.split(b'"', field_num + 1)[field_num])
            except IndexError:
                break
            lines.append((offset, found_id))

        # sort the list of offsets by ID
        lines.sort(key=lambda x: x[1])

        # jump from one offset to the other to write lines according to order in dst
        for offset, _ in lines:
            srch.seek(offset, os.SEEK_SET)
            dsth.write(srch.readline())

    if delete_src:
        src.unlink()


def merge_two_xml_files(
    main_src: pathlib.Path,
    sub_src: pathlib.Path,
    dst: pathlib.Path,
    sub_node_name: str,
    field_index_in_main: int = 1,
    field_index_in_sub: int = 3,
    write_header: bool = True,
    delete_src: bool = True,
):
    """Insert nodes from a `sub` XML file into nodes of a `main` one matching a prop ID

    sample:
        main:
            <nodeA someId="A" />
            <nodeA someId="B" />
        sub
            <nodeB attr="value" anId="A" />
            <nodeB attr="value" anId="A" />
        dst:
            <nodeA someId="A">
                <nodeBs>
                    <nodeB attr="value" anId="A" />
                    <nodeB attr="value" anId="A" />
                </nodeBs>
            </nodeA>
    """

    with open(main_src, "rb") as mainfh, open(sub_src, "rb") as subfh, open(
        dst, "wb"
    ) as dsth:

        def read_sub():
            line = subfh.readline()
            if not line:
                return None
            return get_id_in(line, field_index_in_sub, within=40), line

        nodes_start = f"<{sub_node_name}s>".encode(UTF8)
        nodes_end = f"</{sub_node_name}s>".encode(UTF8)
        node_start = f"<{sub_node_name}".encode(UTF8)

        # write header to dest
        if write_header:
            dsth.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
            dsth.write(b"<root>\n")

        # read first badges line so we can compare it in loop
        current_sub = read_sub()

        # loop on main file as this is our base that we'll complete with sub rows
        for main_line in mainfh:
            main_id = get_id_in(main_line, field_index_in_main)

            # write main line to dest; removing tag end (/> -> >) and CRLF
            dsth.write(main_line[:-4])
            dsth.write(b">")

            # fetch subs matching this ID (IDs are sorted so it's continuous)
            has_subs = False
            while current_sub is not None and current_sub[0] < main_id:
                current_sub = read_sub()
            while current_sub is not None and current_sub[0] == main_id:
                if not has_subs:
                    dsth.write(nodes_start)
                    has_subs = True

                dsth.write(node_start)
                # write the sub line removing the 2 heading spaces, node name (<row)
                # removing trailing CRLF as well. node already self closed in source
                dsth.write(current_sub[1][6:-2])
                current_sub = read_sub()

            if has_subs:
                dsth.write(nodes_end)
            has_subs = False
            dsth.write(b"</row>\n")

        if write_header:
            dsth.write(b"</root>")

    if delete_src:
        main_src.unlink()
        sub_src.unlink()


def create_sorted_comments(
    workdir: pathlib.Path, delete_src: bool = False
) -> pathlib.Path:
    """prepare comments by removing headers and sorting by PostId"""

    comments_orig = workdir / "Comments.xml"
    comments_nohead = workdir / "comments_nohead.xml"
    comments_sorted = workdir / "comments_sorted.xml"
    remove_xml_headers(src=comments_orig, dst=comments_nohead, delete_src=delete_src)
    logger.info("removed comments headers")
    del comments_orig

    sort_dump_by_id(
        src=comments_nohead,
        dst=comments_sorted,
        id_attr="PostId",
        delete_src=delete_src,
    )
    logger.info("sorted Comments by UserId")
    return comments_sorted


def merge_posts_with_comments(
    workdir: pathlib.Path, delete_src: bool = False
) -> pathlib.Path:
    """prepare posts+comments by removing post headers and merging with sorted comm"""
    comments_sorted = workdir / "comments_sorted.xml"
    posts_orig = workdir / "Posts.xml"
    posts_nohead = workdir / "posts_nohead.xml"
    posts_comments = workdir / "posts_with_comments.xml"
    remove_xml_headers(src=posts_orig, dst=posts_nohead, delete_src=delete_src)
    logger.info("removed posts headers")
    del posts_orig

    merge_two_xml_files(
        main_src=posts_nohead,
        sub_src=comments_sorted,
        dst=posts_comments,
        sub_node_name="comment",
        write_header=False,
        delete_src=delete_src,
    )
    logger.info("merged Posts and Comments")
    return posts_comments


def split_posts_by_posttypeid(
    src: pathlib.Path, dst_map: dict, delete_src: bool = False
):
    """explode posts file into files based on PostTypeId

    dst_map is a dict with a PostTypeId as key and a tuple value
    Tuple is (fpath, node_name) where fpath is where to write the nodes matchin ID
    and node_name is how those rows should be renamed (instead of input <row />)
    """
    fhs = {int(pid): open(item[0], "ab") for pid, item in dst_map.items()}
    starts = {int(pid): f"<{item[1]}".encode(UTF8) for pid, item in dst_map.items()}
    ends = {int(pid): f"{item[1]}>\n".encode(UTF8) for pid, item in dst_map.items()}

    index = get_index_in(src, "PostTypeId")
    pattern_len = get_within_chars(26, 1)

    with open(src, "rb") as srch:
        for line in srch:
            try:
                found_id = get_id_in(line, index, within=pattern_len)
            except IndexError:
                break
            try:
                # rewrite with new name replacing `  <row` and `row>`
                fhs[found_id].write(starts[found_id])
                fhs[found_id].write(line[6:-5])
                fhs[found_id].write(ends[found_id])
            except KeyError:
                continue

    # close file descriptors
    _ = {fh.close() for fh in fhs.values()}

    if delete_src:
        src.unlink()


def extract_posts_titles(src: pathlib.Path, dst: pathlib.Path):
    """extract all post titles and IDs from source and store as ID,"title" CSV

    CSV must include appropriate quoting for use as an SGML attribute"""
    index = get_index_in(src, "Id")
    with open(src, "r") as srch, open(dst, "w") as dsth:
        for line in srch:
            try:
                post_id = get_id_in(line, index, sep='"')
                title = xml.sax.saxutils.quoteattr(
                    line.rsplit(r'Title="', 1)[-1]
                    .rsplit(r'" Tags="')[0]
                    .replace('"', "")
                )
            except IndexError:
                break

            dsth.write(f"{post_id},{title}\n")


def add_post_names_to_links(
    links_src: pathlib.Path,
    csv_src: pathlib.Path,
    dst: pathlib.Path,
    delete_src: bool = False,
):
    """Recreate links file but each row gets a PostName with post name from CSV"""
    index = get_index_in(links_src, "PostId")
    with open(links_src, "rb") as linksh, open(csv_src, "rb") as csvh, open(
        dst, "wb"
    ) as dsth:

        def read_csv():
            line = csvh.readline()
            if not line:
                return None
            pid, title = line.split(b",", 1)
            return int(pid), title[:-1]  # remove CRLF, keep quotes

        # read first CSV line so we can compare it in loop
        current_csv = read_csv()

        # loop on links as this is our base that we'll update with names
        for line in linksh:
            post_id = get_id_in(line, index=index, within=None)

            while current_csv[0] < post_id:
                current_csv = read_csv()
                if current_csv is None:
                    break

            if current_csv is None:
                break

            if current_csv[0] == post_id:
                # write user line to dest; removing tag end and CRLF
                dsth.write(b"<link")
                dsth.write(line[6:-4])
                # CSV title already includes appropriate quoting
                dsth.write(b" PostName=")
                dsth.write(current_csv[1])
                dsth.write(b" />\n")

    if delete_src:
        links_src.unlink()
        csv_src.unlink()


class PostsAnswersLinksMerger:
    """merge <answers /> from answers file and <links /> from links file into posts

    Factored as a multi-methods class in order to lower code complexity"""

    def __init__(
        self,
        questions_src: pathlib.Path,
        answers_src: pathlib.Path,
        links_src: pathlib.Path,
        dst: pathlib.Path,
        delete_src: bool = False,
    ):
        self.files = {
            "questions": questions_src,
            "answers": answers_src,
            "links": links_src,
            "dst": dst,
        }
        self.handlers = {}  # file handles for all files
        # index of used Id used for matching in respective files
        self.indexes = {
            "id": get_index_in(questions_src, "Id"),
            "parent_id": get_index_in(answers_src, "ParentId"),
            "related_post_id": get_index_in(links_src, "RelatedPostId"),
        }
        self.open_files()

        # write header to dest
        self.handlers["dst"].write(b'<?xml version="1.0" encoding="utf-8"?>\n')
        self.handlers["dst"].write(b"<root>\n")
        self.write_lines()
        self.handlers["dst"].write(b"</root>")

        self.release_files(delete_src)

    def write_lines(self):
        # read first lines of answers and links
        current_answer = self.read_line("answers")
        current_link = self.read_line("links")

        # loop on questions file that we'll complete with answers and links
        for question_line in self.handlers["questions"]:
            post_id = get_id_in(question_line, self.indexes["id"])

            # write user line to dest; removing end tag and CRLF
            self.handlers["dst"].write(question_line[0:-8])

            # fetch matching answers. every answers is tied to a question
            has_answers = False
            while current_answer is not None and current_answer[0] < post_id:
                current_answer = self.read_line("answers")
            while current_answer is not None and current_answer[0] == post_id:
                if not has_answers:
                    self.handlers["dst"].write(b"<answers>")
                    has_answers = True

                self.handlers["dst"].write(current_answer[1][0:-1])  # skip CRLF
                current_answer = self.read_line("answers")
            if has_answers:
                self.handlers["dst"].write(b"</answers>")
            has_answers = False

            # fetch subs matching this ID (continuous)
            has_links = False
            while current_link is not None and current_link[0] < post_id:
                current_link = self.read_line("links")
            while current_link is not None and current_link[0] == post_id:
                if not has_links:
                    self.handlers["dst"].write(b"<links>")
                    has_links = True
                self.handlers["dst"].write(current_link[1][:-1])  # skip CRLF
                current_link = self.read_line("links")
            if has_links:
                self.handlers["dst"].write(b"</links>")
            has_links = False

            self.handlers["dst"].write(b"</post>\n")

    def read_line(self, kind):
        """read line in requested file and return matched-id, line"""
        within = get_within_chars(*{"answers": (39, 2), "links": (78, 3)}[kind])
        index = self.indexes[{"answers": "parent_id", "links": "related_post_id"}[kind]]

        line = self.handlers[kind].readline()
        if not line:
            return None
        return get_id_in(line, index, within=within), line

    def open_files(self):
        self.handlers = {
            key: open(value, "wb" if key == "dst" else "rb")
            for key, value in self.files.items()
        }

    def release_files(self, delete_src):
        for key, handler in self.handlers.items():
            handler.close()
            if delete_src and handler.mode.startswith("r"):
                self.files[key].unlink()


def merge_users_with_badges(
    workdir: pathlib.Path, delete_src: bool = False
) -> pathlib.Path:
    """list of User <row> (inside <root>) nodes with <badges /> (<badge />) merged-in"""

    badges_orig = workdir / "Badges.xml"
    badges_nohead = workdir / "badges_nohead.xml"
    badges_sorted = workdir / "badges_sorted.xml"
    remove_xml_headers(src=badges_orig, dst=badges_nohead, delete_src=delete_src)
    logger.info("removed badges headers")

    sort_dump_by_id(
        src=badges_nohead, dst=badges_sorted, id_attr="UserId", delete_src=delete_src
    )
    logger.info("sorted Badges by UserId")

    users_orig = workdir / "Users.xml"
    users_nohead = workdir / "users_nohead.xml"
    remove_xml_headers(users_orig, users_nohead, delete_src=delete_src)
    logger.info("removed users headers")

    users_with_badges = workdir / "users_with_badges.xml"

    # Merge Users and Badges
    merge_two_xml_files(
        users_nohead,
        badges_sorted,
        users_with_badges,
        sub_node_name="badge",
        delete_src=delete_src,
    )
    logger.info("merged both sets")
    return users_with_badges


def merge_posts_with_answers_comments(
    workdir: pathlib.Path, delete_src: bool = False
) -> pathlib.Path:
    """List of <post> nodes inside <root> with answers/comments/links merged-in

    <post> can contain <answers /> <comments /> and <links />
    <answer> can contain <comments />
    """

    # pepare Comments without headers, sorted PostId
    create_sorted_comments(workdir=workdir, delete_src=delete_src)
    # merge comments inside each post node respectively
    posts_comments = merge_posts_with_comments(workdir=workdir, delete_src=delete_src)

    # split posts into questions and answers files
    posts_com_questions = workdir / "posts_com_questions.xml"
    posts_com_answers = workdir / "posts_com_answers.xml"
    posts_excerpt = workdir / "posts_excerpt.xml"
    posts_wiki = workdir / "posts_wiki.xml"
    header = b'<?xml version="1.0" encoding="utf-8"?>\n<posts>\n'
    footer = b"</posts>"
    with open(posts_excerpt, "wb") as fhe, open(posts_wiki, "wb") as fhw:
        fhe.write(header)
        fhw.write(header)

    split_posts_by_posttypeid(
        posts_comments,
        {
            "1": (posts_com_questions, "post"),
            "2": (posts_com_answers, "answer"),
            "4": (posts_excerpt, "post"),
            "5": (posts_wiki, "post"),
        },
        delete_src=delete_src,
    )
    with open(posts_excerpt, "ab") as fhe, open(posts_wiki, "ab") as fhw:
        fhe.write(footer)
        fhw.write(footer)
    logger.info("split Posts-Comments by PostType")
    del posts_comments

    # generate a post_id,title CSV file for all questions
    posts_titles = workdir / "posts_titles.csv"
    extract_posts_titles(src=posts_com_questions, dst=posts_titles)
    logger.info("Extracted Post IDs and titles into CSV")

    posts_com_questions_sorted = workdir / "posts_com_questions_sorted.xml"
    posts_com_answers_sorted = workdir / "posts_com_answers_sorted.xml"
    sort_dump_by_id(
        src=posts_com_questions,
        dst=posts_com_questions_sorted,
        id_attr="Id",
        delete_src=delete_src,
    )
    logger.info("sorted Posts-Comments (questions) by Id")

    sort_dump_by_id(
        src=posts_com_answers,
        dst=posts_com_answers_sorted,
        id_attr="ParentId",
        delete_src=delete_src,
    )
    logger.info("sorted Posts-Comments (answers) by ParentId")

    postlinks_orig = workdir / "PostLinks.xml"
    postlinks_nohead = workdir / "postlinks_nohead.xml"
    postlinks_sorted = workdir / "postlinks_sorted.xml"
    remove_xml_headers(src=postlinks_orig, dst=postlinks_nohead, delete_src=delete_src)
    logger.info("removed postlinks headers")
    del postlinks_orig

    sort_dump_by_id(
        src=postlinks_nohead,
        dst=postlinks_sorted,
        id_attr="PostId",
        delete_src=delete_src,
    )
    logger.info("sorted PostLinks by PostId")
    del postlinks_nohead

    # add post names to <link /> nodes and sort them by RelatedPostId
    postlinks_named = workdir / "postlinks_named.xml"
    postlinks_named_sorted = workdir / "postlinks_named_sorted.xml"
    add_post_names_to_links(
        links_src=postlinks_sorted,
        csv_src=posts_titles,
        dst=postlinks_named,
        delete_src=delete_src,
    )
    del postlinks_sorted
    sort_dump_by_id(postlinks_named, postlinks_named_sorted, id_attr="RelatedPostId")
    logger.info("sorted named post links by RelatedPostId")

    posts_complete = workdir / "posts_complete.xml"
    PostsAnswersLinksMerger(
        questions_src=posts_com_questions_sorted,
        answers_src=posts_com_answers_sorted,
        links_src=postlinks_named_sorted,
        dst=posts_complete,
        delete_src=delete_src,
    )

    return posts_complete
