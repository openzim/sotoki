#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

""" Temporary Store of data that needs to be reused in a later step

    Users details must be stored so we can use user names when building post pages
    but posts only reference Users's Ids for instamce.

    TBD:
      - fastest backend for this task
      - whether this can fit in RAM
      - whether we should have a flexible RAM usage (ie. can this be run iwith 4GB)"""

import json
import pathlib
import sqlite3
import urllib.parse

import redis

from ..constants import Sotoconf, getLogger

logger = getLogger()


class Database:
    """Database Interface

    Should allow use to quickly test alternative backends

    General principles:
      - DB can be initialized (setup of underlyig layers)
      - DB's details not exposed so this contains all DB interactions
      - Assume there's usually a notion of transactions that saves round-trips
        - begin()
        - commit() should_commit commit_maybe()
      - Might require some post-usage cleanup: teardown()
      - Should be able to remove data (it's TEMP only)"""

    COMMIT_EVERY = 20000
    record_on_main_thread = False

    def __init__(self, conf: Sotoconf):
        self.conf = conf
        self.nb_seen = 0

    @property
    def build_dir(self) -> pathlib.Path:
        # file:// URI requires a full path
        return self.conf.build_dir.resolve()

    @property
    def should_commit(self) -> bool:
        """whether to commit now

        This impl. compares `self.nb_seen` with `COMMIT_EVERY` constant"""
        return self.nb_seen % self.COMMIT_EVERY == 0

    def initialize(self):
        """to override: initialize database"""

    def commit_maybe(self):
        """commit() should should_commit allows it"""
        if self.should_commit:
            self.commit()

    def begin(self):
        """to override: start a session/transaction"""
        pass

    def make_dummy_query(self):
        """to override: used to ensure a started session can be closed safely"""
        pass

    def commit(self):
        """to override: end a session"""
        pass

    def record_user(self, user: dict):
        """to override/extend: record user details to DB"""
        self.nb_seen += 1

    def get_user_detail(self, user_id: int) -> dict:
        """to override: user details as dict from user_id"""

    def record_post(self, post: dict):
        """to override/extend: record user details to DB"""
        self.nb_seen += 1

    def teardown(self):
        """to override: release database"""

    def remove(self):
        """to override: remove database data"""


class SqliteDatabase(Database):
    """SQLite in-memory DB or as a file for StackOverflow"""

    # all writes must be done from same thread
    record_on_main_thread = True

    def __init__(self, conf: Sotoconf, initialize=False):
        super().__init__(conf)
        self.fpath = self.build_dir.joinpath("db.sqlite")
        kwargs = (
            {
                "database": f"file:{self.build_dir.joinpath('db.sqlite')}",
                "uri": True,
            }
            if self.conf.is_stackO
            else {"database": ":memory:"}
        )
        kwargs.update({"check_same_thread": False})
        self.conn = sqlite3.connect(**kwargs)

        if not kwargs.get("database").startswith("file:"):
            self.fpath = None

        if self.conf.is_stackO:
            kwargs.update({"database": f'{kwargs["database"]}?mode=ro'})
            self.conn_ro = sqlite3.connect(**kwargs)
        else:
            self.conn_ro = self.conn
        self.conn_ro.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self.cursor.execute("PRAGMA synchronous=OFF")
        self.cursor.execute("PRAGMA count_changes=OFF")
        self.cursor.execute("PRAGMA journal_mode=OFF;")
        self.cursor.execute("PRAGMA cache_size = -209715200;")  # 200Mib

        if initialize:
            self.initialize()

    def initialize(self):
        """Creates tables and indexes"""
        super().initialize()
        self.cursor.execute("DROP TABLE IF EXISTS users;")
        self.cursor.execute("DROP TABLE IF EXISTS questiontag;")
        # self.cursor.execute("DROP TABLE IF EXISTS links;")
        # gets an auto index in id
        self.cursor.execute(
            "CREATE TABLE users(id INTEGER PRIMARY KEY UNIQUE, "
            "DisplayName TEXT, Reputation TEXT);"
        )
        self.cursor.execute(
            "CREATE TABLE IF NOT EXISTS questiontag(id INTEGER PRIMARY KEY "
            "AUTOINCREMENT UNIQUE, Score INTEGER, Title TEXT, QId INTEGER, "
            "CreationDate TEXT, Tag TEXT);"
        )
        # usage:
        # select all TAGS (KEYS "tag:")
        self.conn.execute("CREATE INDEX index_tag ON questiontag (Tag)")
        # self.cursor.execute(
        #     "CREATE TABLE IF NOT EXISTS links (id INTEGER, title TEXT);"
        # )

    def record_user(self, user: dict):
        """saves ID, name and reputation to users table"""
        super().record_user(user)
        self.cursor.execute(
            "INSERT INTO users(id, DisplayName, Reputation) VALUES (?, ?, ?)",
            (int(user["Id"]), user["DisplayName"], user["Reputation"]),
        )
        self.commit_maybe()

    def record_post(self, post: dict):
        """saves post's Score, Title, Id, CreationDate and tag for each tag in post"""
        super().record_post(post)
        self.cursor.executemany(
            "INSERT INTO questiontag (Score, Title, QId, CreationDate, Tag) "
            "VALUES(?, ?, ?, ?, ?)",
            [
                (
                    post["Score"],
                    post["Title"],
                    post["Id"],
                    post["CreationDate"],
                    tag,
                )
                for tag in post.get("Tags", [])
            ],
        )
        self.commit_maybe()

    def get_user_detail(self, user_id: int) -> str:
        return {
            "name": self.conn_ro.execute(
                "SELECT DisplayName as name FROM users WHERE id = ?", (user_id,)
            ).fetchone()[0]
        }

    def make_dummy_query(self):
        """send a resourceless query to cursor so an empty transaction can be closed"""
        self.cursor.execute("SELECT 1")

    def begin(self):
        """start transaction"""
        self.cursor.execute("BEGIN;")

    def commit(self, done=False):
        """end transaction ; starting another one unless `done` is True"""
        self.cursor.execute("COMMIT;")
        if not done:
            self.begin()

    def teardown(self):
        """end transaction and close connection"""
        try:
            self.commit(done=True)
        except sqlite3.OperationalError:
            pass
        self.conn.close()

    def remove(self):
        """remove sqlite file if a file was used"""
        if self.fpath and not self.conf.keep_intermediate_files:
            self.fpath.unlink()


