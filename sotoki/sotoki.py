#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

"""sotoki.

Usage:
  sotoki <domain> <publisher> [--directory=<dir>] [--nozim] [--tag-depth=<tag_depth>] [--threads=<threads>] [--zimpath=<zimpath>] [--optimization-cache=<optimization-cache>] [--reset] [--reset-images] [--clean-previous] [--nofulltextindex] [--ignoreoldsite] [--nopic] [--no-userprofile]
  sotoki (-h | --help)
  sotoki --version

Options:
  -h --help                                     Display this help
  --version                                     Display the version of Sotoki
  --directory=<dir>                             Configure directory in which XML files will be stored [default: download]
  --nozim                                       Doesn't build a ZIM file, output will be in 'work/output/' in flat HTML files (otherwise 'work/ouput/' will be in deflated form and will produce a ZIM file)
  --tag-depth=<tag_depth>                       Configure the number of questions, ordered by Score, to display in tags pages (should be a multiple of 100, default all question are in tags pages) [default: -1]
  --threads=<threads>                           Number of threads to use, default is number_of_cores/2
  --zimpath=<zimpath>                           Final path of the zim file
  --reset                                       Reset dump
  --reset-images                                Remove images in cache
  --clean-previous                              Delete only data from a previous run with '--nozim' or which failed
  --nofulltextindex                             Doesn't index content
  --ignoreoldsite                               Ignore Stack Exchange closed sites
  --nopic                                       Doesn't download images
  --no-userprofile                              Doesn't include user profiles
  --optimization-cache=<optimization-cache>     Use optimization cache with given URL and credentials. The argument needs to be of the form <endpoint-url>?keyId=<key-id>&secretAccessKey=<secret-access-key>&bucketName=<bucket-name>
"""
import re
import sys
import os
import html
import zlib
import shlex
import shutil
import requests
import sqlite3
import os.path
import pathlib
import tempfile
import datetime
import subprocess
from hashlib import sha256
from string import punctuation
from docopt import docopt, DocoptExit
from distutils.dir_util import copy_tree
from multiprocessing import cpu_count, Queue, Process
from xml.sax import make_parser, handler
import urllib.request
import urllib.parse
from urllib.request import urlopen
from PIL import Image
import magic
import mistune
from mistune.plugins import plugin_url
import pydenticon
from slugify import slugify
import bs4 as BeautifulSoup
from jinja2 import Environment
from jinja2 import FileSystemLoader
from lxml import etree
from lxml.html import fromstring as string2html
from lxml.html import tostring as html2string
from kiwixstorage import KiwixStorage
from pif import get_public_ip
from zimscraperlib.download import save_large_file

ROOT_DIR = pathlib.Path(__file__).parent
NAME = ROOT_DIR.name

with open(ROOT_DIR.joinpath("VERSION"), "r") as fh:
    VERSION = fh.read().strip()

SCRAPER = f"{NAME} {VERSION}"

MARKDOWN = None
TMPFS_DIR = "/dev/shm" if os.path.isdir("/dev/shm") else None

CACHE_STORAGE_URL = None

