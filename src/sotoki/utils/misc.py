#!/usr/bin/env python

import pathlib
import platform
import subprocess
import urllib.parse
import zlib
from functools import partial
from http import HTTPStatus
from typing import Any

import backoff
import psutil
import requests

from sotoki.utils.shared import logger


def has_binary(name):
    """whether system has this binary in PATH"""
    return (
        subprocess.run(
            ["/usr/bin/env", "which", name], check=False, stdout=subprocess.DEVNULL
        ).returncode
        == 0
    )


def get_short_hash(text: str) -> str:
    letters = ["E", "T", "A", "I", "N", "O", "S", "H", "R", "D"]
    return "".join([letters[int(x)] for x in str(zlib.adler32(text.encode("UTF-8")))])


def first(*args: str | None) -> str:
    """first non-None value from *args ; fallback to empty string"""
    return next((item for item in args if item is not None), "")


def rebuild_uri(
    uri: urllib.parse.ParseResult,
    *,
    scheme: str | None = None,
    username: str | None = None,
    password: str | None = None,
    hostname: str | None = None,
    port: str | int | None = None,
    path: str | None = None,
    params: str | None = None,
    query: str | None = None,
    fragment: str | None = None,
    failsafe: bool | None = False,
) -> urllib.parse.ParseResult:
    """new named tuple from uri with request part updated"""
    try:
        username = first(username, uri.username, "")
        password = first(password, uri.password, "")
        hostname = first(hostname, uri.hostname, "")
        port = first(str(port), str(uri.port), "")
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


def get_available_memory():
    """Available RAM in system (container if inside one) in bytes"""
    cgroup_memory_limit_file = pathlib.Path(
        "/sys/fs/cgroup/memory/memory.limit_in_bytes"
    )
    cgroup_memory_usage_file = pathlib.Path(
        "/sys/fs/cgroup/memory/memory.usage_in_bytes"
    )
    if cgroup_memory_limit_file.exists() and cgroup_memory_usage_file.exists():
        with open(cgroup_memory_limit_file) as fp:
            mem_total = int(fp.read().strip())
        with open(cgroup_memory_usage_file) as fp:
            mem_used = int(fp.read().strip())
        return mem_total - mem_used

    return psutil.virtual_memory().available


def restart_redis_at(pid: str | int):
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
        else:
            raise NotImplementedError()  # looks like it is not completely implemented
            subprocess.run(
                ["/usr/bin/env", "service", "redis-server", "stop"], check=True
            )

    if isinstance(pid, str):
        raise Exception(f"Unsupported Redis PID for restart: {pid}")
    logger.debug(f"Looking for redis at PID {pid}")
    ps = psutil.Process(pid)
    logger.debug(f"Calling `redis-restart {pid}`")
    subprocess.run(
        ["/usr/bin/env", "redis-restart", str(pid)], cwd=ps.cwd(), check=True
    )


def web_backoff(func):

    def backoff_hdlr(details: Any):
        """Default backoff handler to log something when backoff occurs"""
        logger.debug(
            "Request error, starting backoff of {wait:0.1f} seconds after {tries} "
            "tries. Exception: {exception}".format(**details)
        )

    def should_giveup(exc):
        if isinstance(exc, requests.HTTPError):
            return (
                exc.response is not None
                and exc.response.status_code != HTTPStatus.TOO_MANY_REQUESTS
            )
        return False  # Retry for all other RequestException types

    return backoff.on_exception(
        partial(backoff.expo, base=3, factor=2),
        requests.RequestException,
        max_time=60,  # secs
        on_backoff=backoff_hdlr,
        giveup=should_giveup,
    )(func)
