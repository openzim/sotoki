#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from .constants import getLogger
from .utils.generator import Generator, Walker
from .renderer import SortedSetPaginator

logger = getLogger()


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
        for tag_name in self.database.query_set(
            self.database.tags_key(), num=10, scored=False
        ):
            paginator = SortedSetPaginator(self.database.tag_key(tag_name), 20)
            for page_number in paginator.page_range:
                page = paginator.get_page(page_number)
                with self.lock:
                    self.creator.add_item_for(
                        path=f"questions/tagged/{tag_name}_page={page_number}",
                        content=self.renderer.get_tag_for_page(tag_name, page),
                        mimetype="text/html",
                    )

            with self.lock:
                self.creator.add_redirect(
                    path=f"questions/tagged/{tag_name}",
                    target_path=f"questions/tagged/{tag_name}_page=1",
                    title=f"Highest Voted '{tag_name}' Questions",
                )

        # create paginated pages for tags
        paginator = SortedSetPaginator(self.database.tags_key(), 8)
        for page_number in paginator.page_range:
            page = paginator.get_page(page_number)
            with self.lock:
                # we don't index same-title page for all paginated pages
                # instead we index the redirect to the first page
                self.creator.add_item_for(
                    path=f"tags_page={page_number}",
                    content=self.renderer.get_all_tags_for_page(page),
                    mimetype="text/html",
                )
        with self.lock:
            self.creator.add_redirect(
                path="tags",
                target_path="tags_page=1",
                title="Tags",
            )