#########################
#        Question       #
#########################
class QuestionRender(handler.ContentHandler):
    def __init__(
        self,
        templates,
        output,
        title,
        publisher,
        dump,
        cores,
        cursor,
        conn,
        deflate,
        site_url,
        redirect_file,
        domain,
        mathjax,
        nopic,
        nouserprofile,
    ):
        self.templates = templates
        self.output = output
        self.title = title
        self.publisher = publisher
        self.dump = dump
        self.cores = cores
        self.cursor = cursor
        self.conn = conn
        self.deflate = deflate
        self.site_url = site_url
        self.domain = domain
        self.post = {}
        self.comments = []
        self.answers = []
        self.whatwedo = "post"
        self.nb = 0  # Nomber of post generate
        os.makedirs(os.path.join(output, "question"))
        self.request_queue = Queue(cores * 2)
        self.workers = []
        self.cores = cores
        self.conn = conn
        self.mathjax = mathjax
        self.nopic = nopic
        self.nouserprofile = nouserprofile
        for i in range(self.cores):
            self.workers.append(Worker(self.request_queue))
        for i in self.workers:
            i.start()
        self.f_redirect = open(redirect_file, "a")

    def startElement(self, name, attrs):  # For each element
        if (
            name == "comments" and self.whatwedo == "post"
        ):  # We match if it's a comment of post
            self.whatwedo = "post/comments"
            self.comments = []
            return
        if name == "comments" and self.whatwedo == "post/answers":  # comment of answer
            self.whatwedo = "post/answers/comments"
            self.comments = []
            return
        if name == "answers":  # a answer
            self.whatwedo = "post/answers"
            self.comments = []
            self.answers = []
            return
        if name == "row":  # Here is a answer
            tmp = {}
            for k in list(attrs.keys()):  # Get all item
                tmp[k] = attrs[k]
            tmp["Score"] = int(tmp["Score"])
            if (
                "AcceptedAnswerId" in self.post
                and self.post["AcceptedAnswerId"] == tmp["Id"]
            ):
                tmp["Accepted"] = True
            else:
                tmp["Accepted"] = False

            if (
                "OwnerUserId" in tmp
            ):  # We put the good name of the user how made the post
                user = self.cursor.execute(
                    "SELECT * FROM users WHERE id = ?", (int(tmp["OwnerUserId"]),)
                ).fetchone()
                oid = tmp["OwnerUserId"]
                if user is not None:
                    tmp["OwnerUserId"] = dict_to_unicodedict(user)
                    tmp["OwnerUserId"]["Id"] = oid
                    if self.nouserprofile:
                        tmp["OwnerUserId"]["Path"] = None
                    else:
                        tmp["OwnerUserId"]["Path"] = page_url(
                            tmp["OwnerUserId"]["Id"], tmp["OwnerUserId"]["DisplayName"]
                        )
                else:
                    tmp["OwnerUserId"] = dict_to_unicodedict({"DisplayName": "None"})
                    tmp["OwnerUserId"]["Id"] = oid
            elif "OwnerDisplayName" in tmp:
                tmp["OwnerUserId"] = dict_to_unicodedict(
                    {"DisplayName": tmp["OwnerDisplayName"]}
                )
            else:
                tmp["OwnerUserId"] = dict_to_unicodedict({"DisplayName": "None"})
            # print "        new answers"
            self.answers.append(tmp)
            return

        if name == "comment":  # Here is a comments
            tmp = {}
            for k in list(attrs.keys()):  # Get all item
                tmp[k] = attrs[k]
            # print "                 new comments"
            if "UserId" in tmp:  # We put the good name of the user how made the comment
                user = self.cursor.execute(
                    "SELECT * FROM users WHERE id = ?", (int(tmp["UserId"]),)
                ).fetchone()
                if "UserId" in tmp and user is not None:
                    tmp["UserDisplayName"] = dict_to_unicodedict(user)["DisplayName"]
                    if self.nouserprofile:
                        tmp["Path"] = None
                    else:
                        tmp["Path"] = page_url(tmp["UserId"], tmp["UserDisplayName"])
                else:
                    tmp["UserDisplayName"] = "None"
            else:
                tmp["UserDisplayName"] = "None"

            if "Score" in tmp:
                tmp["Score"] = int(tmp["Score"])
            tmp["Text"] = markdown(tmp["Text"])
            self.comments.append(tmp)
            return

        if name == "link":  # We add link
            if attrs["LinkTypeId"] == "1":
                self.post["relateds"].append(
                    {
                        "PostId": str(attrs["PostId"]),
                        "PostName": html.escape(attrs["PostName"], quote=False),
                    }
                )
            elif attrs["LinkTypeId"] == "3":
                self.post["duplicate"].append(
                    {
                        "PostId": str(attrs["PostId"]),
                        "PostName": html.escape(attrs["PostName"], quote=False),
                    }
                )
            return

        if (
            name != "post"
        ):  # We go out if it's not a post, we because we have see all name of posible tag (answers, row,comments,comment and we will see after post) This normally match only this root
            print("nothing " + name)
            return

        if name == "post":  # Here is a post
            self.whatwedo = "post"
            for k in list(attrs.keys()):  # get all item
                self.post[k] = attrs[k]
            self.post["relateds"] = []  # Prepare list for relateds question
            self.post["duplicate"] = []  # Prepare list for duplicate question
            self.post["filename"] = "%s.html" % self.post["Id"]

            if (
                "OwnerUserId" in self.post
            ):  # We put the good name of the user how made the post
                user = self.cursor.execute(
                    "SELECT * FROM users WHERE id = ?", (int(self.post["OwnerUserId"]),)
                ).fetchone()
                oid = self.post["OwnerUserId"]
                if user is not None:
                    self.post["OwnerUserId"] = dict_to_unicodedict(user)
                    self.post["OwnerUserId"]["Id"] = oid
                    if self.nouserprofile:
                        self.post["OwnerUserId"]["Path"] = None
                    else:
                        self.post["OwnerUserId"]["Path"] = page_url(
                            self.post["OwnerUserId"]["Id"],
                            self.post["OwnerUserId"]["DisplayName"],
                        )
                else:
                    self.post["OwnerUserId"] = dict_to_unicodedict(
                        {"DisplayName": "None"}
                    )
                    self.post["OwnerUserId"]["Id"] = oid
            elif "OwnerDisplayName" in self.post:
                self.post["OwnerUserId"] = dict_to_unicodedict(
                    {"DisplayName": self.post["OwnerDisplayName"]}
                )
            else:
                self.post["OwnerUserId"] = dict_to_unicodedict({"DisplayName": "None"})

    def endElement(self, name):
        if (
            self.whatwedo == "post/answers/comments"
        ):  # If we have a post with answer and comment on this answer, we put comment into the anwer
            self.answers[-1]["comments"] = self.comments
            self.whatwedo = "post/answers"
        if (
            self.whatwedo == "post/answers"
        ):  # If we have a post with answer(s), we put answer(s) we put them into post
            self.post["answers"] = self.answers
        elif (
            self.whatwedo == "post/comments"
        ):  # If we have post without answer but with comments we put comment into post
            self.post["comments"] = self.comments

        if name == "post":
            # print self.post
            self.nb += 1
            if self.nb % 1000 == 0:
                print("Already " + str(self.nb) + " questions done!")
                self.conn.commit()
            self.post["Tags"] = self.post["Tags"][1:-1].split("><")
            for t in self.post["Tags"]:  # We put tags into db
                sql = "INSERT INTO QuestionTag(Score, Title, QId, CreationDate, Tag) VALUES(?, ?, ?, ?, ?)"
                self.cursor.execute(
                    sql,
                    (
                        self.post["Score"],
                        self.post["Title"],
                        self.post["Id"],
                        self.post["CreationDate"],
                        t,
                    ),
                )
            # Make redirection
            for ans in self.answers:
                self.f_redirect.write(
                    "A\telement/"
                    + str(ans["Id"])
                    + ".html\tAnswer "
                    + str(ans["Id"])
                    + "\tA/question/"
                    + self.post["Id"]
                    + ".html\n"
                )
            self.f_redirect.write(
                "A\telement/"
                + str(self.post["Id"])
                + ".html\tQuestion "
                + str(self.post["Id"])
                + "\tA/question/"
                + self.post["Id"]
                + ".html\n"
            )

            data_send = [
                some_questions,
                self.templates,
                self.output,
                self.title,
                self.publisher,
                self.post,
                "question.html",
                self.deflate,
                self.site_url,
                self.domain,
                self.mathjax,
                self.nopic,
            ]
            self.request_queue.put(data_send)
            # some_questions(self.templates, self.output, self.title, self.publisher, self.post, "question.html", self.deflate, self.site_url, self.domain, self.mathjax, self.nopic)
            # Reset element
            self.post = {}
            self.comments = []
            self.answers = []

    def endDocument(self):
        self.conn.commit()
        # closing thread
        for i in range(self.cores):
            self.request_queue.put(None)
        for i in self.workers:
            i.join()
        print("---END--")
        self.f_redirect.close()


def some_questions(
    templates,
    output,
    title,
    publisher,
    question,
    template_name,
    deflate,
    site_url,
    domain,
    mathjax,
    nopic,
):
    try:
        question["Score"] = int(question["Score"])
        if "answers" in question:
            question["answers"] = sorted(
                question["answers"], key=lambda k: k["Score"], reverse=True
            )
            question["answers"] = sorted(
                question["answers"], key=lambda k: k["Accepted"], reverse=True
            )  # sorted is stable so accepted will be always first, then other question will be sort in ascending order
            for ans in question["answers"]:
                ans["Body"] = interne_link(ans["Body"], domain, question["Id"])
                ans["Body"] = image(ans["Body"], output, nopic)
                if "comments" in ans:
                    for comment in ans["comments"]:
                        comment["Text"] = interne_link(
                            comment["Text"], domain, question["Id"]
                        )
                        comment["Text"] = image(comment["Text"], output, nopic)

        filepath = os.path.join(output, "question", question["filename"])
        question["Body"] = interne_link(question["Body"], domain, question["Id"])
        question["Body"] = image(question["Body"], output, nopic)
        if "comments" in question:
            for comment in question["comments"]:
                comment["Text"] = interne_link(comment["Text"], domain, question["Id"])
                comment["Text"] = image(comment["Text"], output, nopic)
        question["Title"] = html.escape(question["Title"], quote=False)
        try:
            jinja(
                filepath,
                template_name,
                templates,
                False,
                deflate,
                question=question,
                rooturl="..",
                title=title,
                publisher=publisher,
                site_url=site_url,
                mathjax=mathjax,
                nopic=nopic,
            )
        except Exception as e:
            print("Failed to generate %s" % filepath)
            print("Error with jinja" + str(e))
            print(question)
    except Exception as e:
        print("Error with a post : " + str(e))


