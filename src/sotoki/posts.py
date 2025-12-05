#!/usr/bin/env python
import datetime
import re
from typing import Any

from zimscraperlib.typing import Callback

from sotoki.constants import NB_PAGINATED_QUESTIONS, NB_QUESTIONS_PER_PAGE
from sotoki.renderer import SortedSetPaginator
from sotoki.utils.generator import Generator, Walker
from sotoki.utils.html import get_slug_for
from sotoki.utils.shared import context, logger, shared


def harmonize_post(post: dict):
    post["has_accepted"] = "AcceptedAnswerId" in post
    post["OwnerName"] = post.get("OwnerUserId", post.get("OwnerDisplayName"))
    post["CreationTimestamp"] = int(
        datetime.datetime.fromisoformat(post["CreationDate"]).strftime("%s")
    )
    # split either by | or by >< (some dumps use the |tag1|tag2| format,
    # others use the <tag1><tag2> format)
    post["Tags"] = re.split(r"\||><", post["Tags"][1:-1])


class WalkerWithTrigger(Walker):
    def startDocument(self):  # noqa: N802
        self.seen = 0

    def check_trigger(self):
        self.seen += 1
        if self.seen % 10000 == 0:
            logger.debug(f"Seen {self.seen}")
            shared.collect()


class FirstPassWalker(WalkerWithTrigger):
    def startElement(self, name, attrs):  # noqa: N802
        def _user_to_set(aset, field):
            if value := attrs.get(field):
                aset.add(int(value))

        # a question
        if name == "post":
            # store xml data until we're through with the <post /> node
            self.post: dict[str, Any] = dict(attrs.items())
            self.post["Id"] = int(self.post["Id"])
            self.post["Score"] = int(self.post["Score"])
            self.post["Tags"] = self.post.get("Tags", "")
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
            # ignore deleted answers
            if "DeletionDate" in attrs:
                return
            _user_to_set(self.post["users_ids"], "OwnerUserId")
            _user_to_set(self.post["users_ids"], "LastEditorUserId")
            self.post["nb_answers"] += 1

    def endElement(self, name):  # noqa: N802

        if name == "post":
            self.processor(item=self.post)

            # reset data holders
            del self.post

            self.check_trigger()


class PostFirstPasser(Generator):

    @property
    def walker(self):
        return FirstPassWalker

    @property
    def fpath(self):
        return shared.build_dir / "posts_complete.xml"

    def __init__(self):
        self.nb_answers = 0
        self.nb_answered = 0
        self.nb_accepted = 0
        self.most_recent_ts = 0

    def run(self):
        super().run()
        shared.postsdatabase.record_questions_stats(
            nb_answers=self.nb_answers,
            nb_answered=self.nb_answered,
            nb_accepted=self.nb_accepted,
            most_recent_ts=self.most_recent_ts,
        )

    def processor(self, item):
        # ignore deleted posts
        if "DeletionDate" in item:
            self.release()
            return
        # skip post without answers ; maybe?
        if context.without_unanswered and not item["nb_answers"]:
            self.release()
            return

        harmonize_post(item)

        # update stats
        self.nb_answers += item["nb_answers"]
        if item["has_accepted"]:
            self.nb_accepted += 1
        if item["nb_answers"]:
            self.nb_answered += 1

        self.most_recent_ts = max(self.most_recent_ts, item["CreationTimestamp"])

        shared.postsdatabase.record_question(post=item)

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

    def startDocument(self):  # noqa: N802
        super().startDocument()
        self.currently_in = None
        self.post = {}
        self.comments = []
        self.answers = []

    def startElement(self, name, attrs):  # noqa: N802
        # a question
        if name == "post":
            # store xml data until we're through with the <post /> node
            self.currently_in = "post"
            self.post: dict[str, Any] = dict(attrs.items())
            self.post["Id"] = int(self.post["Id"])
            self.post["Score"] = int(self.post["Score"])
            self.post["Tags"] = self.post.get("Tags", "")
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
            if "DeletionDate" in attrs:
                return
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

    def endElement(self, name):  # noqa: N802
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
    @property
    def walker(self):
        return PostsWalker

    @property
    def fpath(self):
        return shared.build_dir / "posts_complete.xml"

    def processor(self, item):
        post = item
        if context.without_unanswered and not post["answers"]:
            self.release()
            return
        # ignore deleted posts
        if "DeletionDate" in item:
            self.release()
            return
        harmonize_post(post)

        path = f'questions/{post["Id"]}/{get_slug_for(post["Title"])}'
        # prepare post page outside Lock to prevent dead-lock on image discovery
        post_page = shared.renderer.get_question(post)
        with shared.lock:
            shared.creator.add_item_for(
                path=path,
                title=shared.rewriter.rewrite_string(post.get("Title")),
                content=post_page,
                mimetype="text/html",
                is_front=True,
                callbacks=[Callback(func=self.release)],
            )
            shared.creator.add_redirect(
                path=f'questions/{post["Id"]}',
                target_path=path,
            )
        del post_page

        for answer in post.get("answers", []):
            with shared.lock:
                shared.creator.add_redirect(
                    path=f'a/{answer["Id"]}',
                    target_path=path,
                )

    def generate_questions_page(self):
        paginator = SortedSetPaginator(
            shared.postsdatabase.questions_key(),
            per_page=NB_QUESTIONS_PER_PAGE,
            at_most=NB_PAGINATED_QUESTIONS,
        )
        for page_number in paginator.page_range:
            page = paginator.get_page(page_number)
            with shared.lock:
                page_content = shared.renderer.get_all_questions_for_page(page)
                # we don't index same-title page for all paginated pages
                # instead we index the redirect to the first page
                shared.creator.add_item_for(
                    path=(
                        "questions"
                        if page_number == 1
                        else f"questions_page={page_number}"
                    ),
                    content=page_content,
                    mimetype="text/html",
                    title="Highest Voted Questions" if page_number == 1 else None,
                    is_front=page_number == 1,
                )
                del page_content
        with shared.lock:
            shared.creator.add_redirect(
                path="questions_page=1", target_path="questions", is_front=False
            )
