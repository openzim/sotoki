## Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (as of version 2.0.1).

## [2.2.1] - 2025-06-26

### Fixed

- Reduce number of workers and add backoff on 429 and non-HTTP (network, ...) errors

### Changed

- Changed default `--redis-url` behavior (#333)
  - It now uses the `REDIS_URL` environment variable if set, falling back to `redis://localhost:6379`.
  - Docker image sets `REDIS_URL` to `unix:///var/run/redis.sock` by default.

## [2.2.0] - 2025-06-10

### Changed

- Breaking changes: adapt to new StackExchange dumps and missing Sites.xml (#322)
  - Only working on recent dumps (June 2024 and later)
  - `--title` and `--description` CLI parameters are now mandatory to specify ZIM metadata
  - Dropped `-l`/`--list-all` CLI action to list all SE sites (not working anymore)

### Fixed

- Fix duplicate english Language metadata (#321)
- Change image processing order to save memory (#325)
- Fix confusion between selection and flavour in ZIM name (#327)
- New XML dump files have changed (#329)

## [2.1.3] - 2024-10-29

### Fixed

- Fix Mathjax equations not displayed properly (#283)

## [2.1.2] - 2024-05-13

### Fixed

- User icons don't load properly (#301)
- Revert adaptations to upstream XML format changes (#313)

## [2.1.1] - 2024-05-07

### Fixed

- Adapt to upstream XML format changes (#305)
- Add continuous delivery to Pypi (#303)

## [2.1.0] - 2024-03-28

### Added

- Redirection from `/questions/{questionId}` to the question page (#277)

### Changed

- ZIM Tags now include `_videos:no;_details:no` and conditionaly include `_pictures:no` (#278)
- Default filename now uses `nopic` instead of `all` if using `--without-images` (#278)
- Multi-language domains now handled as such:
  - `Language` metadata to be set to `eng,xxx` (xxx being the second language)
  - `Name` metadata to be like "{domain}_mul_{variant}"
  - Filename metadata to match `Name`
- Using zimscraperlib 3.3
- Changed default publisher metadata from 'Kiwix' to 'openZIM'
- `description` metadata is now limited to 80 chars, full description goes to the `long_description` (#290)

### Fixed

- Multilanguage ZIM are not perfectly handled (#259)
- Incorrect image displayed (#284)
- Markdown text formatting is not rendered (#286)
- Harmonize default publisher to openZIM (#291)
- Docker image: align redis binaries with Python distribution (#294)
- Issue with xml.sax.saxutils (#298)

## [2.0.2] - 2022-10-31

### Changed

- Fixed language-code-looking project codes setting incorrect Language (`ell`, `or`, `vi`)
- Fixed `--name` parameter not being used to set Name nor filename (#267)
- Sax parser now explicitly closed after use
- Fixed same-protocol links being considered relative paths during rewriting (#265)
- More reliable database commits
- Updated to zimscraperlib 1.8.0 and lxml 4.9.1
- Removed inline JS to comply with some CSP
- renamed `redis` module to avoid confusion
- External link icon now inc

## [2.0.1] - 2022-05-26

### Changed

- Default Name (and thus default filename) now uses plain {domain} instead of replacing `.` with `_`.
- Default Name includes language and `_all` (#250 #251)
- Fixed crash when first post in XML dump has zero comments (#254)
- Image requests now uses a User-Agent header (#252)
- Fixed an issue completing process at very end (#253)
- Using zimscraperlib v1.6 (libzim 1.1.0)

## [2.0.0] - 2022-05-1

- rewrite using python-libzim (libzim7)
- added --list-all option to list all available stackexchange domains
- added --preparation-only to only prepare XML files
- faster XML dumps creation step (x5)

## [1.3.2.dev0]

* removed pre-generated identicons (#141)
* removed templates_mini
* upgraded jdenticon to 2.2.0
* single identicon behavior for normal and nopic mode
* add `--no-identicons` option to skip downloading identicons and use only generated ones
* use pylibzim to create ZIM file
* properly handle root-relative links
* removed zipping HTML files on disk and use of --inflateHTML zimwriterfs option
* fix invalid tag internal links
* user profile links now redirect to online version if `--nouserprofile` option is passed
* `.html` extension is now removed from the articles
* internal link redirection is now possible from user profiles
* error during ZIM creation now properly returns 1
* handle internal `/` link

## [1.3.1]

* fixed identicons for missing source image (#142)
* use magic for filetype identification
* log on successful downloads
* do not depend on headers for filetype identification
* use Pillow to convert images (except GIF) to PNG
* use Pillow to resize images (except GIF)
* Download using save_large_file from zimscraperlib
* Prevent a crash in nopic mode if temp dir and output dir on different disks
* Added timeout on HEAD request
* Better handling of images with misleading extensions

## [1.3]

* better logging
* added suppot for optimizaton-cache (S3)
* fixed temp files being left on disk after image conversion errors
* fixed favicon conversion to png
* fixed crash on empty text comment
* fixed some links not working (#129)
* improved plain text links support.
* added support for images in comments
* updated dependencies (mistune, beautifulsoup, Pillow)
* fixed missing index in ZIM
* fixed gif to png conversion
* better filetype checking: fallback to magic no known filetype found in header
* replaced filemagic with python-magic

## [1.2.1]

* image optimization now performed in memory (/dev/shm) if possible (#84)
* improved Usage wording
* fixed regression from 1.2 on image conversion to PNG
* bumped external image optimizers versions
* fixed failed-to-optimize image being left on disk (#111)

## [1.2]

* Switched to python3, abandonning python2 support (#92)
* Added warning before long extract operation (#91)
* Enabled Mathjax everywhere (#98)
* Fixed redirects by fixing redirects TSV format (#95)
* Introduced changelog (#88)
* Fixed /tmp being filled with files (#88)
* Changed image optimization timeout (20s vs 10s before)
* Image optim and resize in memory (/dev/shm) if possible (#84)

## [1.1.2]

* Added `physics.stackexchange.com` to list of Mathjax domains

## [1.1.1]

* Initial version