#########################
#        Tags           #
#########################


class TagsRender(handler.ContentHandler):
    def __init__(
        self,
        templates,
        output,
        title,
        publisher,
        dump,
        cores,
        cursor,
        conn,
        deflate,
        tag_depth,
        description,
        mathjax,
    ):
        # index page
        self.templates = templates
        self.output = output
        self.title = title
        self.publisher = publisher
        self.dump = dump
        self.cores = cores
        self.cursor = cursor
        self.conn = conn
        self.deflate = deflate
        self.description = description
        self.tag_depth = tag_depth
        self.mathjax = mathjax
        self.tags = []
        sql = "CREATE INDEX index_tag ON questiontag (Tag)"
        self.cursor.execute(sql)

    def startElement(self, name, attrs):  # For each element
        if name == "row":  # If it's a tag (row in tags.xml)
            if attrs["Count"] != "0":
                self.tags.append(
                    {
                        "TagUrl": urllib.parse.quote(attrs["TagName"]),
                        "TagName": attrs["TagName"],
                        "nb_post": int(attrs["Count"]),
                    }
                )

    def endDocument(self):
        sql = "SELECT * FROM questiontag ORDER BY Score DESC LIMIT 400"
        questions = self.cursor.execute(sql)
        some_questions = questions.fetchmany(400)
        new_questions = []
        questionsids = []
        for question in some_questions:
            question["filepath"] = str(question["QId"])
            question["Title"] = html.escape(question["Title"], quote=False)
            if question["QId"] not in questionsids:
                questionsids.append(question["QId"])
                new_questions.append(question)
        jinja(
            os.path.join(self.output, "index.html"),
            "index.html",
            self.templates,
            False,
            self.deflate,
            tags=sorted(self.tags[:200], key=lambda k: k["nb_post"], reverse=True),
            rooturl=".",
            questions=new_questions[:50],
            description=self.description,
            title=self.title,
            publisher=self.publisher,
            mathjax=self.mathjax,
        )
        jinja(
            os.path.join(self.output, "alltags.html"),
            "alltags.html",
            self.templates,
            False,
            self.deflate,
            tags=sorted(self.tags, key=lambda k: k["nb_post"], reverse=True),
            rooturl=".",
            title=self.title,
            publisher=self.publisher,
            mathjax=self.mathjax,
        )
        # tag page
        print("Render tag page")
        list_tag = [d["TagName"] for d in self.tags]
        os.makedirs(os.path.join(self.output, "tag"))
        for tag in list(set(list_tag)):
            dirpath = os.path.join(self.output, "tag")
            tagpath = os.path.join(dirpath, "%s" % tag)
            os.makedirs(tagpath)
            # build page using pagination
            offset = 0
            page = 1
            if self.tag_depth == -1:
                questions = self.cursor.execute(
                    "SELECT * FROM questiontag WHERE Tag = ? ORDER BY Score DESC",
                    (str(tag),),
                )
            else:
                questions = self.cursor.execute(
                    "SELECT * FROM questiontag WHERE Tag = ? ORDER BY Score DESC LIMIT ?",
                    (str(tag), self.tag_depth,),
                )

            while offset is not None:
                fullpath = os.path.join(tagpath, "%s.html" % page)
                some_questions = questions.fetchmany(100)
                if len(some_questions) != 100:
                    offset = None
                else:
                    offset += len(some_questions)
                some_questions = some_questions[:99]
                for question in some_questions:
                    question["filepath"] = str(question["QId"])
                    question["Title"] = html.escape(question["Title"], quote=False)
                hasprevious = page != 1
                jinja(
                    fullpath,
                    "tag.html",
                    self.templates,
                    False,
                    self.deflate,
                    tag=tag,
                    index=page,
                    questions=some_questions,
                    rooturl="../..",
                    hasnext=bool(offset),
                    next=page + 1,
                    hasprevious=hasprevious,
                    previous=page - 1,
                    title=self.title,
                    publisher=self.publisher,
                    mathjax=self.mathjax,
                )
                page += 1


#########################
#        Users          #
#########################
class UsersRender(handler.ContentHandler):
    def __init__(
        self,
        templates,
        output,
        title,
        publisher,
        dump,
        cores,
        cursor,
        conn,
        deflate,
        site_url,
        redirect_file,
        mathjax,
        nopic,
        nouserprofile,
    ):
        self.identicon_path = os.path.join(output, "static", "identicon")
        self.templates = templates
        self.output = output
        self.title = title
        self.publisher = publisher
        self.dump = dump
        self.cores = cores
        self.cursor = cursor
        self.conn = conn
        self.deflate = deflate
        self.site_url = site_url
        self.mathjax = mathjax
        self.nopic = nopic
        self.nouserprofile = nouserprofile
        self.id = 0
        self.redirect_file = redirect_file
        if not os.path.exists(self.identicon_path):
            os.makedirs(self.identicon_path)
        os.makedirs(os.path.join(output, "user"))
        # Set-up a list of foreground colours (taken from Sigil).
        self.foreground = [
            "rgb(45,79,255)",
            "rgb(254,180,44)",
            "rgb(226,121,234)",
            "rgb(30,179,253)",
            "rgb(232,77,65)",
            "rgb(49,203,115)",
            "rgb(141,69,170)",
        ]
        # Set-up a background colour (taken from Sigil).
        self.background = "rgb(224,224,224)"

        # Instantiate a generator that will create 5x5 block identicons
        # using SHA256 digest.
        self.generator = pydenticon.Generator(
            5, 5, foreground=self.foreground, background=self.background
        )  # noqa
        self.request_queue = Queue(cores * 2)
        self.workers = []
        self.user = {}
        for i in range(self.cores):
            self.workers.append(Worker(self.request_queue))
        for i in self.workers:
            i.start()

    def startElement(self, name, attrs):  # For each element
        if name == "badges":
            self.user["badges"] = {}
        if name == "badge":
            tmp = {}
            for k in list(attrs.keys()):
                tmp[k] = attrs[k]
            if tmp["Name"] in self.user["badges"]:
                self.user["badges"][tmp["Name"]] = self.user["badges"][tmp["Name"]] + 1
            else:
                self.user["badges"][tmp["Name"]] = 1
        if name == "row":
            self.id += 1
            if self.id % 1000 == 0:
                print("Already " + str(self.id) + " Users done !")
                self.conn.commit()
            self.user = {}
            for k in list(attrs.keys()):  # get all item
                self.user[k] = attrs[k]

    def endElement(self, name):
        if name == "row":
            user = self.user
            sql = "INSERT INTO users(id, DisplayName, Reputation) VALUES(?, ?, ?)"
            self.cursor.execute(
                sql, (int(user["Id"]), user["DisplayName"], user["Reputation"])
            )
            if not self.nouserprofile:
                with open(self.redirect_file, "a") as f_redirect:
                    f_redirect.write(
                        "A\tuser/"
                        + page_url(user["Id"], user["DisplayName"])
                        + ".html\tUser "
                        + slugify(user["DisplayName"])
                        + "\tA/user/"
                        + user["Id"]
                        + ".html\n"
                    )
            data_send = [
                some_user,
                user,
                self.generator,
                self.templates,
                self.output,
                self.publisher,
                self.site_url,
                self.deflate,
                self.title,
                self.mathjax,
                self.nopic,
                self.nouserprofile,
                self.redirect_file,
            ]
            self.request_queue.put(data_send)
            # some_user(user, self.generator, self.templates, self.output, self.publisher, self.site_url, self.deflate, self.title, self.mathjax, self.nopic, self.nouserprofile)

    def endDocument(self):
        self.conn.commit()
        # closing thread
        for i in range(self.cores):
            self.request_queue.put(None)
        for i in self.workers:
            i.join()
        print("---END--")


