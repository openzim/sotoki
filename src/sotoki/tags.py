#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import json

from .constants import (
    NB_PAGINATED_QUESTIONS_PER_TAG,
    NB_QUESTIONS_PER_TAG_PAGE,
)
from .utils.generator import Generator, Walker
from .utils.shared import logger
from .renderer import SortedSetPaginator


class TagsWalker(Walker):
    """Tags.xml SAX parser

    Schema:

    <tags>
        <row Id="" TagName="" Count="" ExcerptPostId="" WikiPostId="" />
    </tags>
    """

    def startElement(self, name, attrs):
        if name == "row":
            self.processor(item=dict(attrs.items()))


class TagFinder(Generator):
    walker = TagsWalker

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fpath = self.conf.build_dir / "Tags.xml"

    def processor(self, item):
        tag = item
        if tag["Count"] == "0":
            logger.debug(f"Tag {item['TagName']} is not used.")
            return

        tag["Count"] = int(tag["Count"])
        self.database.record_tag(tag)
        self.release()


class TagsExcerptWalker(Walker):
    def startElement(self, name, attrs):
        if name == "post":
            self.processor(item=dict(attrs.items()))


class TagExcerptDescriptionRecorder(Generator):
    walker = TagsExcerptWalker
    fname = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fpath = self.conf.build_dir / self.fname

    def processor(self, item):
        # only record if post is in DB's list of IDs we want
        tag_name = self.database.tags_details_ids.get(item.get("Id"))
        if tag_name:
            self.database.record_tag_detail(
                name=tag_name, field=self.field, content=item.get("Body")
            )
        self.release()


class TagExcerptRecorder(TagExcerptDescriptionRecorder):
    fname = "posts_excerpt.xml"
    field = "excerpt"


class TagDescriptionRecorder(TagExcerptDescriptionRecorder):
    fname = "posts_wiki.xml"
    field = "description"


class TagGenerator(Generator):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fpath = self.conf.build_dir / "Tags.xml"

    def run(self):
        # create individual pages for all tags
        for tag_name in self.database.tags_ids.inverse.keys():
            paginator = SortedSetPaginator(
                self.database.tag_key(tag_name),
                per_page=NB_QUESTIONS_PER_TAG_PAGE,
                at_most=NB_PAGINATED_QUESTIONS_PER_TAG,
            )
            for page_number in paginator.page_range:
                page = paginator.get_page(page_number)
                with self.lock:
                    page_content = self.renderer.get_tag_for_page(tag_name, page)
                    self.creator.add_item_for(
                        path=f"questions/tagged/{tag_name}"
                        if page_number == 1
                        else f"questions/tagged/{tag_name}_page={page_number}",
                        content=page_content,
                        mimetype="text/html",
                        title=f"Highest Voted '{tag_name}' Questions"
                        if page_number == 1
                        else None,
                        is_front=page_number == 1,
                    )
                    del page_content

            with self.lock:
                self.creator.add_redirect(
                    path=f"questions/tagged/{tag_name}_page=1",
                    target_path=f"questions/tagged/{tag_name}",
                    is_front=False,
                )
            self.progresser.update(incr=True)

        # create paginated pages for tags
        paginator = SortedSetPaginator(self.database.tags_key(), per_page=36)
        for page_number in paginator.page_range:
            page = paginator.get_page(page_number)
            with self.lock:
                page_content = self.renderer.get_all_tags_for_page(page)
                # we don't index same-title page for all paginated pages
                # instead we index the redirect to the first page
                self.creator.add_item_for(
                    path="tags" if page_number == 1 else f"tags_page={page_number}",
                    content=page_content,
                    mimetype="text/html",
                    title="Tags" if page_number == 1 else None,
                    is_front=page_number == 1,
                )
                del page_content
        with self.lock:
            self.creator.add_redirect(
                path="tags_page=1",
                target_path="tags",
                is_front=False,
            )

        with self.lock:
            self.creator.add_item_for(
                path="api/tags.json",
                content=json.dumps(
                    list(self.database.query_set(self.database.tags_key()))
                ),
                mimetype="application/json",
                is_front=False,
            )
