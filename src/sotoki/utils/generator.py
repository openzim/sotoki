#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu
import xml.sax

from ..utils.shared import Global, GlobalMixin

logger = Global.logger


class Generator(GlobalMixin):

    walker = None

    def __init__(self):

        self.fpath = None

    def run(self):
        Global.database.begin()
        Global.executor.start()

        # parse XML file. not using defusedxml for performances reasons.
        # although containing user-generated content, we trust Stack Exchange dump
        parser = xml.sax.make_parser()  # nosec
        try:
            parser.setContentHandler(self.walker(processor=self.processor_callback))
            parser.parse(self.fpath)
            parser.setContentHandler(None)
        finally:
            try:
                parser.close()
            except xml.sax.SAXException as exc:
                logger.exception(exc)
        logger.debug(f"Done parsing {type(self).__name__}, collecting workers…")

        # await offloaded processing
        Global.executor.join()
        logger.debug(f"{type(self).__name__} Workers collected.")

        # ensure we commited tail of data
        Global.database.commit(done=True)

        if Global.executor.exception:
            raise Global.executor.exception

    def processor_callback(self, item):
        Global.executor.submit(
            self.processor, item=item, raises=True, dont_release=True
        )

    def processor(self, item):
        """to override: process item"""
        raise NotImplementedError()

    def release(self):
        self.executor.task_done()
        self.progresser.update(incr=True)


class Walker(xml.sax.handler.ContentHandler, GlobalMixin):
    def __init__(self, processor):
        super().__init__()
        self.processor = processor