def some_user(
    user,
    generator,
    templates,
    output,
    publisher,
    site_url,
    deflate,
    title,
    mathjax,
    nopic,
    nouserprofile,
    redirect_file,
):
    filename = user["Id"] + ".png"
    identicons_path = os.path.join(output, "static", "identicon")
    fullpath = os.path.join(identicons_path, filename)
    if not nopic and not os.path.exists(fullpath):
        try:
            downloaded_fpath = download_image(
                user["ProfileImageUrl"], identicons_path, convert_png=True, resize=128,
            )
            with open(redirect_file, "a") as f_redirect:
                f_redirect.write(
                    f"I\tstatic/identicon/{filename}\tUser {user['Id']}\tI/static/identicon/{os.path.basename(downloaded_fpath)}\n"
                )

        except Exception:
            # Generate big identicon
            padding = (20, 20, 20, 20)
            identicon = generator.generate(
                slugify(user["DisplayName"]),
                128,
                128,
                padding=padding,
                output_format="png",
            )  # noqa
            with open(fullpath, "wb") as f:
                f.write(identicon)

    #
    if not nouserprofile:
        if "AboutMe" in user:
            user["AboutMe"] = image("<p>" + user["AboutMe"] + "</p>", output, nopic)
        # generate user profile page
        filename = "%s.html" % user["Id"]
        fullpath = os.path.join(output, "user", filename)
        jinja(
            fullpath,
            "user.html",
            templates,
            False,
            deflate,
            user=user,
            title=title,
            rooturl="..",
            publisher=publisher,
            site_url=site_url,
            mathjax=mathjax,
            nopic=nopic,
        )


#########################
#        Tools          #
#########################
class Worker(Process):
    def __init__(self, queue):
        super(Worker, self).__init__()
        self.queue = queue

    def run(self):
        for data in iter(self.queue.get, None):
            try:
                data[0](*data[1:])
                # some_questions(*data)
            except Exception as exc:
                print("error while rendering :", data)
                print(exc)


def intspace(value):
    orig = str(value)
    new = re.sub(r"^(-?\d+)(\d{3})", r"\g<1> \g<2>", orig)
    if orig == new:
        return new
    return intspace(new)


def markdown(text):
    text_html = MARKDOWN(text)[3:-5]
    if len(text_html) == 0:
        return "-"
    return text_html


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def scale(number):
    """Convert number to scale to be used in style to color arrows
    and comment score"""
    number = int(number)
    if number < 0:
        return "negative"
    if number == 0:
        return "zero"
    if number < 3:
        return "positive"
    if number < 8:
        return "good"
    return "verygood"


def page_url(ident, name):
    return str(ident) + "/" + slugify(name)


ENV = None  # Jinja environment singleton


def jinja(output, template, templates, raw, deflate, **context):
    template = ENV.get_template(template)
    page = template.render(**context)
    if raw:
        page = "{% raw %}" + page + "{% endraw %}"
    if deflate:
        with open(output, "wb") as f:
            f.write(zlib.compress(page.encode("utf-8")))
    else:
        with open(output, "w") as f:
            f.write(page)


def jinja_init(templates):
    global ENV
    templates = os.path.abspath(templates)
    ENV = Environment(loader=FileSystemLoader((templates,)))
    filters = dict(
        markdown=markdown,
        intspace=intspace,
        scale=scale,
        clean=lambda y: [x for x in y if x not in punctuation],
        slugify=slugify,
    )
    ENV.filters.update(filters)


def get_tempfile(suffix):
    return tempfile.NamedTemporaryFile(suffix=suffix, dir=TMPFS_DIR, delete=False).name


def get_filetype(path):
    ftype = "none"
    mime = magic.from_file(path)
    if "PNG" in mime:
        ftype = "png"
    elif "JPEG" in mime:
        ftype = "jpeg"
    elif "GIF" in mime:
        ftype = "gif"
    elif "Windows icon" in mime:
        ftype = "ico"
    return ftype


def download_from_cache(key, output, meta_tag, meta_val):
    cache_storage = KiwixStorage(CACHE_STORAGE_URL)
    if not cache_storage.has_object(key):
        print(os.path.basename(output) + " > Not found in cache")
        return False, None
    try:
        meta = cache_storage.get_object_stat(key).meta
    except Exception as e:
        print(
            os.path.basename(output)
            + " > Failed to get object meta from cache\n"
            + str(e)
            + "\n"
        )
        return False, None
    if meta.get(meta_tag, "") == meta_val:
        ext = meta.get("extension", "")
        output = output + ext
        try:
            print(os.path.basename(output) + " > Downloading from cache")
            cache_storage.download_file(key, output, progress=False)
            print(os.path.basename(output) + " > Successfully downloaded from cache")
            return True, output
        except Exception as e:
            print(
                os.path.basename(output)
                + " > Failed to download from cache\n"
                + str(e)
                + "\n"
            )
            return False, None
    print(os.path.basename(output) + f" > {meta_tag} doesn't match {meta_val}")
    return False, None


def upload_to_cache(fpath, key, meta_tag, meta_val, ext):
    meta = {meta_tag: meta_val, "extension": ext}
    cache_storage = KiwixStorage(CACHE_STORAGE_URL)
    try:
        cache_storage.upload_file(fpath, key, meta=meta)
        print(os.path.basename(fpath) + " > Successfully uploaded to cache")
    except Exception as e:
        raise Exception(
            os.path.basename(fpath) + " > Failed to upload to cache\n" + str(e)
        )


