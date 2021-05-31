#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import logging
import subprocess

logger = logging.getLogger(__name__)


def has_binary(name):
    return (
        subprocess.run(
            ["/usr/bin/env", "command", "-v", name], stdout=subprocess.DEVNULL
        ).returncode
        == 0
    )
