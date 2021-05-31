#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import io

from xml_to_dict import XMLtoDict
from zimscraperlib.download import stream_file

from ..constants import DOWNLOAD_ROOT


def get_all_sites():
    url = f"{DOWNLOAD_ROOT}/Sites.xml"
    buf = io.BytesIO()
    stream_file(url, byte_stream=buf)

    parser = XMLtoDict()
    return parser.parse(buf.getvalue()).get("sites", {}).get("row", [])