def get_meta_from_url(url):
    try:
        response_headers = requests.head(url=url, allow_redirects=True).headers
    except Exception as e:
        print(url + " > Problem while head request\n" + str(e) + "\n")
        return None, None
    else:
        if response_headers.get("etag") is not None:
            return "etag", response_headers["etag"]
        if response_headers.get("last-modified") is not None:
            return "last-modified", response_headers["last-modified"]
        if response_headers.get("content-length") is not None:
            return "content-length", response_headers["content-length"]
    return "default", "default"


def post_process_image(tmp_img, convert_png, resize, ext):
    if convert_png and ext != "png":
        convert_to_png(tmp_img, ext)
        ext = "png"
    if resize and ext != "gif":
        resize_one(tmp_img, ext, str(resize))
    optimize_one(tmp_img, ext)


def prepare_for_post_processing(ext, tmp_img, fullpath, convert_png):
    """ Adds extention to tmp_img and returns updated values of fullpath and tmp_img """
    if convert_png:
        ext = "png"
    fullpath = fullpath + f".{ext}"
    os.rename(tmp_img, tmp_img + f".{ext}")
    tmp_img = tmp_img + f".{ext}"
    return fullpath, tmp_img


def download_image(url, dst_dir, convert_png=False, resize=False):
    file_name = sha256(url.encode("utf-8")).hexdigest()
    fullpath = os.path.join(dst_dir, file_name)
    for extension in [".jpeg", ".png"]:
        if os.path.exists(fullpath + extension):
            return fullpath + extension
    downloaded = False
    key = None
    meta_tag = None
    meta_val = None
    if url[0:2] == "//":
        url = "http:" + url
    print(url + " > To be saved as " + os.path.basename(fullpath))
    if CACHE_STORAGE_URL:
        meta_tag, meta_val = get_meta_from_url(url)
        if meta_tag and meta_val:
            src_url = urllib.parse.urlparse(url)
            prefix = f"{src_url.scheme}://{src_url.netloc}/"
            key = f"{src_url.netloc}/{urllib.parse.quote_plus(src_url.geturl()[len(prefix):])}"
            # Key looks similar to ww2.someplace.state.gov/data%2F%C3%A9t%C3%A9%2Fsome+chars%2Fimage.jpeg%3Fv%3D122%26from%3Dxxx%23yes
            downloaded, fullpath = download_from_cache(
                key, fullpath, meta_tag, meta_val
            )
            if downloaded:
                return fullpath
    if not downloaded:
        tmp_img = None
        print(os.path.basename(fullpath) + " > Downloading from URL")
        try:
            tmp_img = get_tempfile(os.path.basename(fullpath))
            save_large_file(url, tmp_img)
            print(os.path.basename(fullpath) + " > Successfully downloaded from URL")
        except subprocess.CalledProcessError as e:
            os.unlink(tmp_img)
            print(
                os.path.basename(fullpath)
                + " > Error while downloading from original URL\n"
                + str(e)
                + "\n"
            )
            raise e
        else:
            # get extension
            ext = get_filetype(tmp_img)
            if ext != "none":
                fullpath, tmp_img = prepare_for_post_processing(
                    ext, tmp_img, fullpath, convert_png
                )
                try:
                    post_process_image(tmp_img, convert_png, resize, ext)
                    if CACHE_STORAGE_URL and meta_tag and meta_val:
                        print(os.path.basename(fullpath) + " > Uploading to cache")
                        upload_to_cache(tmp_img, key, meta_tag, meta_val, ext)
                except Exception as exc:
                    print(f"{os.path.basename(fullpath)} {exc}")
                finally:
                    shutil.move(tmp_img, fullpath)
                    print(f"Moved {tmp_img} to {fullpath}")
                    return fullpath
            else:
                os.unlink(tmp_img)


def interne_link(text_post, domain, question_id):
    body = string2html(text_post)
    links = body.xpath("//a")
    for a in links:
        if "href" in a.attrib:
            a_href = re.sub("^https?://", "", a.attrib["href"])
            if len(a_href) >= 2 and a_href[0] == "/" and a_href[1] != "/":
                link = a_href
            elif (
                a_href[0 : len(domain)] == domain
                or a_href[0 : len(domain) + 2] == "//" + domain
            ):
                if a_href[0] == "/":
                    link = a_href[2:]
                else:
                    link = a_href[len(domain) + 1 :]
            else:
                continue
            if link[0:2] == "q/" or (
                link[0:10] == "questions/" and link[10:17] != "tagged/"
            ):
                is_a = link.split("/")[-1].split("#")
                if len(is_a) == 2 and is_a[0] == is_a[1]:
                    # it a answers
                    qans = is_a[0]
                    a.attrib["href"] = "../element/" + qans + ".html#a" + qans
                else:
                    # question
                    qid = link.split("/")[1]
                    a.attrib["href"] = "../element/" + qid + ".html"
            elif link[0:10] == "questions/" and link[10:17] == "tagged/":
                tag = urllib.parse.quote(link.split("/")[-1])
                a.attrib["href"] = "../tag/" + tag + ".html"
            elif link[0:2] == "a/":
                qans_split = link.split("/")
                qans = qans_split[1]
                a.attrib["href"] = "../element/" + qans + ".html#a" + qans
            elif link[0:6] == "users/":
                userid = link.split("/")[1]
                a.attrib["href"] = "../user/" + userid + ".html"
    if links:
        text_post = html2string(body, method="html", encoding="unicode")
    return text_post


def image(text_post, output, nopic):
    images = os.path.join(output, "static", "images")
    body = string2html(text_post)
    imgs = body.xpath("//img")
    for img in imgs:
        if nopic:
            img.attrib["src"] = ""
        else:
            src = img.attrib["src"]
            fpath = download_image(src, images, resize=540)
            filename = os.path.basename(fpath)
            if filename:
                src = "../static/images/" + filename
                img.attrib["src"] = src
                img.attrib["style"] = "max-width:100%"

    # does the post contain images? if so, we surely modified
    # its content so save it.
    if imgs:
        text_post = html2string(body, method="html", encoding="unicode")
    return text_post


