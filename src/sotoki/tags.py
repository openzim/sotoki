#!/usr/bin/env python

import json
from abc import abstractmethod

from sotoki.constants import (
    NB_PAGINATED_QUESTIONS_PER_TAG,
    NB_QUESTIONS_PER_TAG_PAGE,
)
from sotoki.renderer import SortedSetPaginator
from sotoki.utils.generator import Generator, Walker
from sotoki.utils.shared import logger, shared


class TagsWalker(Walker):
    """Tags.xml SAX parser

    Schema:

    <tags>
        <row Id="" TagName="" Count="" ExcerptPostId="" WikiPostId="" />
    </tags>
    """

    def startElement(self, name, attrs):  # noqa: N802
        if name == "row":
            self.processor(item=dict(attrs.items()))


class TagFinder(Generator):

    @property
    def walker(self):
        return TagsWalker

    @property
    def fpath(self):
        return shared.build_dir / "Tags.xml"

    def processor(self, item):
        tag = item
        if tag["Count"] == "0":
            logger.debug(f"Tag {item['TagName']} is not used.")
            return

        tag["Count"] = int(tag["Count"])
        shared.tagsdatabase.record_tag(tag)
        self.release()


class TagsExcerptWalker(Walker):
    def startElement(self, name, attrs):  # noqa: N802
        if name == "post":
            self.processor(item=dict(attrs.items()))


class TagExcerptDescriptionRecorder(Generator):

    @property
    def walker(self):
        return TagsExcerptWalker

    @property
    def fpath(self):
        return shared.build_dir / self.fname

    @property
    @abstractmethod
    def fname(self) -> str:
        pass

    @property
    @abstractmethod
    def field(self) -> str:
        pass

    def processor(self, item):
        # only record if post is in DB's list of IDs we want
        tag_name = shared.tagsdatabase.tags_details_ids.get(item.get("Id"))
        if tag_name:
            shared.tagsdatabase.record_tag_detail(
                name=tag_name, field=self.field, content=item.get("Body")
            )
        self.release()


class TagExcerptRecorder(TagExcerptDescriptionRecorder):
    @property
    def fname(self) -> str:
        return "posts_excerpt.xml"

    @property
    def field(self) -> str:
        return "excerpt"


class TagDescriptionRecorder(TagExcerptDescriptionRecorder):
    @property
    def fname(self) -> str:
        return "posts_wiki.xml"

    @property
    def field(self) -> str:
        return "description"


class TagGenerator(Generator):

    @property
    def fpath(self):
        return shared.build_dir / "Tags.xml"

    def run(self):
        # create individual pages for all tags
        for tag_name in shared.tagsdatabase.tags_ids.inverse.keys():
            paginator = SortedSetPaginator(
                shared.tagsdatabase.tag_key(tag_name),
                per_page=NB_QUESTIONS_PER_TAG_PAGE,
                at_most=NB_PAGINATED_QUESTIONS_PER_TAG,
            )
            for page_number in paginator.page_range:
                page = paginator.get_page(page_number)
                with shared.lock:
                    page_content = shared.renderer.get_tag_for_page(tag_name, page)
                    shared.creator.add_item_for(
                        path=(
                            f"questions/tagged/{tag_name}"
                            if page_number == 1
                            else f"questions/tagged/{tag_name}_page={page_number}"
                        ),
                        content=page_content,
                        mimetype="text/html",
                        title=(
                            f"Highest Voted '{tag_name}' Questions"
                            if page_number == 1
                            else None
                        ),
                        is_front=page_number == 1,
                    )
                    del page_content

            with shared.lock:
                shared.creator.add_redirect(
                    path=f"questions/tagged/{tag_name}_page=1",
                    target_path=f"questions/tagged/{tag_name}",
                    is_front=False,
                )
            shared.progresser.update(incr=True)

        # create paginated pages for tags
        paginator = SortedSetPaginator(shared.tagsdatabase.tags_key(), per_page=36)
        for page_number in paginator.page_range:
            page = paginator.get_page(page_number)
            with shared.lock:
                page_content = shared.renderer.get_all_tags_for_page(page)
                # we don't index same-title page for all paginated pages
                # instead we index the redirect to the first page
                shared.creator.add_item_for(
                    path="tags" if page_number == 1 else f"tags_page={page_number}",
                    content=page_content,
                    mimetype="text/html",
                    title="Tags" if page_number == 1 else None,
                    is_front=page_number == 1,
                )
                del page_content
        with shared.lock:
            shared.creator.add_redirect(
                path="tags_page=1",
                target_path="tags",
                is_front=False,
            )

        with shared.lock:
            shared.creator.add_item_for(
                path="api/tags.json",
                content=json.dumps(
                    list(shared.database.query_set(shared.tagsdatabase.tags_key()))
                ),
                mimetype="application/json",
                is_front=False,
            )
