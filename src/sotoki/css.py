from io import BytesIO

from zimscraperlib.download import stream_file
from zimscraperlib.rewriting.css import CssRewriter
from zimscraperlib.rewriting.url_rewriting import (
    ArticleUrlRewriter,
    HttpUrl,
    RewriteResult,
    ZimPath,
)

from sotoki.constants import USER_AGENT
from sotoki.utils.shared import shared


def process_css(online_url: str, filename: str):
    css_zim_path = f"static/css/{filename}"
    dst = BytesIO()
    stream_file(url=online_url, byte_stream=dst, headers={"User-Agent": USER_AGENT})
    url_rewriter = CssUrlsRewriter(
        article_url=HttpUrl(online_url),
        article_path=ZimPath(css_zim_path),
    )
    css_rewriter = CssRewriter(
        url_rewriter=url_rewriter, base_href=None, remove_errors=True
    )
    result = css_rewriter.rewrite(content=dst.getvalue())
    shared.creator.add_item_for(css_zim_path, content=result, is_front=False)


class CssUrlsRewriter(ArticleUrlRewriter):
    """A rewriter for CSS processing, storing items to download as URL as processed"""

    def __call__(
        self,
        item_url: str,
        base_href: str | None,
        *,
        rewrite_all_url: bool = True,  # noqa: ARG002
    ) -> RewriteResult:
        result = super().__call__(item_url, base_href, rewrite_all_url=True)
        if result.zim_path is None:
            return result
        shared.imager.defer(result.absolute_url, result.zim_path.value)
        return result