def grab_title_description_favicon_lang(url, output_dir, do_old):
    if (
        "moderators.meta.stackexchange.com" in url
    ):  # We do this special handling because redirect do not exist; website have change name, but not dump name see issue #80
        get_data = urlopen("https://communitybuilding.meta.stackexchange.com")
    else:
        get_data = urlopen(url)
    if "area51" in get_data.geturl():
        if do_old:
            close_site = {
                "http://arabic.stackexchange.com": "https://web.archive.org/web/20150812150251/http://arabic.stackexchange.com/"
            }
            if url in close_site:
                get_data = urlopen(close_site[url])
            else:
                sys.exit(
                    "This Stack Exchange site has been closed and is not supported by sotoki, please open a issue"
                )
        else:
            print(
                "This Stack Exchange site has been closed and --ignoreoldsite has been pass as argument so we stop"
            )
            sys.exit(0)

    output = get_data.read().decode("utf-8")
    soup = BeautifulSoup.BeautifulSoup(output, "html.parser")
    title = soup.find("meta", attrs={"name": "twitter:title"})["content"]
    description = soup.find("meta", attrs={"name": "twitter:description"})["content"]
    jss = soup.find_all("script")
    lang = "en"
    for js in jss:
        search = re.search(r'StackExchange.init\({"locale":"[^"]*', output)
        if search is not None:
            lang = re.sub(r'StackExchange.init\({"locale":"', "", search.group(0))
    favicon = soup.find("link", attrs={"rel": "icon"})["href"]
    if favicon[:2] == "//":
        favicon = "http:" + favicon
    favicon_out = os.path.join(output_dir, "favicon.png")
    try:
        downloaded_file = download_image(
            favicon, output_dir, convert_png=True, resize=48,
        )
        shutil.move(downloaded_file, favicon_out)
    except Exception as e:
        print(e)
    return [title, description, lang]


def exec_cmd(cmd, timeout=None, workdir=None):
    try:
        ret = None
        ret = subprocess.run(shlex.split(cmd), timeout=timeout, cwd=workdir).returncode
        return ret
    except subprocess.TimeoutExpired:
        print("Timeout ({}s) expired while running: {}".format(timeout, cmd))
    except Exception as e:
        print(e)


def bin_is_present(binary):
    try:
        subprocess.Popen(
            binary,
            universal_newlines=True,
            shell=False,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
    except OSError:
        return False
    else:
        return True


def dict_to_unicodedict(dictionnary):
    dict_ = {}
    if "OwnerDisplayName" in dictionnary:
        dictionnary["OwnerDisplayName"] = ""
    for k, v in list(dictionnary.items()):
        #        if isinstance(k, str):
        #            unicode_key = k.decode('utf8')
        #        else:
        unicode_key = k
        #        if isinstance(v, str) or type(v) == type({}) or type(v) == type(1):
        unicode_value = v
        #        else:
        #            unicode_value =  v.decode('utf8')
        dict_[unicode_key] = unicode_value

    return dict_


def prepare(dump_path, bin_dir):
    cmd = "bash " + bin_dir + "prepare_xml.sh " + dump_path + " " + bin_dir
    if exec_cmd(cmd) == 0:
        print("Prepare xml ok")
    else:
        sys.exit("Unable to prepare xml :(")


def optimize_one(path, ftype):
    if ftype == "jpeg":
        ret = exec_cmd("jpegoptim --strip-all -m50 " + path, timeout=20)
        if ret != 0:
            raise Exception("> jpegoptim failed for " + str(path))
    elif ftype == "png":
        ret = exec_cmd(
            "pngquant --verbose --nofs --force --ext=.png " + path, timeout=20
        )
        if ret != 0:
            raise Exception("> pngquant failed for " + str(path))
        # TODO: avdef step disabled temporarily as suspect in blender run freeze
        # ret = exec_cmd("advdef -q -z -4 -i 5  " + path, timeout=20)
        # if ret != 0:
        #     raise Exception("> advdef failed for " + str(path))
    elif ftype == "gif":
        ret = exec_cmd("gifsicle --batch -O3 -i " + path, timeout=20)
        if ret != 0:
            raise Exception("> gifscale failed for " + str(path))


def resize_one(path, ftype, nb_pix):
    if ftype == "gif":
        ret = exec_cmd("mogrify -resize " + nb_pix + r"x\> " + path, timeout=20)
        if ret != 0:
            raise Exception("> mogrify -resize failed for GIF " + str(path))
    elif ftype in ["png", "jpeg"]:
        try:
            im = Image.open(path)
            ratio = float(nb_pix) / float(im.size[0])
            hsize = int(float(im.size[1]) * ratio)
            im.resize((int(nb_pix), hsize)).save(path, ftype)
        except (KeyError, IOError) as e:
            raise Exception("> Pillow failed to resize\n" + e)


def create_temporary_copy(path):
    fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)))
    os.close(fd)
    shutil.copy2(path, temp_path)
    return temp_path


def convert_to_png(path, ext):
    if ext == "gif":
        path_tmp = create_temporary_copy(path)
        ret = exec_cmd(
            "gif2apng " + os.path.basename(path_tmp) + " " + os.path.basename(path),
            workdir=os.path.dirname(os.path.abspath(path)),
        )
        os.remove(path_tmp)
        if ret != 0:
            raise Exception("> gif2apng failed for " + str(path))
    else:
        try:
            im = Image.open(path)
            im.save(path, "PNG")
        except (KeyError, IOError) as e:
            raise Exception("> Pillow failed to convert to PNG\n" + e)


def get_hash(site_name):
    digest = None
    sha1hash_url = "https://archive.org/download/stackexchange/stackexchange_files.xml"
    output = urlopen(sha1hash_url).read()
    tree = etree.fromstring(output)
    for file in tree.xpath("/files/file"):
        if file.get("name") == site_name + ".7z":
            print("found")
            digest = file.xpath("sha1")[0].text
    if digest is None:
        print("File :" + site_name + ".7z no found")
        sys.exit(1)
    return digest


def download_dump(domain, dump_path):
    url_dump = "https://archive.org/download/stackexchange/" + domain + ".7z"
    digest = get_hash(domain)
    f = open(domain + ".hash", "w")
    f.write(digest + " " + domain + ".7z")
    f.close()
    exec_cmd("wget " + url_dump)
    if exec_cmd("sha1sum -c " + domain + ".hash") == 0:
        print("Ok we have get dump")
    else:
        print("KO, error will downloading the dump")
        os.remove(domain + ".hash")
        os.remove(domain + ".7z")
        sys.exit(1)
    print(
        "Starting to decompress dump, may take a very long time depending on dump size"
    )
    exec_cmd("7z e " + domain + ".7z -o" + dump_path)
    os.remove(domain + ".hash")
    os.remove(domain + ".7z")


def languageToAlpha3(lang):
    tab = {"en": "eng", "ru": "rus", "pt-BR": "por", "ja": "jpn", "es": "spa"}
    return tab[lang]


