#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import sys
import pathlib


def main():
    # allows running it from source using python sotoki
    sys.path = [str(pathlib.Path(__file__).parent.parent.resolve())] + sys.path

    from sotoki.entrypoint import main as entry

    entry()


if __name__ == "__main__":
    main()
