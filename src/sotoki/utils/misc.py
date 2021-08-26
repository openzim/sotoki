#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import zlib
import pathlib
import platform
import subprocess
import urllib.parse
from typing import Union, Iterable

import psutil

from .shared import logger


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
    failsafe: bool = False,
) -> urllib.parse.ParseResult:
    """new named tuple from uri with request part updated"""
    try:
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
    except Exception as exc:
        if failsafe:
            logger.error(
                f"Failed to rebuild "  # lgtm [py/clear-text-logging-sensitive-data]
                f"URI {uri} with {scheme=} {username=} {password=} "
                f"{hostname=} {port=} {path=} "
                f"{params=} {query=} {fragment=} - {exc}"
            )
            return uri
        raise exc


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


def restart_redis_at(pid: Union[str, int]):
    """restart redis-server so it reallocates from dump, eliminating fragmentation"""
    if pid == "service":
        logger.debug("Restarting redis")
        if platform.system() == "Darwin":
            subprocess.run(
                ["/usr/bin/env", "brew", "services", "stop", "redis"], check=True
            )
            subprocess.run(
                ["/usr/bin/env", "brew", "services", "start", "redis"], check=True
            )
            return
        subprocess.run(["/usr/bin/env", "service", "redis-server", "stop"], check=True)

    logger.debug(f"Looking for redis at PID {pid}")
    ps = psutil.Process(pid)
    logger.debug(f"Calling `redis-restart {pid}`")
    subprocess.run(
        ["/usr/bin/env", "redis-restart", str(pid)], cwd=ps.cwd(), check=True
    )
