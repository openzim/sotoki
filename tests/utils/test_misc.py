import urllib.parse

import pytest

from sotoki.utils.misc import rebuild_uri


@pytest.mark.parametrize(
    "href, expected",
    [
        # relative in-ZIM links must stay relative (#443)
        ("../../questions/1/x", "../../questions/1/slug#5"),
        ("/questions/1/x", "../../questions/1/slug#5"),
        # an explicit port is kept
        (
            "https://example.com:8080/q/1",
            "https://example.com:8080/../../questions/1/slug#5",
        ),
    ],
)
def test_rebuild_uri_netloc(href, expected):
    uri = urllib.parse.urlparse(href)
    assert (
        rebuild_uri(uri=uri, path="../../questions/1/slug", fragment="5").geturl()
        == expected
    )
