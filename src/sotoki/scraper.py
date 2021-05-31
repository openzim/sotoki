#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import shutil

from .constants import getLogger, Sotoconf
from .archives import ArchiveManager
from .utils.s3 import s3_credentials_ok

logger = getLogger()


class StackExchangeToZim:
    def __init__(self, **kwargs):

        self.conf = Sotoconf(**kwargs)
        for option in self.conf.required:
            if getattr(self.conf, option) is None:
                raise ValueError(f"Missing parameter `{option}`")

        self.s3_storage = None

    @property
    def domain(self):
        return self.conf.domain

    @property
    def build_dir(self):
        return self.conf.build_dir

    def cleanup(self):
        """ Remove temp files and release resources before exiting"""
        if not self.conf.keep_build_dir:
            logger.debug(f"Removing {self.build_dir}")
            shutil.rmtree(self.build_dir, ignore_errors=True)

    def run(self):
        if self.conf.s3_url_with_credentials and not s3_credentials_ok(
            self.s3_storage, self.conf.s3_url_with_credentials
        ):
            raise ValueError("Unable to connect to Optimization Cache. Check its URL.")

        s3_msg = (
            f"  using cache: {self.s3_storage.url.netloc} "
            f"with bucket: {self.s3_storage.bucket_name}"
            if self.s3_storage
            else ""
        )
        logger.info(
            f"Starting scraper with:\n"
            f"  domain: {self.domain}\n"
            f"  build_dir: {self.build_dir}\n"
            f"  output_dir: {self.conf.output_dir}\n"
            f"{s3_msg}"
        )

        logger.info("STEP 1: XML Dumps prepation")
        ark_manager = ArchiveManager(self.conf)
        ark_manager.check_and_prepare_dumps()
        del ark_manager

        if self.conf.prepare_only:
            logger.info("Requested preparation only; exiting")
            return
