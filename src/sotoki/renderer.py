#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import datetime
from typing import Union

from jinja2 import Environment, PackageLoader
from jinja2_pluralize import pluralize_dj

from .utils.shared import Global, GlobalMixin
from .utils.html import get_slug_for
from .utils.paginator import Paginator


def number_format(number: int, short: bool = False):
    try:
        number = int(number)
    except Exception:
        return number

    if not short:
        return f"{number:,}"

    try:
        suffix = ""
        for step, step_suff in ((1000000, "M"), (10000, "k")):
            if number > step:
                number = number / step
                suffix = step_suff
                break
        if isinstance(number, int):
            return f"{number:,}"
        return f"{number:,.2}{suffix}"
    except Exception:
        return number


def number_format_short(number: int):
    return number_format(number, short=True)


def date_format(adate: Union[datetime.datetime, str], fmt: str = "%b %d '%y at %H:%M"):
    if adate:
        try:
            if not isinstance(adate, datetime.datetime):
                adate = datetime.datetime.fromisoformat(adate)
        except ValueError:
            pass
        else:
            return adate.strftime(fmt)
    return adate


def extend_questions(questions):
    for post_id, score in questions:
        yield Global.database.get_question_details(post_id=post_id, score=score)


def get_user_details(user_id):
    user = Global.database.get_user_full(user_id)
    if not user:
        return {"deleted": True, "name": user_id}
    user["slug"] = get_slug_for(user["name"])
    user["deleted"] = False
    return user


class SortedSetPaginator(Paginator):
    def __init__(self, set_name: str, per_page: int = 10, at_most: int = None):
        self.set_name = set_name
        self.at_most = at_most
        super().__init__(per_page=per_page)

    def get_count(self):
        total = Global.database.get_set_count(self.set_name)
        if self.at_most:
            return min([self.at_most, total])
        return total

    def query(self, bottom: int, top: int):
        return Global.database.query_set(
            self.set_name, start=bottom, num=self.per_page, scored=True
        )


class ListPaginator(Paginator):
    def __init__(self, src: list, per_page: int = 10, at_most: int = None):
        self.src = src
        self.at_most = at_most
        super().__init__(per_page=per_page)

    def get_count(self):
        total = len(self.src)
        if self.at_most:
            return min([self.at_most, total])
        return total

    def query(self, bottom: int, top: int):
        return self.src[bottom:top]


class Renderer(GlobalMixin):
    def __init__(self):
        is_meta = bool(self.site.get("ParentId"))
        subtitle = (
            self.site.get("LongName")
            if self.conf.is_stackO
            else f"{self.site.get('LongName')} Stack Exchange"
        )
        # disabling autoescape as we are mosty inputing HTML content from SE dumps
        # that we trust already (should not include any XSS)
        self.env = Environment(  # nosec
            loader=PackageLoader("sotoki"), autoescape=False
        )
        self.env.filters["int"] = int
        self.env.filters["user"] = get_user_details
        self.env.filters["number"] = number_format
        self.env.filters["number_short"] = number_format_short
        self.env.filters["datetime"] = date_format
        self.env.filters["datetime"] = date_format
        self.env.filters["pluralize"] = pluralize_dj
        self.env.filters["question_score"] = self.database.get_question_score
        self.env.filters["has_accepted"] = self.database.question_has_accepted_answer
        self.env.filters["rewrote"] = self.rewriter.rewrite
        self.env.filters["rewrote_string"] = self.rewriter.rewrite_string
        self.env.filters["slugify"] = get_slug_for
        self.global_context = {
            "site_subtitle": subtitle,
            "site_title": self.site.get("LongName").replace(" Meta", "")
            if is_meta
            else subtitle,
            "site_mathjax": self.site.get("mathjax", False),
            "site_highlight": self.site.get("highlight", False),
            "is_meta": is_meta,
            # meta sites (with a ParentId) don't use custom CSS
            "site_css": "" if self.site.get("ParentId") else self.site.get("TagCss"),
            "conf": self.conf,
        }

    def get_question(self, post: dict):
        """Single question HTML for ZIM"""
        return self.env.get_template("question.html").render(
            body_class="question-page",
            whereis="questions",
            post=post,
            to_root="../../",
            title=self.rewriter.rewrite_string(post["Title"]),
            **self.global_context,
        )

    def get_all_questions_for_page(self, page):
        """All tags listing HTML for ZIM"""
        return self.env.get_template("questions.html").render(
            body_class="questions-page",
            whereis="questions",
            title="Highest Voted Questions",
            popular_tags=self.database.query_set(
                self.database.tags_key(), num=10, scored=False
            ),
            questions=extend_questions(page),
            to_root="./",
            page_obj=page,
            **self.global_context,
        )

    def get_all_tags_for_page(self, page):
        """All tags listing HTML for ZIM"""

        def extend_tags(tags):
            for tag in tags:
                yield (tag[0], tag[1], self.database.get_tag_detail(tag[0], "excerpt"))

        return self.env.get_template("tags.html").render(
            body_class="tags-page",
            whereis="tags",
            tags=extend_tags(page),
            to_root="./",
            title="Tags",
            page_obj=page,
            **self.global_context,
        )

    def get_tag_for_page(self, tag, page):
        """Single Tag page HTML for ZIM"""
        return self.env.get_template("tag.html").render(
            body_class="tagged-questions-page",
            whereis="questions",
            to_root="../../",
            title=f"Highest Voted '{tag}' Questions",
            questions=extend_questions(page),
            page_obj=page,
            nb_questions=self.database.get_numquestions_for_tag(tag),
            **self.global_context,
            **self.database.get_tag_full(tag),
        )

    def get_user(self, user):
        """User profile HTML for ZIM"""
        return self.env.get_template("user.html").render(
            body_class="user-page",
            whereis="users",
            to_root="../../",
            title=f"User {user['DisplayName']}",
            **self.global_context,
            **user,
        )

    def get_users_for_page(self, page):
        """All users listing HTML for ZIM"""

        def extend_users(users):
            for user_id in users:
                yield get_user_details(user_id=user_id)

        return self.env.get_template("users.html").render(
            body_class="users-page",
            whereis="users",
            users=extend_users(page),
            to_root="./",
            title="Users",
            page_obj=page,
            **self.global_context,
        )

    def get_about_page(self):
        total_questions = self.database.get_set_count(self.database.questions_key())
        stats = self.database.get_questions_stats()
        percent_answered = stats["nb_answered"] / total_questions
        return self.env.get_template("about.html").render(
            body_class="about-page",
            whereis="about",
            to_root="./",
            title="About",
            dump_date=self.conf.dump_date.strftime("%B %Y"),
            total_questions=total_questions,
            nb_answers=stats["nb_answers"],
            nb_answered=stats["nb_answered"],
            percent_answered=percent_answered * 100,
            total_users=self.database.nb_users,
            total_tags=self.database.get_set_count(self.database.tags_key()),
            **self.global_context,
        )
