#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import zlib
import queue
import pathlib
import logging
import subprocess
import urllib.parse
import concurrent.futures as cf
from typing import Union, Iterable

import psutil

logger = logging.getLogger(__name__)


def has_binary(name):
    """whether system has this binary in PATH"""
    return (
        subprocess.run(
            ["/usr/bin/env", "which", name], stdout=subprocess.DEVNULL
        ).returncode
        == 0
    )


def get_short_hash(text: str) -> str:
    letters = ["E", "T", "A", "I", "N", "O", "S", "H", "R", "D"]
    return "".join([letters[int(x)] for x in str(zlib.adler32(text.encode("UTF-8")))])


def first(*args: Iterable[object]) -> object:
    """first non-None value from *args ; fallback to empty string"""
    return next((item for item in args if item is not None), "")


def rebuild_uri(
    uri: urllib.parse.ParseResult,
    scheme: str = None,
    username: str = None,
    password: str = None,
    hostname: str = None,
    port: Union[str, int] = None,
    path: str = None,
    params: str = None,
    query: str = None,
    fragment: str = None,
) -> urllib.parse.ParseResult:
    """new named tuple from uri with request part updated"""
    username = first(username, uri.username, "")
    password = first(password, uri.password, "")
    hostname = first(hostname, uri.hostname, "")
    port = first(port, uri.port, "")
    netloc = (
        f"{username}{':' if password else ''}{password}"
        f"{'@' if username or password else ''}{hostname}"
        f"{':' if port else ''}{port}"
    )
    return urllib.parse.urlparse(
        urllib.parse.urlunparse(
            (
                first(scheme, uri.scheme),
                netloc,
                first(path, uri.path),
                first(params, uri.params),
                first(query, uri.query),
                first(fragment, uri.fragment),
            )
        )
    )


def is_running_inside_container():
    """whether currently running from inside a container (Docker most likely)"""
    fpath = pathlib.Path("/proc/self/cgroup")
    if not fpath.exists():
        return False
    try:
        with open(fpath, "r") as fh:
            for line in fh.readlines():
                if line.strip().rsplit(":", 1)[-1] != "/":
                    return True
    finally:
        pass
    return False


is_inside_container = is_running_inside_container()


def get_available_memory():
    """Available RAM in system (container if inside one) in bytes"""
    if is_inside_container:
        with open("/sys/fs/cgroup/memory/memory.limit_in_bytes", "r") as fp:
            mem_total = int(fp.read().strip())
        with open("/sys/fs/cgroup/memory/memory.usage_in_bytes", "r") as fp:
            mem_used = int(fp.read().strip())
        return mem_total - mem_used

    return psutil.virtual_memory().available


class BoundedThreadPoolExecutor(cf.ThreadPoolExecutor):
    """Regular ThreadPoolExecutor with SimpleQueue replaced by bounded FIFO one

    TPE uses an unbounded FIFO queue to stack jobs until those are fetched by workers.
    As we usually parse XML files very fast and submit jobs directly, we end up
    with an incredibly large queue that keeps growing to millions of entries, increasing
    the gap between submitted and processed job.

    Using a bounded queue, submit() is blocked until a new slot is available so the
    workers are always at most queue-size jobs behind submitted ones.

    This keeps parsing and processing progress in sync and caps memory usage"""

    def __init__(
        self,
        queue_size,
        max_workers=None,
        thread_name_prefix="",
        initializer=None,
        initargs=(),
    ):

        super().__init__(max_workers, thread_name_prefix, initializer, initargs)
        self._work_queue = queue.Queue(maxsize=queue_size)
