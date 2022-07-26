#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

from .common import Database
from .redisdb import RedisDatabase


def get_database() -> Database:
    return RedisDatabase(initialize=True)
