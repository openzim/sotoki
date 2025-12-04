#!/usr/bin/env python

import xml.sax.handler
from abc import abstractmethod
from pathlib import Path

from sotoki.utils.shared import logger, shared


class Walker(xml.sax.handler.ContentHandler):
    def __init__(self, processor):
        super().__init__()
        self.processor = processor


class Generator:

    @property
    @abstractmethod
    def walker(self) -> type[Walker]:
        pass

    @property
    @abstractmethod
    def fpath(self) -> Path:
        pass

    def run(self):
        shared.executor.start()

        # parse XML file. not using defusedxml for performances reasons.
        # although containing user-generated content, we trust Stack Exchange dump
        parser = xml.sax.make_parser()  # nosec # noqa: S317
        try:
            parser.setContentHandler(self.walker(processor=self.processor_callback))
            parser.parse(self.fpath)
            parser.setContentHandler(None)  # pyright: ignore[reportArgumentType]
        finally:
            try:
                parser.close()  # pyright: ignore[reportAttributeAccessIssue]
            except xml.sax.SAXException as exc:
                logger.exception(exc)
        logger.debug(f"Done parsing {type(self).__name__}, collecting workers…")

        # await offloaded processing
        shared.executor.join()
        logger.debug(f"{type(self).__name__} Workers collected.")

        # ensure we commited tail of data
        shared.database.commit(done=True)

        if shared.executor.exception:
            raise shared.executor.exception

    def processor_callback(self, item):
        shared.executor.submit(
            self.processor, item=item, raises=True, dont_release=True
        )

    def processor(self, item):
        """to override: process item"""
        raise NotImplementedError()

    def release(self):
        shared.executor.task_done()
        shared.progresser.update(incr=True)
