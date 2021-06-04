#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

""" Stack Exchanges Sites details from Sites.xml file

    Each Site in Stack Exchange galaxy is listed in this Sites.xml file which
    also includes some metadata:

    - Id:                   22
    - TynyName:             programmers
    - Name:                 Software Engineering
    - LongName:             Software Engineering
    - Url:                  https://softwareengineering.stackexchange.com
    - ImageUrl:             Wide PNG logo
    - IconUrl:              16x16 PNG favicon
    - DatabaseName:         StackExchange.Programmers
    - Tagline:              Q&amp;A for professionals, academics, and stu...
    - TagCss:               some custom CSS
    - TotalQuestions:       58740
    - TotalAnswers:         167762
    - TotalUsers:           326498
    - TotalComments:        503659
    - TotalTags:            1662
    - LastPost:             2021-02-28T04:56:10.200
    - BadgeIconUrl:         square icon suitable for our Zim Illustration
    """

import io
from typing import List

from xml_to_dict import XMLtoDict
from zimscraperlib.download import stream_file

from ..constants import DOWNLOAD_ROOT


def get_all_sites() -> List[dict]:
    """List of all StackExchange Sites with basic details"""
    url = f"{DOWNLOAD_ROOT}/Sites.xml"
    buf = io.BytesIO()
    stream_file(url, byte_stream=buf)

    parser = XMLtoDict()
    return parser.parse(buf.getvalue()).get("sites", {}).get("row", [])


def get_site(domain) -> dict:
    """Details for a single StackExchange site"""
    for site in get_all_sites():
        if site.get("@Url") == f"https://{domain}":
            for key in list(site.keys()):
                site[key.replace("@", "")] = site[key]
                del site[key]
            site["Domain"] = domain
            return site
