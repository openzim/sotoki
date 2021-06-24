#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu

import sys
import pathlib
from setuptools import setup, find_packages

root_dir = pathlib.Path(__file__).parent

# download assets dependencies before packing
sys.path = [str(root_dir.joinpath("src").resolve())] + sys.path
from sotoki.dependencies import main as download_deps

download_deps()


def read(*names, **kwargs):
    with open(root_dir.joinpath(*names), "r") as fh:
        return fh.read()


setup(
    name="sotoki",
    version=read("src", "sotoki", "VERSION").strip(),
    description="Turn StackExchange dumps into ZIM files for offline usage",
    long_description=read("README.md"),
    long_description_content_type="text/markdown",
    author="Kiwix",
    author_email="contact+dev@kiwix.org",
    url="https://github.com/openzim/sotoki",
    keywords="kiwix zim offline stackechange stackoverflow",
    license="GPLv3+",
    packages=find_packages("src"),
    package_dir={"": "src"},
    install_requires=[
        line.strip()
        for line in read("requirements.txt").splitlines()
        if not line.strip().startswith("#")
    ],
    zip_safe=False,
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "sotoki=sotoki.__main__:main",
            "sotoki-deps-download=sotoki.dependencies:main",
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
    ],
    python_requires=">=3.6",
)
