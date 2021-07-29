#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

""" Temporary Store of data that needs to be reused in a later step

    Users details must be stored so we can use user names when building post pages
    but posts only reference Users's Ids for instance.
"""

import json
import time
import datetime
import threading
import collections
from typing import Union, Iterator, Tuple

import redis
import bidict
import snappy

from .shared import Global
from .html import get_text
from ..constants import UTF8, NB_PAGINATED_USERS


class TopDict(collections.UserDict):
    """A fixed-sized dict that keeps only the highest values"""

    def __init__(self, maxlen: int):
        super().__init__()
        self.maxlen = maxlen

    def __setitem__(self, key, value):
        with threading.Lock():
            # we're full, might not accept value
            if len(self) >= self.maxlen:
                # value is bellow our min, don't care
                min_val = min(self.values())
                if value < min_val:
                    return

                # value should be in top, let's remove our min to allow it
                min_key = list(self.keys())[list(self.values()).index(min_val)]
                del self[min_key]
            super().__setitem__(key, value)

    def sorted(self):
        return [k for k, _ in sorted(self.items(), key=lambda x: x[1], reverse=True)]


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

    commit_every = 1000
    record_on_main_thread = False

    def __init__(self):
        self.nb_seen = 0

    def initialize(self):
        """to override: initialize database"""

    @property
    def should_commit(self) -> bool:
        """whether to commit now

        This impl. compares `self.nb_seen` with `commit_every` constant"""
        return self.nb_seen % self.commit_every == 0

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

        def decode_results(results):
            for result in results:
                if scored:
                    yield (result[0].decode(UTF8), result[1])
                else:
                    yield result.decode(UTF8)

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
        return decode_results(func(**kwargs))


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
        return f"TE:{name}"

    @staticmethod
    def tag_desc_key(name):
        return f"TD:{name}"

    @classmethod
    def tag_detail_key(cls, name: str, field: str):
        return {
            "excerpt": cls.tag_excerpt_key(name),
            "description": cls.tag_desc_key(name),
        }.get(field)

    def record_tag(self, tag: dict):
        """record tag name in sorted set by Count (nb questions using it)

        Also updates the tag_details_ids with Excerpt/Desc Ids for later use"""

        # record excerpt and wiki content post IDs in mapping
        if tag.get("ExcerptPostId"):
            self.tags_details_ids[tag["ExcerptPostId"]] = tag["TagName"]
        if tag.get("WikiPostId"):
            self.tags_details_ids[tag["WikiPostId"]] = tag["TagName"]

        # record tag Id
        self.tags_ids[int(tag["Id"])] = tag["TagName"]

        # update our sorted set of tags
        self.pipe.zadd(self.tags_key(), mapping={tag["TagName"]: tag["Count"]}, nx=True)

        self.bump_seen(2)
        self.commit_maybe()

    def record_tag_detail(self, name: str, field: str, content: str):
        """insert or update tag row for excerpt or description"""
        self.pipe.set(self.tag_detail_key(name, field), content)
        self.bump_seen()
        self.commit_maybe()

    def clear_tags_mapping(self):
        """releases the PostId/Type mapping used to filter usedful posts"""
        del self.tags_details_ids

    def clear_extra_tags_questions_list(self, at_most: int):
        """only keep at_most question IDs per tag in the database

        Those T:{post_id} ordered sets are used to build per-tag list of questions
        and those are paginated up to some arbitrary value so it makes no sense
        to keep more than this number"""

        # don't use pipeline as those commands are RAM-hungry on redis side and
        # we don't want to stack them up
        for tag in self.tags_ids.inverse.keys():
            self.conn.zremrangebyrank(self.tag_key(tag), 0, -(at_most + 1))

    def get_tag_id(self, name: str) -> int:
        """Tag ID for its name"""
        try:
            return self.tags_ids.inverse[name]
        except KeyError:
            return None

    def get_tag_name_for(self, tag_id: int) -> str:
        return self.tags_ids[tag_id]

    def get_numquestions_for_tag(self, name: str) -> int:
        """Total number of questions using tag by name

        Stored as score of tag entry in main tags zset"""
        return int(self.conn.zscore(self.tags_key(), name))

    def get_tag_detail(self, name: str, field: str) -> str:
        """single detail (excerpt or description) for a tag"""
        detail = self.conn.get(self.tag_detail_key(name, field))
        return detail.decode(UTF8) if detail is not None else None

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

    def record_user(self, user: dict):
        """record basic user details to MEM at U:{id} key

        Name, Reputation, NbGoldBages, NbSilverBadges, NbBronzeBadges"""

        # record score in top mapping
        self._top_users[user["Id"]] = user["Reputation"]

        # record profile details into individual key
        self.pipe.set(
            self.user_key(user["Id"]),
            snappy.compress(
                json.dumps(
                    (
                        user["DisplayName"],
                        user["Reputation"],
                        user["nb_gold"],
                        user["nb_silver"],
                        user["nb_bronze"],
                    )
                )
            ),
        )

        self.bump_seen()
        self.commit_maybe()

    def cleanup_users(self):
        """frees list of active users that we won't need anymore. sets nb_users"""
        self.nb_users = len(self._all_users)
        del self._all_users
        self.top_users = self._top_users.sorted()
        del self._top_users

    def get_user_full(self, user_id: int) -> str:
        """All recorded information for a UserId

        id, name, rep, nb_gold, nb_silver, nb_bronze"""
        user = self.conn.get(self.user_key(user_id))
        if not user:
            return None
        user = json.loads(snappy.decompress(user))
        return {
            "id": user_id,
            "name": user[0],
            "rep": user[1],
            "nb_gold": user[2],
            "nb_silver": user[3],
            "nb_bronze": user[4],
        }

    def is_active_user(self, user_id):
        """whether a user_id is considered active (has interaction in content)

        WARN: only valid during Users listing step"""
        return user_id in self._all_users


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

        # update set of users_ids (users with activity)
        for user_id in post.get("users_ids"):
            self._all_users.add(user_id)

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

        # store int for user Ids (most use) to save some space in redis
        if post.get("OwnerUserId"):
            post["OwnerName"] = int(post["OwnerUserId"])

        # store question details
        self.pipe.setnx(
            self.question_key(post["Id"]),
            snappy.compress(
                json.dumps(
                    (
                        post["CreationTimestamp"],
                        post["OwnerName"],
                        post["has_accepted"],
                        post["nb_answers"],
                        # Tag ID can be None in the event a Tag existed and was not used
                        # but got used first during the dumping process, after the Tags
                        # were dumped but before questions we fully dumped.
                        # SO Tag `imac` in 2021-06 dumps for instance
                        [
                            self.get_tag_id(tag)
                            for tag in post.get("Tags", [])
                            if self.get_tag_id(tag)
                        ],
                    )
                )
            ),
        )

        # record question's meta: ID: title, excerpt for use in home and tag pages
        self.pipe.set(
            self.question_details_key(post["Id"]),
            snappy.compress(
                json.dumps((post["Title"], get_text(post["Body"], strip_at=250)))
            ),
        )

        self.bump_seen(4 + len(post.get("Tags", [])))
        self.commit_maybe()

    def record_questions_stats(
        self, nb_answers: int, nb_answered: int, nb_accepted: int
    ):
        """store total number of answers through dump"""
        self.pipe.set(
            self.questions_stats_key(),
            json.dumps((nb_answers, nb_answered, nb_accepted)),
        )

        self.bump_seen()
        self.commit_maybe()

    def get_question_title_desc(self, post_id: int) -> dict:
        """dict including title and excerpt fo a question by PostId"""
        try:
            data = json.loads(
                snappy.decompress(self.conn.get(self.question_details_key(post_id)))
            )
        except Exception:
            # we might not have a record for that post_id:
            # - post_id can be erroneous (from a mistyped link)
            # - post_id can reference an excluded question (no answer)
            data = [None, None]
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
            ) = json.loads(snappy.decompress(post_entry))
            item["creation_date"] = datetime.datetime.fromtimestamp(
                item["creation_date"]
            )
            item["tags"] = [self.get_tag_name_for(t) for t in item["tags"]]
        return item

    def get_question_score(self, post_id: int) -> int:
        """Score of a question by PostId"""
        return int(self.conn.zscore(self.questions_key(), int(post_id)))

    def question_has_accepted_answer(self, post_id: int) -> bool:
        """Whether the question has an accepted answer or not"""
        post_entry = self.conn.get(self.question_key(post_id))
        if post_entry:
            return json.loads(snappy.decompress(post_entry))[2]  # 3rd entry, accepted
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
        self.connections = {}
        self.pipes = {}
        self.nb_seens = {}

        super().__init__()

        # temp set to hold all active users' IDs
        self._all_users = set()
        # temp dict to hold `n` most active users' ID:score
        self._top_users = TopDict(NB_PAGINATED_USERS)
        # total number of active users
        self.nb_users = 0

        self.tags_details_ids = {}
        # bidirectionnal Tag ID:name and (as inverse) name:ID mapping
        self.tags_ids = bidict.bidict()

        if initialize:
            self.initialize()

    @property
    def conn(self):
        """thread-specific Redis connection"""
        try:
            return self.connections[threading.get_ident()]
        except KeyError:
            self.connections[threading.get_ident()] = redis.StrictRedis.from_url(
                Global.conf.redis_url.geturl(), charset=UTF8, decode_responses=False
            )
            return self.connections[threading.get_ident()]

    @property
    def pipe(self):
        """thread-specific Pipeline for this thread-specific connection"""
        try:
            return self.pipes[threading.get_ident()]
        except KeyError:
            self.pipes[threading.get_ident()] = self.conn.pipeline()
            return self.pipes[threading.get_ident()]

    @property
    def nb_seen(self):
        """thread-specific number of items seen"""
        try:
            return self.nb_seens[threading.get_ident()]
        except KeyError:
            self.nb_seens[threading.get_ident()] = 0
            return self.nb_seens[threading.get_ident()]

    @nb_seen.setter
    def nb_seen(self, value):
        self.nb_seens[threading.get_ident()] = value

    def initialize(self):
        # test connection
        self.conn.get("NOOP")

        # clean up potentially existing DB
        if not Global.conf.open_shell:
            self.conn.flushdb()

    def make_dummy_query(self):
        self.pipe.get("")

    def commit(self, done=False):
        self.pipe.execute()

        # make sure we've commited pipes on all thread-specific pipelines
        if done:
            time.sleep(2)  # prevent last-thread created while we iterate on mini domain
            for pipe in self.pipes.values():
                pipe.execute()

    def purge(self):
        """ask redis to reclaim dirty pages space. Effective only on Linux"""
        self.conn.memory_purge()

    def teardown(self):
        self.pipe.execute()
        self.conn.close()

    def remove(self):
        """flush database"""
        if not Global.conf.keep_redis:
            self.conn.flushdb()


def get_database() -> Database:
    return RedisDatabase(initialize=True)
