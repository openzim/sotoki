#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging
import pathlib
import subprocess

import py7zr

from .misc import has_binary

logger = logging.getLogger(__name__)
has_p7zip = has_binary("7z")


def extract_using_p7z(
    src: pathlib.Path, to_dir: pathlib.Path, delete_src: bool = False
):
    """Extract a single 7z file into to_dir using p7zip (fast)"""
    args = ["/usr/bin/env", "7z", "x", "-y", f"-o{to_dir}", str(src)]
    logger.debug(f"Running {args}")
    p7z = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if not p7z.returncode == 0:
        logger.error(f"Error running {args}: returned {p7z.returncode}\n{p7z.stdout}")
        raise subprocess.CalledProcessError(p7z.returncode, args)

    if delete_src:
        src.unlink()


def extract_using_python(
    src: pathlib.Path, to_dir: pathlib.Path, delete_src: bool = False
):
    """Extract a single 7z file into to_dir using python.

    Slower than p7zip but doesn't depend on it"""
    archive = py7zr.SevenZipFile(str(src), mode="r")
    archive.extractall(path=to_dir)
    archive.close()
    if delete_src:
        src.unlink()


def extract_7z(src: pathlib.Path, to_dir: pathlib.Path, delete_src: bool = False):
    """Extract single 7z file into to_dir using p7zip if avail, fallback to python"""
    func = extract_using_p7z if has_p7zip else extract_using_python
    return func(src=src, to_dir=to_dir, delete_src=delete_src)