class RedisDatabase(Database):
    def __init__(self, conf: Sotoconf, initialize: bool = False):
        super().__init__(conf)

        kwargs = {}
        if self.conf.redis_url.scheme == "file":
            kwargs.update({"unix_socket_path": self.conf.redis_url.path})
            if self.conf.redis_url.query:
                db = (
                    urllib.parse.parse_qs(self.conf.redis_url.query).get("db", []).pop()
                )
                if db is not None:
                    kwargs.update({"db": db})
        elif self.conf.redis_url.scheme == "redis":
            kwargs.update(
                {
                    "host": self.conf.redis_url.hostname,
                    "port": self.conf.redis_url.port,
                    "db": self.conf.redis_url.path[1:]
                    if len(self.conf.redis_url.path) > 1
                    else None,
                    "username": self.conf.redis_url.username,
                    "password": self.conf.redis_url.password,
                }
            )
        self.conn = redis.Redis(**kwargs)
        self.pipe = self.conn.pipeline()

        if initialize:
            self.initialize()

    @staticmethod
    def user_key(user_id):
        return f"u:{user_id}"

    @staticmethod
    def post_key(post_id):
        return f"p:{post_id}"

    def initialize(self):
        """flush database"""
        self.conn.flushdb()

    def record_user(self, user: dict):
        """record name and reputation on a user:{id} key"""
        super().record_user(user)
        self.pipe.set(
            self.user_key(user["Id"]),
            json.dumps({"name": user["DisplayName"], "rep": user["Reputation"]}),
        )
        self.commit_maybe()

    def record_post(self, post: dict):
        """record post details and associated tags

        - JSON string of score, title and date on a p:{id} key
        - update questions ordered set with post ID and score
        - update/create tag ordered set with postId and score for each tag"""
        super().record_post(post)
        # store question details
        self.pipe.setnx(
            f'q:{post["Id"]}',
            json.dumps(
                {
                    "score": post["Score"],
                    "title": post["Title"],
                    "date": post["CreationDate"],
                }
            ),
        )

        # add this postId to the ordered list of questions sorted by score
        self.pipe.zadd("questions", mapping={post["Id"]: post["Score"]}, nx=True)

        # record each tag as an ordered set of question IDs (by quest score)
        for tag in post.get("tags", []):
            self.pipe.zadd(f"tag:{tag}", mapping={post["Id"]: post["Score"]}, nx=True)

        self.commit_maybe()

    def get_user_detail(self, user_id: int) -> str:
        user = self.conn.get(self.user_key(user_id))
        if not user:
            return None
        return json.loads(user)

    def make_dummy_query(self):
        self.conn.get("")

    def commit(self, done=False):
        self.pipe.execute()

    def teardown(self):
        self.pipe.execute()
        self.conn.close()

    def remove(self):
        """flush database"""
        self.conn.flushdb()


def get_database(conf: Sotoconf) -> Database:
    """get appropriate, initialized, Database instance from conf"""
    cls = RedisDatabase if conf.use_redis else SqliteDatabase
    return cls(conf, initialize=True)
