#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu


from ..constants import getLogger

from slugify import slugify
from bs4 import BeautifulSoup


logger = getLogger()


def get_text(content: str, strip_at: int = -1):
    """extracted text from an HTML source, optionaly striped"""
    text = BeautifulSoup(content, "lxml").text
    if strip_at and len(text) > strip_at:
        return f'{text[0:strip_at].rsplit(" ", 1)[0]}…'
    return text


def get_slug_for(title: str):
    """stackexchange-similar slug for a title"""
    return slugify(title)[:78]
