#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu


""" Generate one page per Tag with list of related questions and a list of tags"""

from .constants import getLogger
from .utils.generator import Generator, Walker

logger = getLogger()


class TagsWalker(Walker):
    """posts_complete SAX parser

    Schema:

    <tags>
        <row Id="" TagName="" Count="" ExcerptPostId="" WikiPostId="" />
    </tags>
    """

    def __init__(self, processor, recorder):
        self.processor = processor
        # fake a query as we won't record anything
        recorder(item=None)

    def startElement(self, name, attrs):
        if name == "row":
            self.processor(item=dict(attrs.items()))


class TagGenerator(Generator):
    walker = TagsWalker

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fpath = self.conf.build_dir / "Tags.xml"
        # keep a record of all tags names and Count (nb of posts using it)
        # SO is 60K tags so ~1MiB in RAM
        self.tags = []

    def run(self):
        super().run()

        logger.debug("Sort all tags by number of questions")
        self.tags.sort(key=lambda t: t[1], reverse=True)
        logger.debug("done")

        # create alltags page at tags/
        with self.creator_lock:
            self.creator.add_item_for(
                path="tags",
                title="Tags",
                content="<ul><li>"
                + "</li><li>".join([t[0] for t in self.tags])
                + "</li></ul>",
                mimetype="text/html",
            )

    def recorder(self, item):
        self.database.make_dummy_query()

    def processor(self, item):
        tag = item
        if self.conf.without_unanswered and tag["Count"] == "0":
            return
        name = tag["TagName"]
        self.tags.append((name, int(tag["Count"])))

        # create tag page at questions/tagged/{name}
        with self.creator_lock:
            self.creator.add_item_for(
                path=f"questions/tagged/{name}",
                title="'{name}' Questions",
                content="content for tag",
                mimetype="text/html",
            )
