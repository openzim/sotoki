#!/usr/bin/env python

import threading
import time
from collections.abc import Iterator

import redis
import redis.client
import redis.exceptions

from sotoki.constants import UTF8
from sotoki.utils.misc import restart_redis_at
from sotoki.utils.shared import context, logger


class RedisDatabase:

    commit_every = 1000

    def __init__(self, *, initialize: bool = False):
        self.connections: dict[int, redis.Redis] = {}
        self.pipes: dict[int, redis.client.Pipeline] = {}
        self.nb_seens: dict[int, int] = {}
        self.should_commits: dict[int, bool] = {}

        if initialize:
            self.initialize()

    @property
    def conn(self) -> redis.Redis:
        """thread-specific Redis connection"""
        try:
            return self.connections[threading.get_ident()]
        except KeyError:
            self.connections[threading.get_ident()] = redis.StrictRedis.from_url(
                context.redis_url, encoding=UTF8, decode_responses=False
            )
            return self.connections[threading.get_ident()]

    @property
    def pipe(self) -> redis.client.Pipeline:
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
        if not context.open_shell and not context.keep_redis:
            self.conn.flushdb()

    def make_dummy_query(self):
        self.pipe.get("")

    def safe_get(self, key: str):
        """GET command retried on ConnectionError"""
        return self.safe_command("get", key)

    def safe_zcard(self, key: str):
        """ZCARD command retried on ConnectionError"""
        return self.safe_command("zcard", key)

    def safe_zscore(self, key: str, member: str | int):
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

    def commit(self, *, done=False):
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
        if not context.redis_pid:
            logger.warning(f"Cannot defrag with {context.redis_pid=}")
            return

        logger.info("Starting REDIS defrag (external)")
        logger.debug(".. dumping to filesystem")
        self.dump()
        logger.debug(".. restarting redis")
        restart_redis_at(context.redis_pid)
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
        if not context.keep_redis:
            self.conn.flushdb()

    def get_set_count(self, set_name: str) -> int:
        """Number of recorded entries in set"""
        return self.safe_zcard(set_name)

    def query_set(
        self,
        set_name: str,
        start: int = 0,
        num: int | None = None,
        *,
        desc: bool = True,
        scored: bool = True,
    ) -> Iterator[tuple[object, int] | object]:
        """Query entries in named sorted set"""

        def decode_results(results):
            for result in results:
                if scored:
                    yield (result[0].decode(UTF8), result[1])
                else:
                    yield result.decode(UTF8)

        func = getattr(self.conn, "zrevrangebyscore" if desc else "zrangebyscore")

        if num is None:
            num = self.safe_zcard(set_name)

        kwargs = {
            "name": set_name,
            "max": "+inf",
            "min": "-inf",
            "start": start,
            "num": num,
            "withscores": scored,
            "score_cast_func": int,
        }
        return decode_results(func(**kwargs))

    def commit_maybe(self):
        """commit() should should_commit allows it"""
        if self.should_commit:
            self.commit()
            self.should_commit = False

    def bump_seen(self, by: int = 1):
        """track number of items seen and update commit decision"""
        old_threshold = self.nb_seen // self.commit_every
        self.nb_seen += by
        new_threshold = self.nb_seen // self.commit_every
        if old_threshold != new_threshold:
            self.should_commit = True
