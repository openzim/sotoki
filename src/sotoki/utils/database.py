#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

""" Temporary Store of data that needs to be reused in a later step

    Users details must be stored so we can use user names when building post pages
    but posts only reference Users's Ids for instance.
"""

import json
import pathlib
import urllib.parse
from typing import Union, Iterator, Tuple

import redis

from ..constants import getLogger, Global
from ..utils.html import get_text

logger = getLogger()


class Database:
    """Database Interface

    Should allow us to quickly test alternative backends

    General principles:
      - DB can be initialized (setup of underlyig layers)
      - DB's details not exposed so this contains all DB interactions
      - Assume there's usually a notion of transactions that saves round-trips
        - begin()
        - commit() should_commit commit_maybe()
      - Might require some post-usage cleanup: teardown()
      - Should be able to remove data (it's TEMP only)"""

    COMMIT_EVERY = 20000
    record_on_main_thread = False

    def __init__(self):
        self.nb_seen = 0

    @property
    def build_dir(self) -> pathlib.Path:
        # file:// URI requires a full path
        return Global.conf.build_dir.resolve()

    def initialize(self):
        """to override: initialize database"""

    @property
    def should_commit(self) -> bool:
        """whether to commit now

        This impl. compares `self.nb_seen` with `COMMIT_EVERY` constant"""
        return self.nb_seen % self.COMMIT_EVERY == 0

    def commit_maybe(self):
        """commit() should should_commit allows it"""
        if self.should_commit:
            self.commit()

    def begin(self):
        """to override: start a session/transaction"""

    def bump_seen(self, by: int = 1):
        self.nb_seen += by

    def make_dummy_query(self):
        """to override: used to ensure a started session can be closed safely"""

    def commit(self):
        """to override: end a session"""

    def teardown(self):
        """to override: release database"""

    def remove(self):
        """to override: remove database data"""

    def get_set_count(self, set_name: str) -> int:
        """Number of recorded entries in set"""
        return self.conn.zcard(set_name)

    def query_set(
        self,
        set_name: str,
        start: int = 0,
        num: int = None,
        desc: bool = True,
        scored: bool = True,
    ) -> Iterator[Union[Tuple[object, int], object]]:
        """Query entries in named sorted set"""

        func = getattr(self.conn, "zrevrangebyscore" if desc else "zrangebyscore")

        if num is None:
            num = self.conn.zcard(set_name)

        kwargs = {
            "name": set_name,
            "max": "+inf",
            "min": "-inf",
            "start": start,
            "num": num,
            "withscores": scored,
            "score_cast_func": int,
        }
        return func(**kwargs)


