#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import xml.sax
import concurrent.futures as cf

from ..constants import getLogger

logger = getLogger()


class Generator:

    walker = None

    def __init__(self, conf, creator, creator_lock, executor, database):
        self.conf = conf
        self.creator = creator
        self.creator_lock = creator_lock
        self.executor = executor
        self.database = database

        self.fpath = None
        self.futures = {}

    def run(self):
        self.database.begin()

        # parse XML file. not using defusedxml for performances reasons.
        # although containing user-generated content, we trust Stack Exchange dump
        parser = xml.sax.make_parser()  # nosec
        parser.setContentHandler(
            self.walker(
                processor=self.processor_callback,
                # for non-thread-safe database writes: we'll record from the main
                # thread which is the one running the parser
                recorder=self.recorder
                if self.database.record_on_main_thread
                else self.recorder_callback,
            )
        )
        parser.parse(self.fpath)

        # await offloaded processing
        result = cf.wait(self.futures.keys(), return_when=cf.FIRST_EXCEPTION)
        # ensure we commited tail of data
        self.database.commit(done=True)

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
        future = self.executor.submit(self.processor, item=item)
        self.futures.update({future: item.get("Id")})

    def recorder_callback(self, item):
        future = self.executor.submit(self.recorder, item=item)
        self.futures.update({future: item.get("Id")})

    def processor(self, item):
        """to override: process item"""
        raise NotImplementedError()

    def recorder(self, item):
        """to override: record item"""
        raise NotImplementedError()


class Walker(xml.sax.handler.ContentHandler):
    def __init__(self, processor, recorder):
        self.processor = processor
        self.recorder = recorder
