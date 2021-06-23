#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu


from slugify import slugify

from .constants import getLogger
from .renderer import SortedSetPaginator
from .utils.generator import Generator, Walker
from .utils.misc import get_short_hash

logger = getLogger()


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
            # only if processing wasn't skiped by generated (user accepted)
            if self.processor(item=self.user) and self.conf.with_user_identicons:
                profile_url = self.user.get("ProfileImageUrl")
                if profile_url:
                    self.imager.defer(
                        url=profile_url,
                        path=f"images/user/{self.user['Id']}",
                        is_profile=True,
                    )

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
            return
        super().processor_callback(item=item)
        return True

    def processor(self, item):
        user = item
        user["Id"] = int(user["Id"])

        if not self.database.is_active_user(user["Id"]):
            return

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

        with self.lock:
            self.creator.add_item_for(
                path=f'users/{user["Id"]}',
                title=f'User {user["DisplayName"]}',
                content=self.renderer.get_user(user),
                mimetype="text/html",
            )

        with self.lock:
            self.creator.add_redirect(
                path=f'users/{user["Id"]}/{user["slug"]}',
                target_path=f'users/{user["Id"]}',
            )

    def generate_users_page(self):
        paginator = SortedSetPaginator(
            self.database.users_key(), per_page=36, at_most=3600
        )
        for page_number in paginator.page_range:
            page = paginator.get_page(page_number)
            with self.lock:
                # we don't index same-title page for all paginated pages
                # instead we index the redirect to the first page
                self.creator.add_item_for(
                    path=f"users_page={page_number}",
                    content=self.renderer.get_users_for_page(page),
                    mimetype="text/html",
                )
        with self.lock:
            self.creator.add_redirect(
                path="users",
                target_path="users_page=1",
                title="Users",
            )
