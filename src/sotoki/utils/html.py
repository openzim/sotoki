#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import re

import bs4
from tld import get_fld
from slugify import slugify

from . import GlobalMixin
from ..constants import getLogger


logger = getLogger()


def get_text(content: str, strip_at: int = -1):
    """extracted text from an HTML source, optionaly striped"""
    text = bs4.BeautifulSoup(content, "lxml").text
    if strip_at and len(text) > strip_at:
        return f'{text[0:strip_at].rsplit(" ", 1)[0]}…'
    return text


def get_slug_for(title: str):
    """stackexchange-similar slug for a title"""
    return slugify(title)[:78]


SOCIAL_DOMAINS = [
    "facebook.com",
    "youtube.com",
    "whatsapp.com",
    "m.me",
    "instagram.com",
    "icq.com",
    "qq.com",
    "tiktok.com",
    "douyin.com",
    "weibo.com",
    "telegram.com",
    "twitter.com",
    "snapchat.com",
    "twitch.tv",
    "kuaishou.com",
    "pinterest.com",
    "reddit.com",
    "oscars.org",
]

REDACTED_STRING = "[redacted]"


class Rewriter(GlobalMixin):
    def __init__(self):
        self.domain_re = re.compile(rf"http?s://{self.domain}(?P<path>\/.+)")
        self.qid_slug_re = re.compile(r"^q/(?P<post_id>[0-9+])\/.+")
        self.qid_re = re.compile(r"^q/(?P<post_id>[0-9+])/?$")
        self.aid_re = re.compile(r"^a/(?P<answer_id>[0-9+])/?$")
        self.uid_slug_re = re.compile(r"^users/(?P<user_id>[0-9+])\/.+")
        self.redacted_string = bs4.NavigableString("[redacted]")

    @property
    def domain(self):
        return self.conf.domain

    def redact_link(self, link):
        for attr in ("href", "title"):
            if attr in link:
                del link[attr]
        link.contents = [self.redacted_string]

    def rewrite(self, content: str):
        """rewrite a stackexchange HTML markup to comply with ZIM and options

        SE's content is usually inputed as Markdown but the SE dumps we use
        contain the HTML version of posts.
        Allowed HTML markup: https://meta.stackexchange.com/questions/1777/

        Highlights:
        - Images are only in <img />, not <picture /> or <object />
        - No `srcset` attr for <img />
        - No relative `src` for <img />
        - <a /> can have a `title` attr.

        """
        soup = bs4.BeautifulSoup(content, "lxml")

        self.rewrite_links()

        self.rewrite_images(soup)

        if self.conf.censor_words_list:
            self.censor_words(soup)

        return str(soup)

    def rewrite_links(self, soup):
        # rewrite links targets
        for link in soup.find_all("a", href=True):

            # don't bother empty href=""
            if not link.get("href", "").strip():
                # remove link to "" as the use of a <base /> in our template
                # would turn it into a link to root
                del link["href"]
                continue

            link["href"] = link["href"].strip()

            # relative links (/xxx or ./ or ../)
            is_relative = link["href"][0] in ("/", ".")

            if not is_relative:
                match = self.domain_re.match(link["href"].strip())
                if match:
                    is_relative = True
                    # make the link relative and remove / so it's Zim compat
                    link["href"] = match.groupdict().get("path")[1:]

            # rewrite relative links to match our in-zim URIs
            if is_relative:
                self.rewrite_relative_link(link)
                continue

            # remove link completly if to an identified social-network domain
            if self.rewrite_user_link(link):
                continue  # external removal implied here

            # link is not relative, apply rules
            self.rewrite_external_link(link)

    def rewrite_user_link(self, link):
        if self.conf.without_users_links and get_fld(link["href"]) in SOCIAL_DOMAINS:
            self.redact_link(link)
            return 1

    def rewrite_external_link(self, link):
        if self.conf.without_external_links:
            del link["href"]

    def rewrite_relative_link(self, link):
        # link to root (/)
        if link["href"] == "":
            # our <base /> will take care of the rest now
            return

        # link to question (q/{id}/slug)
        # rewrite to q/id
        qid_slug_m = self.qid_slug_re.match(link["href"])
        if qid_slug_m:
            link["href"] = f'questions/{qid_slug_m.groupdict().get("post_id")}'
            return

        # link to question (q/{id})
        qid_m = self.qid_re.match(link["href"])
        if qid_m:
            link["href"] = f'questions/{qid_m.groupdict().get("post_id")}'
            return

        # link to answer (a/{aId} and a/{aId}/)
        aid_m = self.aid_re.match(link["href"])
        if aid_m:
            aid = aid_m.groupdict().get("answer_id")
            link["href"] = f"a/{aid}#{aid}"
            return

        # link to (users/uId/slug)
        # > we have a redirect
        # uid_slug_m = self.uid_slug_re.match(link["href"])
        # if uid_slug_m:
        #     link["href"] = f'users/{uid_slug_m.groupdict().get("user_id")}'
        #     return

    def rewrite_images(self, soup):
        for img in soup.find_all("img", src=True):
            if not img.get("src"):
                continue
            # remove all images
            if self.conf.without_images:
                del img["src"]
            # process all images
            else:
                img["src"] = self.imager.defer(img["src"], is_profile=False)

    def censor_words(self, soup):
        # strip out censored words
        if not self.conf.censor_words_list:
            return
