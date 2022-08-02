#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import re
import urllib.parse
import warnings

import bs4

# import mistune
# from mistune.plugins import plugin_strikethrough, plugin_table, plugin_footnotes
from tld import get_fld
from slugify import slugify

from .shared import logger, GlobalMixin
from .misc import rebuild_uri


def get_text(content: str, strip_at: int = -1):
    """extracted text from an HTML source, optionaly striped"""
    soup = bs4.BeautifulSoup(content, "lxml")
    text = soup.text
    soup.decompose()
    if strip_at and len(text) > strip_at:
        return f'{text[0:strip_at].rsplit(" ", 1)[0]}…'
    return text


def get_slug_for(title: str):
    """stackexchange-similar slug for a title"""
    return slugify(str(title))[:78]


def is_in_code(elem):
    """whether this node is inside a <code /> one

    <code/> blocks are used to share code and are thus usually not rewritten"""
    for parent in elem.parents:
        if parent.name == "code":
            return True
    return False


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

# prevent beautifulsoup warning on comments containing only URLs
warnings.filterwarnings("ignore", category=bs4.MarkupResemblesLocatorWarning)


class BeautifulSoup(bs4.BeautifulSoup):
    def find_all(self, *args, **kwargs):
        try:
            return super().find_all(*args, **kwargs)
        except AttributeError as exc:
            logger.error(exc)
            return []


