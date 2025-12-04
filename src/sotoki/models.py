from dataclasses import dataclass


@dataclass(kw_only=True)
class SiteDetails:
    mathjax: bool
    highlight: bool
    domain: str
    site_title: str
    primary_css: str
    secondary_css: str
    small_favicon: str
    big_favicon: str
