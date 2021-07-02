#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import re
import urllib.parse

import bs4
import mistune
from mistune.plugins import plugin_strikethrough, plugin_table, plugin_footnotes
from tld import get_fld
from slugify import slugify

from . import GlobalMixin
from .misc import rebuild_uri
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
]

REDACTED_STRING = "[redacted]"


class Rewriter(GlobalMixin):
    redacted_text = "[redacted]"

    def __init__(self):
        self.domain_re = re.compile(rf"https?://{self.domain}(?P<path>/.+)")
        self.qid_slug_answer_re = re.compile(
            r"^(q|questions)/(?P<post_id>[0-9]+)/[^/]+/(?P<answer_id>[0-9]+)"
        )
        self.qid_re = re.compile(r"^(q|questions)/(?P<post_id>[0-9]+)/?")
        self.aid_re = re.compile(r"^a/(?P<answer_id>[0-9]+)/?")
        self.uid_re = re.compile(r"^users/(?P<user_id>[0-9]+)/?")
        self.redacted_string = bs4.NavigableString(self.redacted_text)
        self.markdown = mistune.create_markdown(
            escape=False,
            plugins=[plugin_strikethrough, plugin_table, plugin_footnotes],
        )
        if self.conf.censor_words_list:
            with open(self.conf.build_dir.joinpath("words.list"), "r") as fh:
                # this will actually replace occurences of ~strings matching
                # words in the list but those can be part of actual words or whole.
                self.words_re = re.compile(
                    r"\b\b|\b\b".join(
                        map(re.escape, [line.strip() for line in fh.readlines()])
                    )
                )
                # self.words_as_char_re = re.compile(
                #     "|".join(map(re.escape,
                # [line.strip() for line in fh.readlines()])))

    @property
    def domain(self):
        return self.conf.domain

    def redact_link(self, link):
        for attr in ("href", "title"):
            if attr in link:
                del link[attr]
        link.contents = [self.redacted_string]

    def rewrite(self, content: str, unwrap: bool = False):
        """rewrite a stackexchange HTML markup to comply with ZIM and options

        SE's content is usually inputed as Markdown but the SE dumps we use
        contain the HTML version of posts.
        Allowed HTML markup: https://meta.stackexchange.com/questions/1777/

        Highlights:
        - Images are only in <img />, not <picture /> or <object />
        - No `srcset` attr for <img />
        - No relative `src` for <img />
        - <a /> can have a `title` attr.

        `unwrap` parameter: whether to ~unwrap the tag around the content.
        Markdown (mistune) considers single line of texts as paragraphs so single-line
        content are wrapped inside a <p/> node which is not what we want in some
        cases like Comments.

        """

        soup = bs4.BeautifulSoup(self.markdown(content), "lxml")

        # remove makrdown wrapping for single-line if requested
        if unwrap:
            soup.body.find().unwrap()

        # remove <html><body> wrapping that lxml generated
        soup.body.unwrap()
        soup.html.unwrap()

        self.rewrite_links(soup)

        self.rewrite_images(soup)

        # apply censorship rewriting
        if self.conf.censor_words_list:
            self.censor_words(soup)

        return str(soup)

    def rewrite_string(self, content: str) -> str:
        """rewritten single-string using non-markup-related rules"""
        if self.conf.censor_words_list:
            return self.words_re.sub(self.redacted_text, content)
        return content

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
        if self.conf.without_users_links and (
            link["href"].startswith("mailto:")
            or get_fld(link["href"]) in SOCIAL_DOMAINS
        ):
            self.redact_link(link)
            return 1

    def rewrite_external_link(self, link):
        link["class"] = " ".join(link.get("class", []) + ["external-link"])
        if self.conf.without_external_links:
            del link["href"]

    def rewrite_relative_link(self, link):
        # link to root (/)
        if link["href"] == "":
            # our <base /> will take care of the rest now
            return

        uri = urllib.parse.urlparse(link["href"])

        # link to question:
        #  - q/{qid}/slug/{aid}#{aid}
        #  - q/{qid}/slug/{aid}
        #  - questions/{qid}/{slug}/{aid}#{aid}
        #  - questions/{qid}/{slug}/{aid}
        # rewrite to questions/{id}/{slug}
        qid_answer_m = self.qid_slug_answer_re.match(uri.path)
        if qid_answer_m:
            qid = qid_answer_m.groupdict().get("post_id")
            aid = qid_answer_m.groupdict().get("answer_id")
            title = self.database.get_question_title_desc(qid)["title"]
            link["href"] = rebuild_uri(
                uri=uri, path=f"questions/{qid}/{get_slug_for(title)}", fragment=aid
            ).geturl()
            return

        # link to question
        #  - q/{id}
        #  - q/{id}/
        #  - q/{id}/{slug}
        #  - questions/{id}
        #  - questions/{id}/
        #  - questions/{id}/{slug}
        # rewrite to questions/{id}/{slug}
        qid_m = self.qid_re.match(uri.path)
        if qid_m:
            qid = qid_m.groupdict().get("post_id")
            title = self.database.get_question_title_desc(qid)["title"]
            link["href"] = rebuild_uri(
                uri=uri, path=f"questions/{qid}/{get_slug_for(title)}"
            ).geturl()
            return

        # link to answer:
        #  - a/{aId}
        #  - a/{aId}/
        #  - a/{aId}/{userId}
        #  - a/{aId}/{userId}/
        # rewrite to a/{aId}
        # we have a/{aId} redirect for all answer redirecting to questions/{qid}/{slug}
        # so eventually this will lead to questions/{qid}/{slug}#{aid}
        aid_m = self.aid_re.match(uri.path)
        if aid_m:
            aid = aid_m.groupdict().get("answer_id")
            link["href"] = rebuild_uri(uri=uri, path=f"a/{aid}", fragment=aid).geturl()
            return

        # link to user profile:
        # users/{uId}/slug
        # users/{uId}/slug/
        # users/{uId}
        # users/{uId}/
        # > rewrite to users/{uId}/{slug}
        uid_slug_m = self.uid_re.match(uri.path)
        if uid_slug_m:
            uid = uid_slug_m.groupdict().get("user_id")
            try:
                name = self.database.get_user_full(uid)["name"]
            except TypeError:
                # we might not get a response from database for that user_id:
                # - link to be to an invalid user_id
                # - user might have been excluded if without interactions
                del link["href"]
            else:
                link["href"] = rebuild_uri(
                    uri=uri, path=f"users/{uid}/{get_slug_for(name)}"
                ).geturl()
            return

    def rewrite_images(self, soup):
        for img in soup.find_all("img", src=True):
            if not img.get("src"):
                continue
            # remove all images
            if self.conf.without_images:
                del img["src"]
            # process all images
            else:
                img["onerror"] = "onImageLoadingError(this);"
                img["src"] = self.imager.defer(img["src"], is_profile=False)

    # def censor_words_as_string(self, soup) -> str:
    #     if not self.conf.censor_words_list:
    #         return str(soup)

    #     return self.words_as_char_re.sub(self.redacted_text, str(soup))

    def censor_words(self, soup):
        if not self.conf.censor_words_list:
            return

        # BeautifulSoup doesn't allow editing NavigableString in place. We have to
        # replace those with new instances.
        # Additionaly, we can't replace occurences within a loop on the
        # .descendants generator (breaks the loop[]) so we have to iterate over all
        # tags using find_all

        def only_bare_strings(tag):
            # BS returns NavigableString but also its parent if it contains a single NS
            # make sure we don't apply this to code-related elements
            # should we apply it to <code/> and <pre /> ?
            return isinstance(tag, bs4.NavigableString) and tag.parent.name not in (
                "script",
                "body",
                "html",
                "[document]",
                "style",
                "code",
                "pre",
            )

        for tag in filter(only_bare_strings, soup.find_all(string=True)):
            try:
                tag.replace_with(self.rewrite_string(tag))
            except Exception as exc:
                logger.debug(f"Replacement error: {exc} on: {tag}")
                continue

        # now apply filtering on tag attributes. As per SE rules, users can only
        # set `alt` and `title` on <img />` and `title` on `<a />`
        for tag in soup.find_all(
            lambda x: x.name in ("a", "img")
            and (x.has_attr("title") or x.has_attr("alt"))
        ):
            for attr in ("title", "alt"):
                if tag.attrs.get(attr):
                    tag.attrs[attr] = self.rewrite_string(tag.attrs[attr])
