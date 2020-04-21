### 1.3

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

## 1.2.1

* image optimization now performed in memory (/dev/shm) if possible (#84)
* improved Usage wording
* fixed regression from 1.2 on image conversion to PNG
* bumped external image optimizers versions
* fixed failed-to-optimize image being left on disk (#111)

## 1.2

* Switched to python3, abandonning python2 support (#92)
* Added warning before long extract operation (#91)
* Enabled Mathjax everywhere (#98)
* Fixed redirects by fixing redirects TSV format (#95)
* Introduced changelog (#88)
* Fixed /tmp being filled with files (#88)
* Changed image optimization timeout (20s vs 10s before)
* Image optim and resize in memory (/dev/shm) if possible (#84)

## 1.1.2

* Added `physics.stackexchange.com` to list of Mathjax domains

## 1.1.1

* Initial version
