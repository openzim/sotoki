## Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (as of version 2.0.1).

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
