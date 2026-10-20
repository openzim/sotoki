import re
from pathlib import Path

import pytest
from zimscraperlib.zim import Archive

# Paths which are always present in the ZIM, whatever the scraped domain is. A ZIM
# missing any of those (or with empty content) is a full regression that zimcheck
# would not catch.
EXPECTED_FILES = [
    pytest.param("favicon.ico", "image/", id="favicon.ico"),
    pytest.param("apple-touch-icon.png", "image/png", id="apple-touch-icon.png"),
    pytest.param("about", "text/html", id="about"),
    pytest.param("users", "text/html", id="users"),
    pytest.param("tags", "text/html", id="tags"),
    pytest.param("api/tags.json", "application/json", id="api/tags.json"),
    pytest.param("static/css/sotoki.css", "text/css", id="static/css/sotoki.css"),
    pytest.param("static/css/stacks.css", "text/css", id="static/css/stacks.css"),
    pytest.param("static/css/primary.css", "text/css", id="static/css/primary.css"),
    pytest.param("static/css/secondary.css", "text/css", id="static/css/secondary.css"),
    pytest.param("static/img/home.svg", "image/svg+xml", id="static/img/home.svg"),
    pytest.param("Img/user.svg", "image/svg+xml", id="Img/user.svg"),
]

# JavaScript mimetype is environment-dependent (text/javascript or
# application/javascript), so it is matched with a dedicated test
EXPECTED_JS_FILES = [
    pytest.param("static/js/fromnow.js", id="static/js/fromnow.js"),
    pytest.param("static/js/jdenticon.min.js", id="static/js/jdenticon.min.js"),
    pytest.param("static/js/moment.min.js", id="static/js/moment.min.js"),
]

POST_PATH_RE = re.compile(r"^questions/\d+/")


def test_is_file(zim_file_path: Path):
    """Ensure ZIM file exists"""
    assert zim_file_path.exists()
    assert zim_file_path.is_file()


def test_zim_main_page(zim_fh: Archive):
    """Ensure main page is a redirect to the questions homepage"""
    main_entry = zim_fh.main_entry
    assert main_entry.is_redirect
    assert main_entry.get_redirect_entry().path == "questions"

    homepage = zim_fh.get_item("questions")
    assert homepage.mimetype == "text/html"
    # the homepage should list the questions, not be a minimal placeholder
    assert b"Most Popular" in bytes(homepage.content)
    assert len(bytes(homepage.content)) > 1000


def test_zim_metadata(zim_fh: Archive):
    """Ensure scraper and ZIM metadata are present and correct"""
    assert "sotoki v" in zim_fh.get_text_metadata("Scraper")
    assert zim_fh.get_text_metadata("Name")
    assert zim_fh.get_text_metadata("Title") == "Alcohol StackExchange Meta"
    assert (
        zim_fh.get_text_metadata("Description")
        == "Meta for StackExchange questions about beer, wine & spirits"
    )
    assert zim_fh.get_text_metadata("Language") == "eng"
    assert zim_fh.get_text_metadata("Creator") == "Stack Exchange"
    assert zim_fh.get_text_metadata("Publisher") == "openZIM"


@pytest.mark.parametrize("item_path,expected_mimetype", EXPECTED_FILES)
def test_zim_content_expected_files(
    zim_fh: Archive, item_path: str, expected_mimetype: str
):
    """Ensure important files are present, with proper mimetype and non-empty"""
    item = zim_fh.get_item(item_path)
    assert item.mimetype.startswith(expected_mimetype)
    assert len(bytes(item.content)) > 0


@pytest.mark.parametrize("item_path", EXPECTED_JS_FILES)
def test_zim_content_expected_js_files(zim_fh: Archive, item_path: str):
    """Ensure JS files are present, with a javascript mimetype and non-empty"""
    item = zim_fh.get_item(item_path)
    assert item.mimetype.endswith("javascript")
    assert len(bytes(item.content)) > 0


def test_zim_content_not_empty(zim_fh: Archive):
    """Ensure the ZIM contains a substantial amount of content

    zimcheck would be happy with a ZIM containing only a few items, so we make sure
    articles and media are actually there.
    """
    assert zim_fh.article_count > 0
    assert zim_fh.media_count > 0


def test_zim_content_post_pages(zim_fh: Archive):
    """Ensure at least one question page is present, non-empty and well-formed"""
    post_paths = [
        entry.path
        for entry in (zim_fh.get_entry_by_id(i) for i in range(zim_fh.entry_count))
        if not entry.is_redirect and POST_PATH_RE.match(entry.path)
    ]
    assert post_paths

    post = zim_fh.get_item(post_paths[0])
    content = bytes(post.content)
    assert post.mimetype == "text/html"
    assert b"<html" in content.lower()