class Rewriter(GlobalMixin):
    redacted_text = "[redacted]"

    def __init__(self):
        self.domain_re = re.compile(rf"(https?:)?//{self.domain}(?P<path>/.+)")
        self.qid_slug_answer_re = re.compile(
            r"^(q|questions)/(?P<post_id>[0-9]+)/[^/]+/(?P<answer_id>[0-9]+)"
        )
        self.qid_re = re.compile(r"^(q|questions)/(?P<post_id>[0-9]+)/?")
        self.aid_re = re.compile(r"^a/(?P<answer_id>[0-9]+)/?")
        self.uid_re = re.compile(r"^users/(?P<user_id>[0-9]+)/?")
        self.tid_re = re.compile(r"^questions/tagged/(?P<tag_id>[0-9]+)/?$")

        # supported internal paths (what we provide)
        # used to rule-out in-SE internal links we don't support
        self.supported_res = (
            re.compile(r"questions/tagged/.+"),
            re.compile(r"users/[0-9]+/.+"),
            re.compile(r"questions/[0-9]+/.+"),
            re.compile(r"a/[0-9]+/?$"),
            re.compile(r"users/profiles/[0-9]+.webp$"),
            re.compile(r"questions/?$"),
            re.compile(r"questions_page=[0-9]+$"),
            re.compile(r"users/?$"),
            re.compile(r"users_page=[0-9]+$"),
            re.compile(r"tags$"),
            re.compile(r"tags_page=[0-9]+$"),
            re.compile(r"api/tags.json$"),
            re.compile(r"about$"),
            re.compile(r"images/[0-9]+.webp$"),
        )

        self.redacted_string = bs4.NavigableString(self.redacted_text)
        # self.markdown = mistune.create_markdown(
        #     escape=False,
        #     plugins=[plugin_strikethrough, plugin_table, plugin_footnotes],
        # )
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
            if attr in link.attrs:
                del link.attrs[attr]
        link.contents = [bs4.NavigableString("[redacted]")]

    def rewrite(self, content: str, to_root: str = "", unwrap: bool = False):
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
        # Content might be empty
        content = content.strip()
        if not content:
            return ""

        try:
            # soup = bs4.BeautifulSoup(self.markdown(content), "lxml")
            soup = BeautifulSoup(content, "lxml")
        except Exception as exc:
            logger.error(f"Unable to init soup or markdown for {content}: {exc}")
            return content

        if not soup:
            return ""

        # remove makrdown wrapping for single-line if requested
        if unwrap:
            try:
                soup.body.find().unwrap()
            except AttributeError:
                pass

        # remove <html><body> wrapping that lxml generated
        for wrapper in ("body", "html"):
            try:
                getattr(soup, wrapper).unwrap()
            except AttributeError:
                pass

        if self.site.get("highlight", False):
            self.rewrite_code(soup)

        self.rewrite_links(soup, to_root)

        self.rewrite_images(soup, to_root)

        # apply censorship rewriting
        if self.conf.censor_words_list:
            self.censor_words(soup)

        result = str(soup)
        soup.decompose()
        return result

    def rewrite_string(self, content: str) -> str:
        """rewritten single-string using non-markup-related rules"""
        if self.conf.censor_words_list:
            return self.words_re.sub(self.redacted_text, content)
        return content

    def rewrite_links(self, soup, to_root):
        # rewrite links targets
        for link in soup.find_all("a", href=True):

            # don't bother empty href=""
            if not link.get("href", "").strip():
                # remove link to "" as the use of a <base /> in our template
                # would turn it into a link to root
                del link.attrs["href"]
                continue

            # skip links inside <code /> nodes
            if is_in_code(link):
                continue

            link["href"] = link["href"].strip()

            # relative links (/xxx or ./ or ../)
            # we could have relative links starting with about anything else but
            # it's unlikely those are valid links inside questions as it would
            # only point to paths inside current path where users have no control
            is_relative = link["href"][0] in ("/", ".")
            is_relative &= not link["href"].startswith("//")

            if not is_relative:
                match = self.domain_re.match(link["href"])
                if match:
                    is_relative = True
                    # make the link relative and remove / so it's Zim compat
                    link["href"] = match.groupdict().get("path")[1:]

            # rewrite relative links to match our in-zim URIs
            if is_relative:
                # might be a relative link for which we don't offer an offline
                # version. ex: /help/*
                if not self.rewrite_relative_link(link, to_root):
                    continue

            # remove link completly if to an identified social-network domain
            if self.rewrite_user_link(link):
                continue  # external removal implied here

            # link is not relative, apply rules
            self.rewrite_external_link(link)

    def rewrite_user_link(self, link):
        try:
            if self.conf.without_users_links and (
                link["href"].startswith("mailto:")
                or get_fld(link["href"]) in SOCIAL_DOMAINS
            ):
                self.redact_link(link)
                return 1
        except Exception as exc:
            logger.warning(f"Failed to get fld for {link.get('href')}: {exc}")
            return 0

    def rewrite_external_link(self, link):
        link["class"] = " ".join(link.get("class", []) + ["external-link"])
        if self.conf.without_external_links:
            del link.attrs["href"]

    def rewrite_relative_link(self, link, to_root):
        # link to root (/)
        if link["href"] == "":
            # our <base /> will take care of the rest now
            return

        try:
            uri = urllib.parse.urlparse(link["href"])
            # normalize path as if from root.
            # any folder-walking link is considered to be targetting root
            uri_path = re.sub(r"^(\.\.?/)+", "", uri.path)
            uri_path = re.sub(r"^/", "", uri_path)
        except Exception as exc:
            logger.error(f"Failed to parse link target {link['href']}: {exc}")
            # consider this external
            return True

        # link to question:
        #  - q/{qid}/slug/{aid}#{aid}
        #  - q/{qid}/slug/{aid}
        #  - questions/{qid}/{slug}/{aid}#{aid}
        #  - questions/{qid}/{slug}/{aid}
        # rewrite to questions/{id}/{slug}
        qid_answer_m = self.qid_slug_answer_re.match(uri_path)
        if qid_answer_m:
            qid = qid_answer_m.groupdict().get("post_id")
            aid = qid_answer_m.groupdict().get("answer_id")
            title = self.database.get_question_title_desc(qid)["title"]
            if not title:
                del link.attrs["href"]
            else:
                link["href"] = rebuild_uri(
                    uri=uri,
                    path=f"{to_root}questions/{qid}/{get_slug_for(title)}",
                    fragment=aid,
                    failsafe=True,
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
        qid_m = self.qid_re.match(uri_path)
        if qid_m:
            qid = qid_m.groupdict().get("post_id")
            title = self.database.get_question_title_desc(qid)["title"]
            if not title:
                del link.attrs["href"]
            else:
                link["href"] = rebuild_uri(
                    uri=uri,
                    path=f"{to_root}questions/{qid}/{get_slug_for(title)}",
                    failsafe=True,
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
        aid_m = self.aid_re.match(uri_path)
        if aid_m:
            aid = aid_m.groupdict().get("answer_id")
            link["href"] = rebuild_uri(
                uri=uri,
                path=f"{to_root}a/{aid}",
                fragment=aid,
                failsafe=True,
            ).geturl()
            return

        # link to user profile:
        # users/{uId}/slug
        # users/{uId}/slug/
        # users/{uId}
        # users/{uId}/
        # > rewrite to users/{uId}/{slug}
        uid_slug_m = self.uid_re.match(uri_path)
        if uid_slug_m:
            uid = uid_slug_m.groupdict().get("user_id")
            try:
                name = self.database.get_user_full(uid)["name"]
            except TypeError:
                # we might not get a response from database for that user_id:
                # - link to be to an invalid user_id
                # - user might have been excluded if without interactions
                del link.attrs["href"]
            else:
                link["href"] = rebuild_uri(
                    uri=uri,
                    path=f"{to_root}users/{uid}/{get_slug_for(name)}",
                    failsafe=True,
                ).geturl()
            return

        # link to tag by ID
        # questions/tagged/{tId}
        # questions/tagged/{tId}/
        # > rewrite to questions/tagged/{tName}
        tid_m = self.tid_re.match(uri_path)
        if tid_m:
            try:
                tag = self.database.get_tag_name_for(
                    int(tid_m.groupdict().get("tag_id"))
                )
            except KeyError:
                del link.attrs["href"]
            else:
                link["href"] = rebuild_uri(
                    uri=uri,
                    path=f"{to_root}questions/tagged/{tag}",
                    failsafe=True,
                ).geturl()
            return

        # we did not rewrite this link. could be because it was already OK.
        # must check whether it has to be considered non-internal (not offlined)
        # ie: if it points to a path that is not being offlined
        if not any(filter(lambda reg: reg.match(uri_path), self.supported_res)):
            # doesn't match support route, rewrite to fqdn and report to caller
            link["href"] = rebuild_uri(
                uri=uri,
                scheme="http",
                hostname=self.conf.domain,
                failsafe=True,
            ).geturl()
            return True

        # did not require rewritting. Need normalization and to_root though
        link["href"] = rebuild_uri(
            uri=uri,
            path=f"{to_root}{uri_path}",
            failsafe=True,
        ).geturl()

    def rewrite_images(self, soup, to_root):
        for img in soup.find_all("img", src=True):
            if not img.get("src"):
                continue

            # remove all images
            if self.conf.without_images:
                del img.attrs["src"]
            # process all images
            else:

                # skip links inside <code /> nodes
                if is_in_code(img):
                    continue

                path = self.imager.defer(img["src"], is_profile=False)
                if path is None:
                    del img.attrs["src"]
                else:
                    img["src"] = f"{to_root}{path}"

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

    def rewrite_code(self, soup):
        for code in soup.find_all(
            lambda x: x.name == "code" and x.parent.name == "pre"
        ):
            pre_class = code.parent.attrs.get("class", [])
            if not isinstance(pre_class, list):
                pre_class = list(pre_class)
            code.parent.attrs["class"] = list(set(pre_class + ["s-code-block"]))