def clean(output, db, redirect_file):
    for elem in ["question", "tag", "user"]:
        elem_path = os.path.join(output, elem)
        if os.path.exists(elem_path):
            print("remove " + elem_path)
            shutil.rmtree(elem_path)
    if os.path.exists(os.path.join(output, "favicon.png")):
        os.remove(os.path.join(output, "favicon.png"))
    if os.path.exists(os.path.join(output, "index.html")):
        os.remove(os.path.join(output, "index.html"))
    if os.path.exists(db):
        print("remove " + db)
        os.remove(db)
    if os.path.exists(redirect_file):
        print("remove " + redirect_file)
        os.remove(redirect_file)


def data_from_previous_run(output, db, redirect_file):
    for elem in ["question", "tag", "user"]:
        elem_path = os.path.join(output, elem)
        if os.path.exists(elem_path):
            return True
    if (
        os.path.exists(os.path.join(output, "favicon.png"))
        or os.path.exists(os.path.join(output, "index.html"))
        or os.path.exists(db)
        or os.path.exists(redirect_file)
    ):
        return True
    return False


def use_mathjax(domain):
    """ const True

        used to be a static list of domains for which mathjax should be enabled.
        this list was updated with help from find_mathml_site.sh script (looks for
        mathjax string in homepage of the domain) """
    return True


def cache_credentials_ok(cache_storage_url):
    cache_storage = KiwixStorage(cache_storage_url)
    if not cache_storage.check_credentials(
        list_buckets=True, bucket=True, write=True, read=True, failsafe=True
    ):
        print("S3 cache connection error while testing permissions.")
        print(f"  Server: {cache_storage.url.netloc}")
        print(f"  Bucket: {cache_storage.bucket_name}")
        print(f"  Key ID: {cache_storage.params.get('keyid')}")
        print(f"  Public IP: {get_public_ip()}")
        return False
    print(
        "Using optimization cache: "
        + cache_storage.url.netloc
        + " with bucket: "
        + cache_storage.bucket_name
    )
    return True


#########################
#     Zim generation    #
#########################


def create_zims(
    title,
    publisher,
    description,
    redirect_file,
    domain,
    lang_input,
    zim_path,
    html_dir,
    noindex,
    nopic,
    scraper_version,
):
    print("Creating ZIM files")
    if zim_path is None:
        zim_path = dict(
            title=domain.lower(),
            lang=lang_input.lower(),
            date=datetime.datetime.now().strftime("%Y-%m"),
        )
        if nopic:
            zim_path = os.path.join(
                "work/", "{title}_{lang}_all_{date}_nopic.zim".format(**zim_path)
            )
        else:
            zim_path = os.path.join(
                "work/", "{title}_{lang}_all_{date}.zim".format(**zim_path)
            )

    if nopic:
        name = "kiwix." + domain.lower() + ".nopic"
    else:
        name = "kiwix." + domain.lower()
    creator = title
    return create_zim(
        html_dir,
        zim_path,
        title,
        description,
        languageToAlpha3(lang_input),
        publisher,
        creator,
        redirect_file,
        noindex,
        name,
        nopic,
        scraper_version,
        domain,
    )


def create_zim(
    static_folder,
    zim_path,
    title,
    description,
    lang_input,
    publisher,
    creator,
    redirect_file,
    noindex,
    name,
    nopic,
    scraper_version,
    domain,
):
    print("\tWriting ZIM for {}".format(title))
    context = {
        "languages": lang_input,
        "title": title,
        "description": description,
        "creator": creator,
        "publisher": publisher,
        "home": "index.html",
        "favicon": "favicon.png",
        "static": static_folder,
        "zim": zim_path,
        "redirect_csv": redirect_file,
        "tags": "_category:stack_exchange;stackexchange",
        "name": name,
        "scraper": scraper_version,
        "source": "https://{}".format(domain),
    }

    cmd = "zimwriterfs "
    if nopic:
        tmpfile = tempfile.mkdtemp()
        os.rename(
            os.path.join(static_folder, "static", "images"),
            os.path.join(tmpfile, "images"),
        )
        os.rename(
            os.path.join(static_folder, "static", "identicon"),
            os.path.join(tmpfile, "identicon"),
        )
        cmd = cmd + '--flavour="nopic" '
        context["tags"] += ";nopic"

    if noindex:
        cmd = cmd + "--withoutFTIndex "
    cmd = (
        cmd
        + ' --inflateHtml --redirects="{redirect_csv}" --welcome="{home}" --favicon="{favicon}" --language="{languages}" --title="{title}" --description="{description}" --creator="{creator}" --publisher="{publisher}" --tags="{tags}" --name="{name}" --scraper="{scraper}" --source="{source}" "{static}" "{zim}"'.format(
            **context
        )
    )
    print(cmd)

    if exec_cmd(cmd) == 0:
        print("Successfuly created ZIM file at {}".format(zim_path))
        if nopic:
            os.rename(
                os.path.join(tmpfile, "images"),
                os.path.join(static_folder, "static", "images"),
            )
            os.rename(
                os.path.join(tmpfile, "identicon"),
                os.path.join(static_folder, "static", "identicon"),
            )
            shutil.rmtree(tmpfile)
        return True
    print("Unable to create ZIM file :(")
    if nopic:
        os.rename(
            os.path.join(tmpfile, "images"),
            os.path.join(static_folder, "static", "images"),
        )
        os.rename(
            os.path.join(tmpfile, "identicon"),
            os.path.join(static_folder, "static", "identicon"),
        )
        shutil.rmtree(tmpfile)
    return False