class TagsDatabaseMixin:
    """Tags related Database operations

    Tags are mainly stored in a single `tags` sorted set which contains
    the tag name string and is scored via the Count tag value which represents
    the number of posts using it (aka popularity)

    In addition, we individually keep 2 keys for each tag:
    - T:E:{name}: the excerpt str text for the tag
    - T:D:{name}: the description str text for the tag
    - T:ID:{name}: the Id of the tag, used to generate redirect to tag page from ID

    We also *temporarily* store as a dict inside this object a all PostIds: Tag
    corresponding to the `ExcerptPostId` and `WikiPostId` found in Tags.
    This mapping is then used when walking through wiki and excerpt dedicated
    files so we record only those we need"""

    @staticmethod
    def tag_key(name):
        return f"T:{name}"

    @staticmethod
    def tags_key():
        return "tags"

    @staticmethod
    def tag_excerpt_key(name):
        return f"T:E:{name}"

    @staticmethod
    def tag_desc_key(name):
        return f"T:D:{name}"

    @staticmethod
    def tag_id_key(name):
        return f"T:ID:{name}"

    @classmethod
    def tag_detail_key(cls, name: str, field: str):
        return {
            "excerpt": cls.tag_excerpt_key(name),
            "description": cls.tag_desc_key(name),
            "id": cls.tag_id_key(name),
        }.get(field)

    def record_tag(self, tag: dict):
        """record tag name in sorted set by Count (nb questions using it)

        Also updates the tag_details_ids with Excerpt/Desc Ids for later use"""

        self.bump_seen()

        # record excerpt and wiki content post IDs in mapping
        if tag.get("ExcerptPostId"):
            self.tags_details_ids[tag["ExcerptPostId"]] = tag["TagName"]
        if tag.get("WikiPostId"):
            self.tags_details_ids[tag["WikiPostId"]] = tag["TagName"]

        # record tag Id
        self.pipe.set(self.tag_id_key(tag["TagName"]), int(tag["Id"]))

        # update our sorted set of tags
        self.pipe.zadd(self.tags_key(), mapping={tag["TagName"]: tag["Count"]}, nx=True)

        self.commit_maybe()

    def record_tag_detail(self, name: str, field: str, content: str):
        """insert or update tag row for excerpt or description"""
        self.pipe.set(self.tag_detail_key(name, field), content)

    def clear_tags_mapping(self):
        """releases the PostId/Type mapping used to filter usedful posts"""
        del self.tags_details_ids

    def get_tag_detail(self, name: str, field: str) -> str:
        """single detail (excerpt or description) for a tag"""
        return self.conn.get(self.tag_detail_key(name, field))

    def get_tag_details(self, name) -> dict:
        """dict of all the recorded known details for tag"""
        return {
            "excerpt": self.get_tag_detail(name, "excerpt"),
            "description": self.get_tag_detail(name, "description"),
        }

    def get_tag_full(self, name: str, score: int = None) -> dict:
        """All recorded information for a tag

        name, score, excerpt?, description?"""
        if score is None:
            score = self.conn.zscore(self.tags_key(), name)

        item = self.get_tag_details(name) or {}
        item["score"] = score
        item["name"] = name
        return item


class UsersDatabaseMixin:
    """Users related Database operations

    We mainly store some basic profile-details for each user so that we can display
    the user card wherever needed (in questions listing and inside question pages).
    Most important datapoint is the name (DisplayName) followed by Reputation (a score)
    We also store the number of badges owned by class (gold, silver, bronze) as this
    is this is an extension to thre reputation.

    We store this as a list in U:{userId} key for each user

    We also have a sorted set of UserIds scored by Reputation.
    Because we first go through Posts to eliminate all Users without interactions,
    we first gather an un-ordered list of UserIds: a non-sorted set.
    Once we're trhough with this step, we create the sorted one and trash the first one.

    List of users is essential to exclude users without interactions, so we don't
    create pages for them.

    Sorted list of users allows us to build a page with the list of Top users.

    Note: interactions associated with Deleted users are recorded to a name and not
    a UserId.

    Note: we don't track User's profile image URL as we store images in-Zim at a fixed
    location based on UserId."""

    @staticmethod
    def user_key(user_id):
        return f"U:{user_id}"

    @staticmethod
    def users_key():
        return "users"

    @staticmethod
    def unsorted_users_key():
        return "unsorted_users"

    def record_user(self, user: dict):
        """record basic user details to MEM at U:{id} key

        Name, Reputation, NbGoldBages, NbSilverBadges, NbBronzeBadges"""

        self.bump_seen()

        # record profile details into individual key
        self.pipe.set(
            self.user_key(user["Id"]),
            json.dumps(
                (
                    user["DisplayName"],
                    user["Reputation"],
                    user["nb_gold"],
                    user["nb_silver"],
                    user["nb_bronze"],
                )
            ),
        )
        self.commit_maybe()

    def sort_users(self):
        """convert our unsorted users ids set into a sorted one
        now that we have individual scores for each"""

        nb_items = 100  # batch number to pop/insert together
        user_ids = self.conn.spop(self.unsorted_users_key(), nb_items)
        while user_ids:
            self.pipe.zadd(
                self.users_key(),
                mapping={
                    uid: self.get_reputation_for(uid)
                    for uid in user_ids
                    if uid is not None
                },
                nx=True,
            )

            self.bump_seen(nb_items)
            self.commit_maybe()

            user_ids = self.conn.spop(nb_items)
        self.users_are_sorted = True

    def get_user_full(self, user_id: int) -> str:
        """All recorded information for a UserId

        id, name, rep, nb_gold, nb_silver, nb_bronze"""
        user = self.conn.get(self.user_key(user_id))
        if not user:
            logger.warning(f"get_user_full('{user_id}') is None")
            return None
        user = json.loads(user)
        return {
            "id": user_id,
            "name": user[0],
            "rep": user[1],
            "nb_gold": user[2],
            "nb_silver": user[3],
            "nb_bronze": user[4],
        }

    def is_active_user(self, user_id):
        """whether a user_id is considered active (has interaction in content)"""
        # depending on whether we've pasted the sorting step or not, retrieval differs
        if self.users_are_sorted:
            return self.conn.zscore(self.users_key(), user_id) is not None
        return self.conn.sismember(self.unsorted_users_key(), user_id)

    def get_reputation_for(self, user_id: int):
        """Reputation score for a user_id"""
        user = self.conn.get(self.user_key(user_id))
        if not user:
            return 0
        return json.loads(user)[1]


