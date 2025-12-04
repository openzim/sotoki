#!/usr/bin/env python

import gc
import pathlib
import threading
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zimscraperlib.zim import Creator

from sotoki.context import Context

if TYPE_CHECKING:
    from sotoki.models import SiteDetails
    from sotoki.renderer import Renderer
    from sotoki.utils.database.posts import PostsDatabase
    from sotoki.utils.database.redisdb import RedisDatabase
    from sotoki.utils.database.tags import TagsDatabase
    from sotoki.utils.database.users import UsersDatabase
    from sotoki.utils.executor import SotokiExecutor
    from sotoki.utils.html import Rewriter
    from sotoki.utils.imager import Imager
    from sotoki.utils.progress import Progresser

context = Context.get()
logger = context.logger


class Shared:
    """Shared context accross all scraper components"""

    creator: Creator
    progresser: Progresser
    database: RedisDatabase
    tagsdatabase: TagsDatabase
    usersdatabase: UsersDatabase
    postsdatabase: PostsDatabase
    executor: SotokiExecutor
    img_executor: SotokiExecutor
    imager: Imager
    rewriter: Rewriter
    renderer: Renderer
    site_details: SiteDetails
    build_dir: pathlib.Path
    lock: Lock = Lock()
    dump_domain: str
    online_domain: str

    # total stats
    total_tags = 0
    total_questions = 0
    total_users = 0

    # lock for operations needing synchronization
    lock = threading.Lock()

    @staticmethod
    def collect():
        logger.debug(f"Collecting {gc.get_count()}… {gc.collect()} collected.")


shared = Shared()
