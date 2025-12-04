#!/usr/bin/env python

from typing import Any

from slugify import slugify
from zimscraperlib.typing import Callback

from sotoki.constants import (
    NB_PAGINATED_USERS,
    NB_USERS_PER_PAGE,
)
from sotoki.renderer import ListPaginator
from sotoki.utils.generator import Generator, Walker
from sotoki.utils.misc import get_short_hash
from sotoki.utils.shared import context, logger, shared


class UsersWalker(Walker):
    """users_with_badges SAX parser

    Schema:

        <root>
        <row Id="" Reputation="" CreationDate="" DisplayName=""
             LastAccessDate="2" WebsiteUrl="" Location="" AboutMe="" Views="" UpVotes=""
             DownVotes="" AccountId="" ><badges><badge Id=""
             UserId="" Name="" Date="" Class="" TagBased="" /></badges></row>
        </root>"""

    def startDocument(self):  # noqa: N802
        self.seen = 0

    def startElement(self, name, attrs):  # noqa: N802
        if name == "row":
            # store xml data until we're through with the <row /> node
            self.user: dict[str, Any] = dict(attrs.items())

        elif name == "badges":
            # prepare a space to record badges for current user
            self.user["badges"] = {"1": {}, "2": {}, "3": {}}

        elif name == "badge":
            # record how many times a single badge was set on this user
            if attrs.get("Name") in self.user["badges"][attrs.get("Class")].keys():
                self.user["badges"][attrs.get("Class")][attrs.get("Name")] += 1
            else:
                self.user["badges"][attrs.get("Class")][attrs.get("Name")] = 1

    def endElement(self, name):  # noqa: N802
        if name == "row":
            self.processor(item=self.user)
            self.seen += 1
            if self.seen % 1000 == 0:
                logger.debug(f"Seen {self.seen}")


class UserGenerator(Generator):

    @property
    def walker(self):
        return UsersWalker

    @property
    def fpath(self):
        return shared.build_dir / "users_with_badges.xml"

    def processor_callback(self, item):
        if not shared.usersdatabase.is_active_user(int(item["Id"])):
            return False  # user was skipped
        super().processor_callback(item=item)

    def processor(self, item):
        user = item
        user["Id"] = int(user["Id"])

        if context.without_names:
            user["DisplayName"] = get_short_hash(user["DisplayName"])

        user["slug"] = slugify(user["DisplayName"])
        user["deleted"] = False
        user["Reputation"] = int(user["Reputation"])
        user["nb_gold"] = sum(user.get("badges", {}).get("1", {}).values())
        user["nb_silver"] = sum(user.get("badges", {}).get("2", {}).values())
        user["nb_bronze"] = sum(user.get("badges", {}).get("3", {}).values())
        shared.usersdatabase.record_user(user=user)

        if context.without_user_profiles:
            return

        # prepare user page outside Lock to prevent dead-lock on image discovery
        user_page = shared.renderer.get_user(user)
        with shared.lock:
            shared.creator.add_item_for(
                path=f'users/{user["Id"]}/{user["slug"]}',
                title=f'User {user["DisplayName"]}',
                content=user_page,
                mimetype="text/html",
                is_front=True,
                callbacks=[Callback(func=self.release)],
            )
        del user_page

    def generate_users_page(self):
        paginator = ListPaginator(
            shared.usersdatabase.top_users,
            per_page=NB_USERS_PER_PAGE,
            at_most=NB_PAGINATED_USERS,
        )
        for page_number in paginator.page_range:
            page = paginator.get_page(page_number)
            with shared.lock:
                page_content = shared.renderer.get_users_for_page(page)
                # we don't index same-title page for all paginated pages
                # instead we index the redirect to the first page
                shared.creator.add_item_for(
                    path="users" if page_number == 1 else f"users_page={page_number}",
                    content=page_content,
                    mimetype="text/html",
                    title="Users" if page_number == 1 else None,
                    is_front=page_number == 1,
                )
                del page_content
        with shared.lock:
            shared.creator.add_redirect(
                path="users_page=1",
                target_path="users",
                is_front=False,
            )
