#!/usr/bin/env python3
# -*-coding:utf8 -*
"""sotoki.

Usage:
  sotoki <domain> <publisher> [--directory=<dir>] [--nozim] [--tag-depth=<tag_depth>] [--threads=<threads>] [--zimpath=<zimpath>] [--reset] [--reset-images] [--clean-previous] [--nofulltextindex] [--ignoreoldsite] [--nopic] [--no-userprofile]
  sotoki (-h | --help)
  sotoki --version

Options:
  -h --help                Show this screen.
  --version                Show version.
  --directory=<dir>        Specify a directory for xml files [default: download]
  --nozim                  doesn't make zim file, output will be in work/output/ in normal html (otherwise work/ouput/ will be in deflate form and will produice a zim file)
  --tag-depth=<tag_depth>  Specify number of question, order by Score, to show in tags pages (should be a multiple of 100, default all question are in tags pages) [default: -1]
  --threads=<threads>      Number of threads to use, default is number_of_cores/2
  --zimpath=<zimpath>      Final path of the zim file
  --reset                  Reset dump
  --reset-images           Remove image in cache
  --clean-previous         Delete only data from a previous run with --nozim or which failed
  --nofulltextindex        Dont index content
  --ignoreoldsite          Ignore Stack Exchange closed site
  --nopic                  Dont download picture
  --no-userprofile         Not include user profile in zim
"""
import re
import sys
import os
import ssl
import html
import zlib
import shlex
import shutil
import sqlite3
import os.path
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
import urllib.error
from urllib.request import urlopen

import magic
import mistune  # markdown
import pydenticon
from PIL import Image
from slugify import slugify
import bs4 as BeautifulSoup
from jinja2 import Environment
from jinja2 import FileSystemLoader
from lxml import etree
from lxml.html import fromstring as string2html
from lxml.html import tostring as html2string

