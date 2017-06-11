from setuptools import setup, find_packages
from pip.req import parse_requirements

setup(
    name='sotoki',
        version='0.8',
    description="Make zimfile from stackexchange dump",
    long_description=open('README.md').read(),
    author='dattaz',
    author_email='taz@dattaz.fr',
    url='http://github.com/kiwix/sotoki',
    keywords="kiwix zim stackexchange offline",
    license="GPL",
    packages=find_packages(exclude=['contrib', 'docs', 'tests*']),
    install_requires=[
        'Jinja2==2.8',
        'lxml==3.4.4',
        'MarkupSafe==0.23',
        'docopt==0.6.2',
        'slugify==0.0.1',
        'pydenticon==0.2',
        'bs4',
        'envoy',
        'subprocess32',
        'filemagic',
        'mistune'
        ],
    zip_safe=False,
    platforms='Linux',
    include_package_data=True,
    entry_points={
            'console_scripts': ['sotoki=sotoki.sotoki:run'],
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7'
    ],
)
