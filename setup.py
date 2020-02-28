import pathlib

from setuptools import setup, find_packages

root_dir = pathlib.Path(__file__).parent
with open(root_dir.joinpath("requirements.txt"), "r") as fh:
    requirements = fh.read()

setup(
    name="sotoki",
    version="1.2",
    description="Make zimfile from stackexchange dump",
    long_description=open("README.md").read(),
    author="dattaz",
    author_email="taz@dattaz.fr",
    url="http://github.com/kiwix/sotoki",
    keywords="kiwix zim stackexchange offline",
    license="GPL",
    packages=find_packages(exclude=["contrib", "docs", "tests*"]),
    install_requires=[
        line.strip()
        for line in requirements.splitlines()
        if not line.strip().startswith("#")
    ],
    zip_safe=False,
    platforms="Linux",
    include_package_data=True,
    entry_points={"console_scripts": ["sotoki=sotoki.sotoki:run"]},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
    ],
)
