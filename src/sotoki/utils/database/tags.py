#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json

from ..shared import Global, logger
from sotoki.constants import UTF8


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

    def ack_tags_ids(self):
        """dump or load tags_ids and tags_details_ids"""
        tags_ids_fpath = Global.conf.build_dir / "tags_ids.json"
        if not self.tags_ids and tags_ids_fpath.exists():
            logger.debug(f"loading tags_ids from {tags_ids_fpath.name}")
            with open(tags_ids_fpath, "r") as fh:
                for tid, tname in json.load(fh).items():
                    self.tags_ids[int(tid)] = tname
        else:
            with open(tags_ids_fpath, "w") as fh:
                json.dump(dict(self.tags_ids), fh, indent=4)

        tags_details_ids_fpath = Global.conf.build_dir / "tags_details_ids.json"
        if not self.tags_details_ids and tags_details_ids_fpath.exists():
            logger.debug(f"loading tags_details_ids from {tags_details_ids_fpath.name}")
            with open(tags_details_ids_fpath, "r") as fh:
                self.tags_details_ids = json.load(fh)
        else:
            with open(tags_details_ids_fpath, "w") as fh:
                json.dump(self.tags_details_ids, fh, indent=4)

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
            self.safe_command("zremrangebyrank", self.tag_key(tag), 0, -(at_most + 1))

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
        return int(self.safe_zscore(self.tags_key(), name))

    def get_tag_detail(self, name: str, field: str) -> str:
        """single detail (excerpt or description) for a tag"""
        detail = self.safe_get(self.tag_detail_key(name, field))
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
            score = self.safe_zscore(self.tags_key(), name)

        item = self.get_tag_details(name) or {}
        item["score"] = score
        item["name"] = name
        return item
