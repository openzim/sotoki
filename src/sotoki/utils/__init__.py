#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu


from ..constants import Global


class GlobalMixin:
    @property
    def conf(self):
        return Global.conf

    @property
    def site(self):
        return Global.site

    @property
    def database(self):
        return Global.database

    @property
    def creator(self):
        return Global.creator

    @property
    def lock(self):
        return Global.lock

    @property
    def imager(self):
        return Global.imager

    @property
    def executor(self):
        return Global.executor

    @property
    def renderer(self):
        return Global.renderer
