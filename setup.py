from setuptools import setup, find_packages

setup(
    name="sotoki",
    version="1.1",
    description="Make zimfile from stackexchange dump",
    long_description=open("README.md").read(),
    author="dattaz",
    author_email="taz@dattaz.fr",
    url="http://github.com/kiwix/sotoki",
    keywords="kiwix zim stackexchange offline",
    license="GPL",
    packages=find_packages(exclude=["contrib", "docs", "tests*"]),
    install_requires=[
        "Jinja2",
        "lxml",
        "MarkupSafe",
        "docopt",
        #        'slugify', # do not exist for python 3
        "python-slugify",
        "pydenticon",
        "bs4",
        "envoy",
        "subprocess32",
        "filemagic",
        "mistune>=2.0.0a2",
    ],
    zip_safe=False,
    platforms="Linux",
    include_package_data=True,
    entry_points={"console_scripts": ["sotoki=sotoki.sotoki:run"],},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
    ],
)
