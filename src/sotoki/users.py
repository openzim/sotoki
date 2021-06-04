#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu


""" Generate one+ page per Tag in the ZIM.

    Each tag page is a list of all questions related to it"""

from slugify import slugify

from .constants import getLogger
from .utils.generator import Generator, Walker

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

    def startElement(self, name, attrs):
        if name == "row":
            # store xml data until we're through with the <row /> node
            self.user = dict(attrs.items())

        elif name == "badges":
            # prepare a space to record badges for current user
            self.user["badges"] = {}

        elif name == "badge":
            # record how many times a single badge was set on this user
            if attrs.get("name") in self.user["badges"].keys():
                self.user["badges"][attrs.get("name")] += 1
            else:
                self.user["badges"][attrs.get("name")] = 1

    def endElement(self, name):
        if name == "row":
            self.processor(item=self.user)
            self.recorder(item=self.user)


class UserGenerator(Generator):
    walker = UsersWalker

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fpath = self.conf.build_dir / "users_with_badges.xml"

    def recorder(self, item):
        self.database.record_user(user=item)

    def processor(self, item):
        user = item

        # TODO: check better way to handle no user profile
        # TODO: check whether we need that slug redirect. from in-posts links?
        # TODO: check whether we need the title on the redirect (save the index)
        if not self.conf.without_user_profiles:
            slug = slugify(user["DisplayName"])
            with self.creator_lock:
                self.creator.add_redirect(
                    path=f'user/{user["Id"]}/{slug}',
                    target_path=f'user/{user["Id"]}',
                    # title=user["DisplayName"],
                )

        with self.creator_lock:
            self.creator.add_item_for(
                path=f'user/{user["Id"]}',
                title=user["DisplayName"],
                content=user.get("AboutMe", "n/a"),
                mimetype="text/html",
            )
