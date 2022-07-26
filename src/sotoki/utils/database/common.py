#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

""" Temporary Store of data that needs to be reused in a later step

    Users details must be stored so we can use user names when building post pages
    but posts only reference Users's Ids for instance.
"""

from typing import Union, Iterator, Tuple

from sotoki.constants import UTF8


class Database:
    """Database Interface

    Should allow us to quickly test alternative backends

    General principles:
      - DB can be initialized (setup of underlyig layers)
      - DB's details not exposed so this contains all DB interactions
      - Assume there's usually a notion of transactions that saves round-trips
        - begin()
        - commit() should_commit commit_maybe()
      - Might require some post-usage cleanup: teardown()
      - Should be able to remove data (it's TEMP only)"""

    commit_every = 1000
    record_on_main_thread = False

    def __init__(self):
        self.nb_seen = 0
        self.should_commit = False

    def initialize(self):
        """to override: initialize database"""

    def commit_maybe(self):
        """commit() should should_commit allows it"""
        if self.should_commit:
            self.commit()
            self.should_commit = False

    def begin(self):
        """to override: start a session/transaction"""

    def bump_seen(self, by: int = 1):
        old_threshold = self.nb_seen // self.commit_every
        self.nb_seen += by
        new_threshold = self.nb_seen // self.commit_every
        if old_threshold != new_threshold:
            self.should_commit = True

    def make_dummy_query(self):
        """to override: used to ensure a started session can be closed safely"""

    def commit(self):
        """to override: end a session"""

    def teardown(self):
        """to override: release database"""

    def remove(self):
        """to override: remove database data"""

    def get_set_count(self, set_name: str) -> int:
        """Number of recorded entries in set"""
        return self.safe_zcard(set_name)

    def query_set(
        self,
        set_name: str,
        start: int = 0,
        num: int = None,
        desc: bool = True,
        scored: bool = True,
    ) -> Iterator[Union[Tuple[object, int], object]]:
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
