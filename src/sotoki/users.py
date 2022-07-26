#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from slugify import slugify

from .constants import (
    NB_PAGINATED_USERS,
    NB_USERS_PER_PAGE,
)
from .utils.shared import logger
from .renderer import ListPaginator
from .utils.generator import Generator, Walker
from .utils.misc import get_short_hash


class UsersWalker(Walker):
    """users_with_badges SAX parser

    Schema:

        <root>
        <row Id="" Reputation="" CreationDate="" DisplayName=""
             LastAccessDate="2" WebsiteUrl="" Location="" AboutMe="" Views="" UpVotes=""
             DownVotes="" ProfileImageUrl="" AccountId="" ><badges><badge Id=""
             UserId="" Name="" Date="" Class="" TagBased="" /></badges></row>
        </root>"""

    def startDocument(self):
        self.seen = 0

    def startElement(self, name, attrs):
        if name == "row":
            # store xml data until we're through with the <row /> node
            self.user = dict(attrs.items())

        elif name == "badges":
            # prepare a space to record badges for current user
            self.user["badges"] = {"1": {}, "2": {}, "3": {}}

        elif name == "badge":
            # record how many times a single badge was set on this user
            if attrs.get("Name") in self.user["badges"][attrs.get("Class")].keys():
                self.user["badges"][attrs.get("Class")][attrs.get("Name")] += 1
            else:
                self.user["badges"][attrs.get("Class")][attrs.get("Name")] = 1

    def endElement(self, name):
        if name == "row":
            self.processor(item=self.user)
            self.seen += 1
            if self.seen % 1000 == 0:
                logger.debug(f"Seen {self.seen}")


class UserGenerator(Generator):
    walker = UsersWalker

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fpath = self.conf.build_dir / "users_with_badges.xml"

    def processor_callback(self, item):
        if not self.database.is_active_user(int(item["Id"])):
            return False  # user was skipped
        super().processor_callback(item=item)

    def processor(self, item):
        user = item
        user["Id"] = int(user["Id"])

        if self.conf.without_names:
            user["DisplayName"] = get_short_hash(user["DisplayName"])

        user["slug"] = slugify(user["DisplayName"])
        user["deleted"] = False
        user["Reputation"] = int(user["Reputation"])
        user["nb_gold"] = sum(user.get("badges", {}).get("1", {}).values())
        user["nb_silver"] = sum(user.get("badges", {}).get("2", {}).values())
        user["nb_bronze"] = sum(user.get("badges", {}).get("3", {}).values())
        self.database.record_user(user=user)

        if self.conf.without_user_profiles:
            return

        # prepare user page outside Lock to prevent dead-lock on image discovery
        user_page = self.renderer.get_user(user)
        with self.lock:
            self.creator.add_item_for(
                path=f'users/{user["Id"]}/{user["slug"]}',
                title=f'User {user["DisplayName"]}',
                content=user_page,
                mimetype="text/html",
                is_front=True,
                callback=self.release,
            )
        del user_page

        if not self.conf.with_user_identicons:
            return

        profile_url = user.get("ProfileImageUrl")
        if profile_url:
            self.imager.defer(
                url=profile_url,
                path=f"users/profiles/{user['Id']}.webp",
                is_profile=True,
            )

    def generate_users_page(self):
        paginator = ListPaginator(
            self.database.top_users,
            per_page=NB_USERS_PER_PAGE,
            at_most=NB_PAGINATED_USERS,
        )
        for page_number in paginator.page_range:
            page = paginator.get_page(page_number)
            with self.lock:
                page_content = self.renderer.get_users_for_page(page)
                # we don't index same-title page for all paginated pages
                # instead we index the redirect to the first page
                self.creator.add_item_for(
                    path="users" if page_number == 1 else f"users_page={page_number}",
                    content=page_content,
                    mimetype="text/html",
                    title="Users" if page_number == 1 else None,
                    is_front=page_number == 1,
                )
                del page_content
        with self.lock:
            self.creator.add_redirect(
                path="users_page=1",
                target_path="users",
                is_front=False,
            )
