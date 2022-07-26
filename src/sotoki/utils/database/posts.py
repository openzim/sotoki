#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import datetime
import json

import snappy

from ..html import get_text


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
            self._all_users_ids.add(user_id)

        # add this postId to the ordered list of questions sorted by score
        self.pipe.zadd(
            self.questions_key(), mapping={post["Id"]: post["Score"]}, nx=True
        )

        # Add this question's PostId to the ordered questions sets of all its tags
        for tag in post.get("Tags", []):
            self.pipe.zadd(
                self.tag_key(tag), mapping={post["Id"]: post["Score"]}, nx=True
            )

        # store int for user Ids (most use) to save some space in redis
        # names stored as str thus belong to deleted users. this prevents del users
        # with a name such as "3200" to be considered User#3200
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
                snappy.decompress(self.safe_get(self.question_details_key(post_id)))
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
            score = self.safe_zscore(self.questions_key(), post_id)

        item = self.get_question_title_desc(post_id) or {}
        item["score"] = score
        item["id"] = post_id

        post_entry = self.safe_get(self.question_key(post_id))
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
        return int(self.safe_zscore(self.questions_key(), int(post_id)))

    def question_has_accepted_answer(self, post_id: int) -> bool:
        """Whether the question has an accepted answer or not"""
        post_entry = self.safe_get(self.question_key(post_id))
        if post_entry:
            return json.loads(snappy.decompress(post_entry))[2]  # 3rd entry, accepted
        return False

    def get_questions_stats(self) -> int:
        """total number of answers in dump (not in DB)"""
        try:
            item = json.loads(self.safe_get(self.questions_stats_key()))
        except Exception:
            item = [0, 0, 0]
        return {"nb_answers": item[0], "nb_answered": item[1], "nb_accepted": item[2]}