MARKDOWN = None


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
            tmp["Text"] = markdown(html.escape(tmp["Text"], quote=False))
            self.comments.append(tmp)
            return

        if name == "link":  # We add link
            if attrs["LinkTypeId"] == "1":
                self.post["relateds"].append(
                    {
                        "PostId": page_url(attrs["PostId"], attrs["PostName"]),
                        "PostName": html.escape(attrs["PostName"], quote=False),
                    }
                )
            elif attrs["LinkTypeId"] == "3":
                self.post["duplicate"].append(
                    {
                        "PostId": page_url(attrs["PostId"], attrs["PostName"]),
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
                    "A\tanswer/"
                    + str(ans["Id"])
                    + ".html\tAnswer "
                    + str(ans["Id"])
                    + "\tA/question/"
                    + self.post["Id"]
                    + ".html\n"
                )
            self.f_redirect.write(
                "A\tquestion/"
                + page_url(self.post["Id"], self.post["Title"])
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
            # some_questions(templates, output, title, publisher, self.post, "question.html", self.cursor)
            # Reset element
            self.post = {}
            self.comments = []
            self.answers = []

    def endDocument(self):
        print("---END--")
        self.conn.commit()
        # closing thread
        for i in range(self.cores):
            self.request_queue.put(None)
        for i in self.workers:
            i.join()
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

        filepath = os.path.join(output, "question", question["filename"])
        question["Body"] = interne_link(question["Body"], domain, question["Id"])
        question["Body"] = image(question["Body"], output, nopic)
        if "comments" in question:
            for comment in question["comments"]:
                comment["Text"] = interne_link(comment["Text"], domain, question["Id"])
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
            print(" * failed to generate: %s" % filepath)
            print("erreur jinja" + str(e))
            print(question)
    except Exception as e:
        print("Erreur with one post : " + str(e))


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
            question["filepath"] = page_url(question["QId"], question["Title"])
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
                    question["filepath"] = page_url(question["QId"], question["Title"])
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
        self.f_redirect = open(redirect_file, "a")

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
                self.f_redirect.write(
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
            ]
            self.request_queue.put(data_send)

    def endDocument(self):
        print("---END--")
        self.conn.commit()
        # closing thread
        for i in range(self.cores):
            self.request_queue.put(None)
        for i in self.workers:
            i.join()
        self.f_redirect.close()


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
):
    filename = user["Id"] + ".png"
    fullpath = os.path.join(output, "static", "identicon", filename)
    if not nopic and not os.path.exists(fullpath):
        try:
            url = user["ProfileImageUrl"]
            ext = os.path.splitext(url.split("?")[0])[1]
            headers = download(url, fullpath, timeout=60)
            ext = get_filetype(headers, fullpath)
            if ext != "png":
                convert_to_png(fullpath, ext)
            if ext != "gif":
                resize_one(fullpath, "png", "128")
                optimize_one(fullpath, "png")
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
        return text
    return MARKDOWN(text)[3:-5]


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


def download(url, output, timeout=None):
    if url[0:2] == "//":
        url = "http:" + url
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    response = urlopen(url, timeout=timeout, context=ctx)
    output_content = response.read()
    with open(output, "wb") as f:
        f.write(output_content)
    return response.headers


def get_filetype(headers, path):
    ftype = "none"
    if "content-type" in headers:
        if ("png" in headers["content-type"]) or ("PNG" in headers["content-type"]):
            ftype = "png"
        elif (
            ("jpg" in headers["content-type"])
            or ("jpeg" in headers["content-type"])
            or ("JPG" in headers["content-type"])
            or ("JPEG" in headers["content-type"])
        ):
            ftype = "jpeg"
        elif ("gif" in headers["content-type"]) or ("GIF" in headers["content-type"]):
            ftype = "gif"
    else:
        with magic.Magic() as m:
            mine = m.id_filename(path)
            if "PNG" in mine:
                ftype = "png"
            elif "JPEG" in mine:
                ftype = "jpeg"
            elif "GIF" in mine:
                ftype = "gif"
    return ftype


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
                    a.attrib["href"] = "../answer/" + qans + ".html#a" + qans
                else:
                    # question
                    qid = link.split("/")[1]
                    a.attrib["href"] = qid + ".html"
            elif link[0:10] == "questions/" and link[10:17] == "tagged/":
                tag = urllib.parse.quote(link.split("/")[-1])
                a.attrib["href"] = "../tag/" + tag + ".html"
            elif link[0:2] == "a/":
                qans_split = link.split("/")
                qans = qans_split[1]
                a.attrib["href"] = "../answer/" + qans + ".html#a" + qans
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
            ext = os.path.splitext(src.split("?")[0])[1]
            filename = sha256(src.encode("utf-8")).hexdigest() + ext
            out = os.path.join(images, filename)
            # download the image only if it's not already downloaded and if it's not a html
            if not os.path.exists(out) and ext != ".html":
                try:
                    headers = download(src, out, timeout=180)
                    ftype = get_filetype(headers, out)
                    # update post's html
                    resize_one(out, ftype, "540")
                    optimize_one(out, ftype)
                except Exception as e:
                    # do nothing
                    print(e)
            src = "../static/images/" + filename
            img.attrib["src"] = src
            img.attrib["style"] = "max-width:100%"
            # finalize offlining

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
    download(favicon, favicon_out)
    resize_image_profile(favicon_out)
    return [title, description, lang]


def resize_image_profile(image_path):
    image = Image.open(image_path)
    w, h = image.size
    image = image.resize((48, 48), Image.ANTIALIAS)
    image.save(image_path)
    image.close()


def exec_cmd(cmd, timeout=None):
    try:
        return subprocess.call(shlex.split(cmd), timeout=timeout)
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
        exec_cmd("jpegoptim --strip-all -m50 " + path, timeout=20)
    elif ftype == "png":
        exec_cmd("pngquant --verbose --nofs --force --ext=.png " + path, timeout=20)
        exec_cmd("advdef -q -z -4 -i 5  " + path, timeout=20)
    elif ftype == "gif":
        exec_cmd("gifsicle --batch -O3 -i " + path, timeout=20)


def resize_one(path, ftype, nb_pix):
    if ftype in ["gif", "png", "jpeg"]:
        exec_cmd("mogrify -resize " + nb_pix + r"x\> " + path, timeout=20)


def create_temporary_copy(path):
    fd, temp_path = tempfile.mkstemp()
    os.close(fd)
    shutil.copy2(path, temp_path)
    return temp_path


def convert_to_png(path, ext):
    if ext == "gif":
        path_tmp = create_temporary_copy(path)
        exec_cmd("gif2apng " + path_tmp + " " + path)
        os.remove(path_tmp)
    else:
        exec_cmd("mogrify -format png " + path)


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

    if not noindex:
        cmd = cmd + "--withFullTextIndex "
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
    scraper_version = "sotoki 1.0"
    try:
        arguments = docopt(__doc__, version=scraper_version)
    except DocoptExit:
        print(__doc__)
        sys.exit()
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
    MARKDOWN = mistune.Markdown(renderer)
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
