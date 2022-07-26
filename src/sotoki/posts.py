#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu
import datetime

from .utils.shared import logger, Global
from .constants import NB_QUESTIONS_PER_PAGE, NB_PAGINATED_QUESTIONS
from .renderer import SortedSetPaginator
from .utils.generator import Generator, Walker
from .utils.html import get_slug_for


def harmonize_post(post: dict):
    post["has_accepted"] = "AcceptedAnswerId" in post
    post["OwnerName"] = post.get("OwnerUserId", post.get("OwnerDisplayName"))
    post["CreationTimestamp"] = int(
        datetime.datetime.fromisoformat(post["CreationDate"]).strftime("%s")
    )


class WalkerWithTrigger(Walker):
    def startDocument(self):
        self.seen = 0

    def check_trigger(self):
        self.seen += 1
        if self.seen % 10000 == 0:
            logger.debug(f"Seen {self.seen}")
            Global.collect()


class FirstPassWalker(WalkerWithTrigger):
    def startElement(self, name, attrs):
        def _user_to_set(aset, field):
            if attrs.get(field):
                aset.add(int(attrs.get(field)))

        # a question
        if name == "post":
            # store xml data until we're through with the <post /> node
            self.post = dict(attrs.items())
            self.post["Id"] = int(self.post["Id"])
            self.post["Score"] = int(self.post["Score"])
            self.post["Tags"] = self.post["Tags"][1:-1].split("><")
            self.post["users_ids"] = set()
            self.post["nb_answers"] = 0
            _user_to_set(self.post["users_ids"], "OwnerUserId")
            _user_to_set(self.post["users_ids"], "LastEditorUserId")
            return

        # opening comments of a question
        if name == "comment":
            _user_to_set(self.post["users_ids"], "UserId")
            return

        # opening answers of a question
        if name == "answer":  # a answer
            _user_to_set(self.post["users_ids"], "OwnerUserId")
            _user_to_set(self.post["users_ids"], "LastEditorUserId")
            self.post["nb_answers"] += 1

    def endElement(self, name):

        if name == "post":
            self.processor(item=self.post)

            # reset data holders
            del self.post

            self.check_trigger()


class PostFirstPasser(Generator):

    walker = FirstPassWalker

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fpath = self.conf.build_dir / "posts_complete.xml"

        self.nb_answers = 0
        self.nb_answered = 0
        self.nb_accepted = 0

    def run(self):
        super().run()
        self.database.record_questions_stats(
            nb_answers=self.nb_answers,
            nb_answered=self.nb_answered,
            nb_accepted=self.nb_accepted,
        )

    def processor(self, item):
        # skip post without answers ; maybe?
        if self.conf.without_unanswered and not item["nb_answers"]:
            self.release()
            return

        harmonize_post(item)

        # update stats
        self.nb_answers += item["nb_answers"]
        if item["has_accepted"]:
            self.nb_accepted += 1
        if item["nb_answers"]:
            self.nb_answered += 1

        self.database.record_question(post=item)

        self.release()