def run():
    scraper_version = SCRAPER
    try:
        arguments = docopt(__doc__, version=scraper_version)
    except DocoptExit:
        print(__doc__)
        sys.exit()
    print(
        "starting sotoki scraper...{}".format(f"using {TMPFS_DIR}" if TMPFS_DIR else "")
    )
    if arguments["--optimization-cache"] is not None:
        if not cache_credentials_ok(arguments["--optimization-cache"]):
            raise ValueError(
                "Bad authentication credentials supplied for optimization cache. Please try again."
            )
        global CACHE_STORAGE_URL
        CACHE_STORAGE_URL = arguments["--optimization-cache"]
    else:
        print("No cache credentials provided. Continuing without optimization cache")
    if not arguments["--nozim"] and not bin_is_present("zimwriterfs"):
        sys.exit("zimwriterfs is not available, please install it.")
    # Check binary
    for binary in [
        "bash",
        "jpegoptim",
        "pngquant",
        "advdef",
        "gifsicle",
        "mogrify",
        "gif2apng",
        "wget",
        "sha1sum",
        "7z",
        "sed",
        "sort",
        "rm",
        "grep",
    ]:
        if not bin_is_present(binary):
            sys.exit(binary + " is not available, please install it.")
    tag_depth = int(arguments["--tag-depth"])
    if tag_depth != -1 and tag_depth <= 0:
        sys.exit("--tag-depth should be a positive integer")
    domain = arguments["<domain>"]
    if re.match("^https?://", domain):
        url = domain
        domain = re.sub("^https?://", "", domain).split("/")[0]
    else:
        url = "http://" + domain
    publisher = arguments["<publisher>"]

    if not os.path.exists("work"):
        os.makedirs("work")

    if arguments["--directory"] == "download":
        dump = os.path.join("work", re.sub(r"\.", "_", domain))
    else:
        dump = arguments["--directory"]

    output = os.path.join(dump, "output")
    db = os.path.join(dump, "se-dump.db")
    redirect_file = os.path.join(dump, "redirection.csv")

    # set ImageMagick's temp folder via env
    magick_tmp = os.path.join(dump, "magick")
    if os.path.exists(magick_tmp):
        shutil.rmtree(magick_tmp)
    os.makedirs(magick_tmp)
    os.environ.update({"MAGICK_TEMPORARY_PATH": magick_tmp})

    deflate = not arguments["--nozim"]

    if arguments["--threads"] is not None:
        cores = int(arguments["--threads"])
    else:
        cores = cpu_count() / 2 or 1

    if arguments["--reset"]:
        if os.path.exists(dump):
            for elem in [
                "Badges.xml",
                "Comments.xml",
                "PostHistory.xml",
                "Posts.xml",
                "Tags.xml",
                "usersbadges.xml",
                "Votes.xml",
                "PostLinks.xml",
                "prepare.xml",
                "Users.xml",
            ]:
                elem_path = os.path.join(dump, elem)
                if os.path.exists(elem_path):
                    os.remove(elem_path)
        arguments["--directory"] = "download"

    if arguments["--reset-images"]:
        if os.path.exists(os.path.join(dump, "output")):
            shutil.rmtree(os.path.join(dump, "output"))

    if arguments["--clean-previous"]:
        clean(output, db, redirect_file)

    if data_from_previous_run(output, db, redirect_file):
        sys.exit(
            "There is still data from a previous run, you can trash them by adding --clean-previous as argument"
        )

    if not os.path.exists(dump):
        os.makedirs(dump)
    if not os.path.exists(output):
        os.makedirs(output)
    if not os.path.exists(os.path.join(output, "static", "images")):
        os.makedirs(os.path.join(output, "static", "images"))

    title, description, lang_input = grab_title_description_favicon_lang(
        url, output, not arguments["--ignoreoldsite"]
    )

    if not os.path.exists(
        os.path.join(dump, "Posts.xml")
    ):  # If dump is not here, download it
        if domain == "stackoverflow.com":
            for part in [
                "stackoverflow.com-Badges",
                "stackoverflow.com-Comments",
                "stackoverflow.com-PostLinks",
                "stackoverflow.com-Posts",
                "stackoverflow.com-Tags",
                "stackoverflow.com-Users",
            ]:
                dump_tmp = os.path.join("work", re.sub(r"\.", "_", part))
                os.makedirs(dump_tmp)
                download_dump(part, dump_tmp)
            for path in [
                os.path.join("work", "stackoverflow_com-Badges", "Badges.xml"),
                os.path.join("work", "stackoverflow_com-Comments", "Comments.xml"),
                os.path.join("work", "stackoverflow_com-PostLinks", "PostLinks.xml"),
                os.path.join("work", "stackoverflow_com-Posts", "Posts.xml"),
                os.path.join("work", "stackoverflow_com-Tags", "Tags.xml"),
                os.path.join("work", "stackoverflow_com-Users", "Users.xml"),
            ]:
                filename = os.path.basename(path)
                os.rename(path, os.path.join(dump, filename))
                shutil.rmtree(os.path.dirname(path))
        else:
            download_dump(domain, dump)

    templates = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), "templates_mini"
    )

    # prepare db
    conn = sqlite3.connect(db)  # can be :memory: for small dump
    conn.row_factory = dict_factory
    cursor = conn.cursor()
    # create table tags-questions
    sql = "CREATE TABLE IF NOT EXISTS questiontag(id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE, Score INTEGER, Title TEXT, QId INTEGER, CreationDate TEXT, Tag TEXT)"
    cursor.execute(sql)
    # creater user table
    sql = "CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY UNIQUE, DisplayName TEXT, Reputation TEXT)"
    cursor.execute(sql)
    # create table for links
    sql = "CREATE TABLE IF NOT EXISTS links(id INTEGER, title TEXT)"
    cursor.execute(sql)
    conn.commit()

    jinja_init(templates)
    global MARKDOWN
    renderer = mistune.HTMLRenderer()
    MARKDOWN = mistune.Markdown(renderer, plugins=[plugin_url])
    if not os.path.exists(
        os.path.join(dump, "prepare.xml")
    ):  # If we haven't already prepare
        prepare(dump, os.path.abspath(os.path.dirname(__file__)) + "/")

    # Generate users !
    parser = make_parser()
    parser.setContentHandler(
        UsersRender(
            templates,
            output,
            title,
            publisher,
            dump,
            cores,
            cursor,
            conn,
            deflate,
            url,
            redirect_file,
            use_mathjax(domain),
            arguments["--nopic"],
            arguments["--no-userprofile"],
        )
    )
    parser.parse(os.path.join(dump, "usersbadges.xml"))
    conn.commit()

    # Generate question !
    parser = make_parser()
    parser.setContentHandler(
        QuestionRender(
            templates,
            output,
            title,
            publisher,
            dump,
            cores,
            cursor,
            conn,
            deflate,
            url,
            redirect_file,
            domain,
            use_mathjax(domain),
            arguments["--nopic"],
            arguments["--no-userprofile"],
        )
    )
    parser.parse(os.path.join(dump, "prepare.xml"))
    conn.commit()

    # Generate tags !
    parser = make_parser()
    parser.setContentHandler(
        TagsRender(
            templates,
            output,
            title,
            publisher,
            dump,
            cores,
            cursor,
            conn,
            deflate,
            tag_depth,
            description,
            use_mathjax(domain),
        )
    )
    parser.parse(os.path.join(dump, "Tags.xml"))
    conn.close()

    # remove magick tmp folder (not reusable)
    shutil.rmtree(magick_tmp, ignore_errors=True)

    # copy static
    if use_mathjax(domain):
        copy_tree(
            os.path.join(os.path.abspath(os.path.dirname(__file__)), "static_mathjax"),
            os.path.join(output, "static"),
        )
    copy_tree(
        os.path.join(os.path.abspath(os.path.dirname(__file__)), "static"),
        os.path.join(output, "static"),
    )
    if not arguments["--nozim"]:
        done = create_zims(
            title,
            publisher,
            description,
            redirect_file,
            domain,
            lang_input,
            arguments["--zimpath"],
            output,
            arguments["--nofulltextindex"],
            arguments["--nopic"],
            scraper_version,
        )
        if done:
            clean(output, db, redirect_file)


if __name__ == "__main__":
    run()