class PostsDatabaseMixin:
    """Posts related Database operations

    Both Questions and Answers are `Posts` in SE. The Database doesn't care about
    answers as those are processed solely using XML Data.

    We mostly store list of questions:

    - A `questions` ordered set of PostId ordered by question Score (votes).
    We use this to build the list of questions for the home page.

    - A `T:{tag}` ordered set of PostId ordered by question Score for each Tag.
    We use this to build the list of questions inside individual Tag pages.

    - A `Q:{id}` containing a JSON list of CreationDate, OwnerName and a bool of whether
    this question has an accepted answer.
    We use those to expand post-info when building list of questions

    - A `QD:{id}` containing a JSON list of Title, Excerpt for all questions. This alone
    can take up to 9GB for StackOverflow.
    We use this to display title and excerpt for posts in questions listing.

    Note: When using the --without-unanswered flag, nothing is recorded for questions
    with a zero count of answers."""

    @staticmethod
    def question_key(post_id):
        return f"Q:{post_id}"

    @staticmethod
    def question_details_key(post_id):
        return f"QD:{post_id}"

    @staticmethod
    def questions_key():
        return "questions"

    @staticmethod
    def questions_stats_key():
        return "nb_answers"

    def record_question(self, post: dict):
        self.bump_seen()

        # update set of users_ids (users with activity)
        if post.get("users_ids"):
            if None in post["users_ids"]:
                logger.error(f"None in users_ids for {post['Id']}")
            self.pipe.sadd(self.unsorted_users_key(), *post["users_ids"])

        # add this postId to the ordered list of questions sorted by score
        self.pipe.zadd(
            self.questions_key(), mapping={post["Id"]: post["Score"]}, nx=True
        )

        # Add this question's PostId to the ordered questions sets of all its tags
        for tag in post.get("Tags", []):
            self.pipe.zadd(
                self.tag_key(tag), mapping={post["Id"]: post["Score"]}, nx=True
            )

        # TODO: just storing name instead of id is not safe. a deleted user could
        # have a name such as "3200" and that would be rendered as User#3200
        if not post.get("OwnerUserId"):
            logger.debug(f"No OwnerUserId for {post['Id']}")
        # store question details
        self.pipe.setnx(
            self.question_key(post["Id"]),
            json.dumps(
                (
                    post["CreationDate"],
                    post["OwnerName"],
                    post["has_accepted"],
                    post["nb_answers"],
                    post.get("Tags", []),
                )
            ),
        )

        # record question's meta: ID: title, excerpt for use in home and tag pages
        self.pipe.set(
            self.question_details_key(post["Id"]),
            json.dumps((post["Title"], get_text(post["Body"], strip_at=250))),
        )

        self.commit_maybe()

    def record_questions_stats(
        self, nb_answers: int, nb_answered: int, nb_accepted: int
    ):
        """store total number of answers through dump"""
        self.pipe.set(
            self.questions_stats_key(),
            json.dumps((nb_answers, nb_answered, nb_accepted)),
        )
        self.commit_maybe()

    def get_question_title_desc(self, post_id: int) -> dict:
        """dict including title and excerpt fo a question by PostId"""
        try:
            data = json.loads(self.conn.get(self.question_details_key(post_id)))
        except Exception:
            # we might not have a record for that post_id:
            # - post_id can be erroneous (from a mistyped link)
            # - post_id can reference an excluded question (no answer)
            data = ["n/a", "n/a"]
        return {"title": data[0], "excerpt": data[1]}

    def get_question_details(self, post_id, score: int = None):
        """Detailed information for a question

        is, score, creation_date, owner_user_id, has_accepted"""
        if score is None:
            score = self.conn.zscore(self.questions_key(), post_id)

        item = self.get_question_title_desc(post_id) or {}
        item["score"] = score
        item["id"] = post_id

        post_entry = self.conn.get(self.question_key(post_id))
        if post_entry:
            (
                item["creation_date"],
                item["owner_user_id"],
                item["has_accepted"],
                item["nb_answers"],
                item["tags"],
            ) = json.loads(post_entry)
        return item

    def get_question_score(self, post_id: int) -> int:
        """Score of a question by PostId"""
        return int(self.conn.zscore(self.questions_key(), int(post_id)))

    def question_has_accepted_answer(self, post_id: int) -> bool:
        """Whether the question has an accepted answer or not"""
        post_entry = self.conn.get(self.question_key(post_id))
        if post_entry:
            return json.loads(post_entry)[2]  # 3rd entry, has accepted
        return False

    def get_questions_stats(self) -> int:
        """total number of answers in dump (not in DB)"""
        try:
            item = json.loads(self.conn.get(self.questions_stats_key()))
        except Exception:
            item = [0, 0, 0]
        return {"nb_answers": item[0], "nb_answered": item[1], "nb_accepted": item[2]}