class PostsWalker(WalkerWithTrigger):
    """posts_complete SAX parser

        Schema:

        <post>
        <comments>
            <comment />
        </comments>
        <answers>
            <answer>
                <comments>
                    <comment />
                </comments>
            </answer>
        </answers>
        <links>
            <link />
        </links>
    </post>"""

    def startDocument(self):
        super().startDocument()
        self.currently_in = None
        self.post = {}
        self.comments = []
        self.answers = []

    def startElement(self, name, attrs):
        # a question
        if name == "post":
            # store xml data until we're through with the <post /> node
            self.currently_in = "post"
            self.post = dict(attrs.items())
            self.post["Id"] = int(self.post["Id"])
            self.post["Score"] = int(self.post["Score"])
            self.post["Tags"] = self.post["Tags"][1:-1].split("><")
            self.post["links"] = {"relateds": [], "duplicates": []}
            return

        # opening comments of a question
        if name == "comments" and self.currently_in == "post":
            self.currently_in = "post/comments"
            self.comments = []
            return

        # opening answers of a question
        if name == "answers":  # a answer
            self.currently_in = "post/answers"
            self.comments = []
            self.answers = []
            return

        # an answer
        if name == "answer":
            self.answers.append(dict(attrs.items()))
            return

        # opening comments of an answer
        if name == "comments" and self.currently_in == "post/answers":
            self.currently_in = "post/answers/comments"
            self.comments = []
            return

        # a comment for a post or an answer
        if name == "comment":
            self.comments.append(dict(attrs.items()))
            return

        # link on a question
        if name == "link":
            pipe = {"1": "duplicates", "3": "relateds"}.get(attrs["LinkTypeId"])
            if pipe:
                self.post["links"][pipe].append(
                    {
                        "Id": int(attrs["PostId"]),
                        "Name": attrs["PostName"],
                    }
                )

    def endElement(self, name):
        # closing comments of an answer. adding comments array to last answer
        if name == "comments" and self.currently_in == "post/answers/comments":
            self.answers[-1]["comments"] = self.comments
            # source comments are sorted by PostId and thus unordered within
            # a single post item. We'll need them sorted by Id/CreationDate
            self.comments.sort(key=lambda item: int(item["Id"]))
            self.currently_in = "post/answers"
        # closing answers of a post. assigning answers to the post
        if name == "answers" and self.currently_in == "post/answers":
            self.post["answers"] = self.answers

        # closing comments of a post. adding comments to the post
        if name == "comments" and self.currently_in == "post/comments":
            # source comments are sorted by PostId and thus unordered within
            # a single post item. We'll need them sorted by Id/CreationDate
            self.comments.sort(key=lambda item: int(item["Id"]))
            self.post["comments"] = self.comments

        if name == "post":
            if self.post.get("answers"):
                self.post["answers"].sort(
                    key=lambda item: int(item["Score"]), reverse=True
                )

            # defer processing to workers
            self.processor(item=self.post)

            # reset data holders
            del self.post
            del self.comments
            del self.answers
            self.post = {}
            self.comments = []
            self.answers = []

            self.check_trigger()


class PostGenerator(Generator):
    walker = PostsWalker

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fpath = self.conf.build_dir / "posts_complete.xml"

    def processor(self, item):
        post = item
        if self.conf.without_unanswered and not post["answers"]:
            self.release()
            return
        harmonize_post(post)

        path = f'questions/{post["Id"]}/{get_slug_for(post["Title"])}'
        # prepare post page outside Lock to prevent dead-lock on image discovery
        post_page = self.renderer.get_question(post)
        with self.lock:
            self.creator.add_item_for(
                path=path,
                title=self.rewriter.rewrite_string(post.get("Title")),
                content=post_page,
                mimetype="text/html",
                is_front=True,
                callback=self.release,
            )
        del post_page

        for answer in post.get("answers", []):
            with self.lock:
                self.creator.add_redirect(
                    path=f'a/{answer["Id"]}',
                    target_path=path,
                )

    def generate_questions_page(self):
        paginator = SortedSetPaginator(
            self.database.questions_key(),
            per_page=NB_QUESTIONS_PER_PAGE,
            at_most=NB_PAGINATED_QUESTIONS,
        )
        for page_number in paginator.page_range:
            page = paginator.get_page(page_number)
            with self.lock:
                page_content = self.renderer.get_all_questions_for_page(page)
                # we don't index same-title page for all paginated pages
                # instead we index the redirect to the first page
                self.creator.add_item_for(
                    path="questions"
                    if page_number == 1
                    else f"questions_page={page_number}",
                    content=page_content,
                    mimetype="text/html",
                    title="Highest Voted Questions" if page_number == 1 else None,
                    is_front=page_number == 1,
                )
                del page_content
        with self.lock:
            self.creator.add_redirect(
                path="questions_page=1", target_path="questions", is_front=False
            )
