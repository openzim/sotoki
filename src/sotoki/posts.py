#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu


""" Generate page for each Post in posts_complete """

import html

from slugify import slugify

from .constants import getLogger
from .utils.generator import Generator, Walker

logger = getLogger()


def get_user_url(user_id, name):
    return f"user/{user_id}/{slugify(name)}"


def get_missing_user(user_id=None, name=None):
    return {"Id": user_id, "DisplayName": name or "-"}


class PostsWalker(Walker):
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
        self.currently_in = None

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
        # TODO: check where those are used and why we need escaping
        if name == "link":
            pipe = {"1": "relateds", "3": "duplicates"}.get(attrs["LinkTypeId"])
            if pipe:
                # TODO: check escaping still required?
                self.post["links"][pipe].append(
                    {
                        "PostId": int(attrs["PostId"]),
                        "PostName": html.escape(attrs["PostName"], quote=False),
                    }
                )

    def endElement(self, name):
        # closing comments of an answer. adding comments array to last answer
        if name == "comments" and self.currently_in == "post/answers/comments":
            self.answers[-1]["comments"] = self.comments
            self.currently_in = "post/answers"
        # closing answers of a post. assigning answers to the post
        if name == "answers" and self.currently_in == "post/answers":
            self.post["answers"] = self.answers

        # closing comments of a post. adding comments to the post
        if name == "comments" and self.currently_in == "post/comments":
            self.post["comments"] = self.comments

        if name == "post":
            # defer processing to workers
            self.processor(item=self.post)
            # write record to DB using main thread (single write trans on sqlite)
            self.recorder(item=self.post)

            # reset data holders
            del self.post
            del self.comments
            del self.answers
            self.post = {}
            self.comments = []
            self.answers = []


class PostGenerator(Generator):
    walker = PostsWalker

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fpath = self.conf.build_dir / "posts_complete.xml"

    def recorder(self, item):
        # skip post without answers ; maybe?
        if self.conf.without_unanswered and not item["answers"]:
            return

        self.database.record_post(post=item)

    def processor(self, item):
        post = item
        if self.conf.without_unanswered and not post["answers"]:
            return

        all_content = post.get("Body")

        # update user details for post/answers/comments(for both)
        self.update_user_details(post, is_owner=True)
        for answer in post.get("answers", []):
            answer["Score"] = int(answer["Score"])
            # whether this is the accepted answer or not
            answer["Accepted"] = (
                "AcceptedAnswerId" in post and post["AcceptedAnswerId"] == answer["Id"]
            )
            self.update_user_details(answer, is_owner=True)
            for comment in answer.get("comments", []):
                if "Score" in comment:
                    comment["Score"] = int(comment["Score"])
                # TODO: render?
                # comment["Text"] = comment["Text"]
                self.update_user_details(comment, is_owner=False)

                all_content += comment["Text"]

            all_content += answer["Body"]

        for comment in post.get("comments", []):
            if "Score" in comment:
                comment["Score"] = int(comment["Score"])
            # TODO: render?
            # comment["Text"] = comment["Text"]
            self.update_user_details(comment, is_owner=False)

            all_content += comment["Text"]

        # create redirections for type-agnostic links:
        # from element/{asnwerId} to question/{postId}
        # so every answer can redirect to its post
        for answer in post.get("answers", []):
            with self.creator_lock:
                # TODO: do we need title?
                self.creator.add_redirect(
                    path=f"element/{answer['Id']}",
                    target_path=f"question/{post['Id']}",
                    # title=f'Answer {answer["Id"]}',
                )

        # create redirections for type-agnostic links:
        # from elemen/{postId} to question/{postId}
        with self.creator_lock:
            # TODO: do we need title?
            self.creator.add_redirect(
                path=f'element/{post["Id"]}',
                target_path=f'question/{post["Id"]}',
                # title=f'Question {post["Id"]}',
            )

        with self.creator_lock:
            self.creator.add_item_for(
                path=f'question/{post["Id"]}',
                title=post.get("Title"),
                content=all_content,
                mimetype="text/html",
            )

    def update_user_details(self, item, is_owner=False):

        id_field = "OwnerUserId" if is_owner else "UserId"
        name_field = "OwnerDisplayName" if is_owner else "UserDisplayName"
        user_id = int(item.get(id_field, "-1"))
        if user_id:
            user = self.database.get_user_detail(user_id)
            if user is not None:
                item["User"] = user  # recast Id to int?

                if not self.conf.without_user_profiles:
                    # TODO: should probably be in template
                    item["User"]["Path"] = get_user_url(user_id, item["User"]["name"])
            else:
                item["User"] = get_missing_user(user_id=user_id)
        else:
            item["User"] = get_missing_user(name=item.get(name_field))