class RedisDatabase(
    Database, TagsDatabaseMixin, UsersDatabaseMixin, PostsDatabaseMixin
):
    def __init__(self, initialize: bool = False):
        super().__init__()

        kwargs = {"charset": "utf-8", "decode_responses": True}
        if Global.conf.redis_url.scheme == "file":
            kwargs.update({"unix_socket_path": Global.conf.redis_url.path})
            if Global.conf.redis_url.query:
                db = (
                    urllib.parse.parse_qs(Global.conf.redis_url.query)
                    .get("db", [])
                    .pop()
                )
                if db is not None:
                    kwargs.update({"db": db})
        elif Global.conf.redis_url.scheme == "redis":
            kwargs.update(
                {
                    "host": Global.conf.redis_url.hostname,
                    "port": Global.conf.redis_url.port,
                    "db": Global.conf.redis_url.path[1:]
                    if len(Global.conf.redis_url.path) > 1
                    else None,
                    "username": Global.conf.redis_url.username,
                    "password": Global.conf.redis_url.password,
                }
            )
        self.conn = redis.StrictRedis(**kwargs)
        self.pipe = self.conn.pipeline()

        self.users_are_sorted = False
        self.tags_details_ids = {}

        if initialize:
            self.initialize()

    def initialize(self):
        # test connection
        self.conn.get("NOOP")

        # clean up potentially existing DB
        self.conn.flushdb()

    def make_dummy_query(self):
        self.pipe.get("")

    def commit(self, done=False):
        self.pipe.execute()

    def teardown(self):
        self.pipe.execute()
        self.conn.close()

    def remove(self):
        """flush database"""
        # TODO: remove
        return
        self.conn.flushdb()


def get_database() -> Database:
    return RedisDatabase(initialize=True)
