#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ai ts=4 sts=4 et sw=4 nu
import pathlib

from zimscraperlib.download import stream_file

# (path, source)
ASSETS = [
    (
        "static/css/stacks.css",
        "https://cdn.sstatic.net/Shared/stacks.css?v=ca5319e49c63",
    ),
    (
        "static/js/tex-mml-chtml.js",
        "https://cdn.jsdelivr.net/npm/mathjax@3.1.3/es5/tex-mml-chtml.js",
    ),
    (
        "static/js/stack-icons.js",
        "https://unpkg.com/@stackoverflow/stacks-icons@2.20.0/build/index.js",
    ),
    ("static/js/moment.min.js", "https://momentjs.com/downloads/moment.min.js"),
    (
        "static/js/jdenticon.min.js",
        "https://raw.githubusercontent.com/dmester/jdenticon/3.1.0"
        "/dist/jdenticon.min.js",
    ),
    (
        "static/css/highlight.default.min.css",
        "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.1.0/styles/"
        "default.min.css",
    ),
    (
        "static/js/highlight.min.js",
        "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.1.0/highlight.min.js",
    ),
    # WepP Hero polyfill
    (
        "static/js/webp-hero.polyfill.js",
        "https://unpkg.com/webp-hero@0.0.0-dev.27/dist-cjs/polyfills.js",
    ),
    (
        "static/js/webp-hero.bundle.js",
        "https://unpkg.com/webp-hero@0.0.0-dev.27/dist-cjs/webp-hero.bundle.js",
    ),
    (
        "static/js/webp-handler.js",
        "https://gist.githubusercontent.com/rgaudin/60bb9cc6f187add506584258028b8ee1/"
        "raw/9d575b8e25d67eed2a9c9a91d3e053a0062d2fc7/web-handler.js",
    ),
    # MathJax dependencies. SE uses v2.7.5 ATM
    (
        "static/js/MathJax.js",
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/"
        "MathJax.js?config=TeX-AMS_HTML-full",
    ),
    (
        "static/js/config/TeX-AMS_HTML-full.js",
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/"
        "config/TeX-AMS_HTML-full.js?V=2.7.5",
    ),
    (
        "static/js/extensions/MathMenu.js",
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/"
        "extensions/MathMenu.js?V=2.7.5",
    ),
    (
        "static/js/extensions/MathZoom.js",
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/"
        "extensions/MathZoom.js?V=2.7.5",
    ),
    (
        "static/js/extensions/TeX/begingroup.js",
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/"
        "extensions/TeX/begingroup.js?V=2.7.5",
    ),
    (
        "static/js/jax/output/HTML-CSS/fonts/STIX/fontdata.js",
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/"
        "jax/output/HTML-CSS/fonts/STIX/fontdata.js?V=2.7.5",
    ),
    (
        "static/js/jax/element/mml/optable/BasicLatin.js",
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/"
        "jax/element/mml/optable/BasicLatin.js?V=2.7.5",
    ),
    (
        "static/js/jax/output/HTML-CSS/fonts/STIX/General/Italic/MathItalic.js",
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/"
        "jax/output/HTML-CSS/fonts/STIX/General/Italic/MathItalic.js?V=2.7.5",
    ),
    (
        "static/js/jax/output/HTML-CSS/fonts/STIX/General/Regular/MathItalic.js",
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/"
        "jax/output/HTML-CSS/fonts/STIX/General/Regular/MathItalic.js?V=2.7.5",
    ),
    (
        "static/js/jax/output/HTML-CSS/fonts/STIX/General/Italic/GreekItalic.js",
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/"
        "jax/output/HTML-CSS/fonts/STIX/General/Italic/GreekItalic.js?V=2.7.5",
    ),
    (
        "static/js/jax/output/HTML-CSS/fonts/STIX/General/Regular/GreekItalic.js",
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/"
        "jax/output/HTML-CSS/fonts/STIX/General/Regular/GreekItalic.js?V=2.7.5",
    ),
    (
        "static/js/jax/output/HTML-CSS/fonts/TeX/fontdata.js",
        "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.5/"
        "jax/output/HTML-CSS/fonts/TeX/fontdata.js?V=2.7.5",
    ),
    # following assets were manualy extracted from primary.css and secondary.css
    # those seem to be similar in all sites.
    # we may consider parsing those CSS to extract and include exact list should
    # this prove to be difficult to maintain
    (
        "Img/icon-envelope-fill-gray.png",
        "https://cdn.sstatic.net/Img/icon-envelope-fill-gray.png",
    ),
    (
        "Img/icon-envelope-fill-gray.svg",
        "https://cdn.sstatic.net/Img/icon-envelope-fill-gray.svg",
    ),
    (
        "Img/forms/icon-disabled.svg",
        "https://cdn.sstatic.net/Img/forms/icon-disabled.svg",
    ),
    (
        "Img/forms/icon-warning.svg",
        "https://cdn.sstatic.net/Img/forms/icon-warning.svg",
    ),
    ("Img/forms/icon-error.svg", "https://cdn.sstatic.net/Img/forms/icon-error.svg"),
    (
        "Img/forms/icon-success.svg",
        "https://cdn.sstatic.net/Img/forms/icon-success.svg",
    ),
    (
        "Img/hero/anonymousHeroBackground.svg",
        "https://cdn.sstatic.net/Img/hero/anonymousHeroBackground.svg",
    ),
    ("Img/img-upload.png", "https://cdn.sstatic.net/Img/img-upload.png"),
    (
        "Img/unified/sprites.png",
        "https://cdn.sstatic.net/Img/unified/sprites.png",
    ),
    (
        "Img/unified/sprites.svg",
        "https://cdn.sstatic.net/Img/unified/sprites.svg",
    ),
    (
        "Img/unifiedmeta/sprites.png",
        "https://cdn.sstatic.net/Img/unifiedmeta/sprites.png",
    ),
    (
        "Img/unified/wmd-buttons.svg",
        "https://cdn.sstatic.net/Img/unified/wmd-buttons.svg",
    ),
    (
        "Img/unified/wmd-buttons-dark.svg",
        "https://cdn.sstatic.net/Img/unified/wmd-buttons-dark.svg",
    ),
    ("Img/progress-dots.gif", "https://cdn.sstatic.net/Img/progress-dots.gif"),
    ("Img/share-sprite.png", "https://cdn.sstatic.net/Img/share-sprite.png"),
    (
        "Img/unifiedmeta/sprites.svg",
        "https://cdn.sstatic.net/Img/unifiedmeta/sprites.svg",
    ),
    (
        "Img/developer-story/timeline.svg",
        "https://cdn.sstatic.net/Img/developer-story/timeline.svg",
    ),
    (
        "Img/user-profile-sprite.png",
        "https://cdn.sstatic.net/Img/user-profile-sprite.png",
    ),
    (
        "Img/user-profile-sprite.svg",
        "https://cdn.sstatic.net/Img/user-profile-sprite.svg",
    ),
    ("Img/share-sprite-new.png", "https://cdn.sstatic.net/Img/share-sprite-new.png"),
    ("Img/share-sprite-new.svg", "https://cdn.sstatic.net/Img/share-sprite-new.svg"),
    ("Img/favicons-sprite16.png", "https://cdn.sstatic.net/Img/favicons-sprite16.png"),
    (
        "Img/favicons-sprite16-dark.png",
        "https://cdn.sstatic.net/Img/favicons-sprite16-dark.png",
    ),
    ("Img/favicons-sprite32.png", "https://cdn.sstatic.net/Img/favicons-sprite32.png"),
    (
        "Img/favicons-sprite32-dark.png",
        "https://cdn.sstatic.net/Img/favicons-sprite32-dark.png",
    ),
    ("Img/filter-sprites.png", "https://cdn.sstatic.net/Img/filter-sprites.png"),
    ("Img/filter-sprites.svg", "https://cdn.sstatic.net/Img/filter-sprites.svg"),
    ("Img/img-upload.svg", "https://cdn.sstatic.net/Img/img-upload.svg"),
    ("Img/user.svg", "https://cdn.sstatic.net/Img/user.svg"),
    ("Img/fatarrows.png", "https://cdn.sstatic.net/Img/fatarrows.png"),
    (
        "Img/open-graph/checkmark.png",
        "https://cdn.sstatic.net/Img/open-graph/checkmark.png",
    ),
]


def get_all_assets(cache):

    for path, source in ASSETS:
        target = cache.joinpath(path)
        if target.exists():
            continue

        if not target.parent.exists():
            target.parent.mkdir(exist_ok=True, parents=True)
        print(f"Downloading {source} into {target}")
        stream_file(url=source, fpath=target)


def main():
    get_all_assets(pathlib.Path(__file__).parent.joinpath("assets"))


if __name__ == "__main__":
    main()
