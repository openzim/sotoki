#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import collections
import threading
import time
from typing import Union

import redis
import bidict

from .common import Database
from .posts import PostsDatabaseMixin
from .tags import TagsDatabaseMixin
from .users import UsersDatabaseMixin
from ..shared import Global, logger
from ..misc import restart_redis_at
from sotoki.constants import UTF8, NB_PAGINATED_USERS


class TopDict(collections.UserDict):
    """A fixed-sized dict that keeps only the highest values"""

    def __init__(self, maxlen: int):
        super().__init__()
        self.maxlen = maxlen
        self.lock = threading.Lock()

    def __setitem__(self, key, value):
        with self.lock:
            # we're full, might not accept value
            if len(self) >= self.maxlen:
                # value is bellow our min, don't care
                min_val = min(self.values())
                if value < min_val:
                    return

                # value should be in top, let's remove our min to allow it
                min_key = list(self.keys())[list(self.values()).index(min_val)]
                del self[min_key]
            super().__setitem__(key, value)

    def sorted(self):
        return [k for k, _ in sorted(self.items(), key=lambda x: x[1], reverse=True)]


class RedisDatabase(
    Database, TagsDatabaseMixin, UsersDatabaseMixin, PostsDatabaseMixin
):
    def __init__(self, initialize: bool = False):
        self.connections = {}
        self.pipes = {}
        self.nb_seens = {}
        self.should_commits = {}

        super().__init__()

        # temp set to hold all active users' IDs
        self._all_users_ids = set()
        # temp dict to hold `n` most active users' ID:score
        self._top_users = TopDict(NB_PAGINATED_USERS)
        # total number of active users
        self.nb_users = 0

        self.tags_details_ids = {}
        # bidirectionnal Tag ID:name and (as inverse) name:ID mapping
        self.tags_ids = bidict.bidict()

        if initialize:
            self.initialize()

    @property
    def conn(self):
        """thread-specific Redis connection"""
        try:
            return self.connections[threading.get_ident()]
        except KeyError:
            self.connections[threading.get_ident()] = redis.StrictRedis.from_url(
                Global.conf.redis_url.geturl(), charset=UTF8, decode_responses=False
            )
            return self.connections[threading.get_ident()]

    @property
    def pipe(self):
        """thread-specific Pipeline for this thread-specific connection"""
        try:
            return self.pipes[threading.get_ident()]
        except KeyError:
            self.pipes[threading.get_ident()] = self.conn.pipeline()
            return self.pipes[threading.get_ident()]

    @property
    def nb_seen(self):
        """thread-specific number of items seen"""
        try:
            return self.nb_seens[threading.get_ident()]
        except KeyError:
            self.nb_seens[threading.get_ident()] = 0
            return self.nb_seens[threading.get_ident()]

    @nb_seen.setter
    def nb_seen(self, value):
        self.nb_seens[threading.get_ident()] = value

    @property
    def should_commit(self):
        """thread-specific flag to decide if it should commit"""
        try:
            return self.should_commits[threading.get_ident()]
        except KeyError:
            self.should_commits[threading.get_ident()] = False
            return self.should_commits[threading.get_ident()]

    @should_commit.setter
    def should_commit(self, value):
        self.should_commits[threading.get_ident()] = value

    def initialize(self):
        # test connection
        self.conn.get("NOOP")

        # clean up potentially existing DB
        if not Global.conf.open_shell and not Global.conf.keep_redis:
            self.conn.flushdb()

    def make_dummy_query(self):
        self.pipe.get("")

    def safe_get(self, key: str):
        """GET command retried on ConnectionError"""
        return self.safe_command("get", key)

    def safe_zcard(self, key: str):
        """ZCARD command retried on ConnectionError"""
        return self.safe_command("zcard", key)

    def safe_zscore(self, key: str, member: Union[str, int]):
        """ZSCORE command retried on ConnectionError"""
        return self.safe_command("zscore", key, member)

    def safe_command(self, command: str, *args, retries: int = 20):
        """RO command retried on ConnectionError"""
        attempt = 1
        func = getattr(self.conn, command.lower())
        while attempt < retries:
            try:
                return func(*args)
            except redis.exceptions.ConnectionError as exc:
                logger.error(
                    f"Redis {command.upper()} Error #{attempt}/{retries}: {exc}"
                )
                attempt += 1
                # wait for 2s
                threading.Event().wait(2)
        return func(*args)

    def commit(self, done=False):
        self.pipe.execute()

        # make sure we've commited pipes on all thread-specific pipelines
        if done:
            time.sleep(2)  # prevent last-thread created while we iterate on mini domain
            for pipe in self.pipes.values():
                pipe.execute()

    def purge(self):
        """ask redis to reclaim dirty pages space. Effective only on Linux"""
        self.conn.memory_purge()

    def defrag_external(self):
        if not Global.conf.redis_pid:
            logger.warning("Cannot defrag with {Global.conf.redis_pid=}")
            return

        logger.info("Starting REDIS defrag (external)")
        logger.debug(".. dumping to filesystem")
        self.dump()
        logger.debug(".. restarting redis")
        restart_redis_at(Global.conf.redis_pid)
        logger.debug(".. awaiting dump load completion")
        while True:
            try:
                self.conn.get("NOOP")
            except redis.BusyLoadingError:
                logger.debug("> busy")
                time.sleep(2)
            else:
                break
        logger.debug("REDIS is ready")

    def dump(self):
        """SAVE a dump on disk (as dump.rdb on CWD)"""
        self.conn.save()

    def teardown(self):
        self.pipe.execute()
        self.conn.close()

    def remove(self):
        """flush database"""
        if not Global.conf.keep_redis:
            self.conn.flushdb()
