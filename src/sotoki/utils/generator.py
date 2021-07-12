#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import xml.sax
import concurrent.futures as cf

from ..constants import getLogger, Global
from ..utils import GlobalMixin

logger = getLogger()


class Generator(GlobalMixin):

    walker = None

    def __init__(self):

        self.fpath = None
        self.futures = {}

    def run(self):
        Global.database.begin()

        # parse XML file. not using defusedxml for performances reasons.
        # although containing user-generated content, we trust Stack Exchange dump
        parser = xml.sax.make_parser()  # nosec
        parser.setContentHandler(self.walker(processor=self.processor_callback))
        parser.parse(self.fpath)
        parser.setContentHandler(None)
        logger.debug("Done parsing, collecting workers…")

        # await offloaded processing
        result = cf.wait(self.futures.keys(), return_when=cf.FIRST_EXCEPTION)
        # ensure we commited tail of data
        Global.database.commit(done=True)

        # check whether any of the jobs failed
        for future in result.done:
            exc = future.exception()
            if exc:
                item = self.futures.get(future)
                logger.error(f"Error processing {item}: {exc}")
                logger.exception(exc)
                raise exc

        if result.not_done:
            logger.error(
                "Some not_done futrues: \n - "
                + "\n - ".join([self.futures.get(future) for future in result.not_done])
            )
            raise Exception("Unable to complete download and extraction")

    def processor_callback(self, item):
        self.executor.submit(self.processor, item=item)

    def processor(self, item):
        """to override: process item"""
        raise NotImplementedError()


class Walker(xml.sax.handler.ContentHandler, GlobalMixin):
    def __init__(self, processor):
        self.processor = processor
