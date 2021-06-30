#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import zlib
import logging
import subprocess
import urllib.parse

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


def rebuild_uri(
    uri,
    scheme=None,
    username=None,
    password=None,
    hostname=None,
    port=None,
    path=None,
    params=None,
    query=None,
    fragment=None,
):
    """new named tuple from uri with request part updated"""
    scheme = scheme or uri.scheme
    username = username or uri.username
    password = password or uri.password
    hostname = hostname or uri.hostname
    port = port or uri.port
    path = path or uri.path
    netloc = ""
    if username:
        netloc += username
    if password:
        netloc += f":{password}"
    if username or password:
        netloc += "@"
    if hostname:
        netloc += hostname
    if port:
        netloc += f":{port}"
    params = params or uri.params
    query = query or uri.query
    fragment = fragment or uri.fragment
    return urllib.parse.urlparse(
        urllib.parse.urlunparse([scheme, netloc, path, params, query, fragment])
    )
