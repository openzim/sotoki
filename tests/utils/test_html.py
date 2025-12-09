from sotoki.utils.html import get_text


class TestGetText:
    """Test basic get_text functionality without stripping"""

    def test_plain_text(self):
        """Should extract plain text from HTML"""
        content = "<p>Hello world</p>"
        result = get_text(content)
        assert result == "Hello world"

    def test_empty_content(self):
        """Should handle empty content"""
        result = get_text("")
        assert result == ""

    def test_nested_tags(self):
        """Should extract text from nested HTML tags"""
        content = "<div><p>Hello <strong>world</strong></p></div>"
        result = get_text(content)
        assert result == "Hello world"

    def test_multiple_paragraphs(self):
        """Should extract text from multiple paragraphs"""
        content = "<p>First paragraph</p><p>Second paragraph</p>"
        result = get_text(content)
        assert result == "First paragraph Second paragraph"

    def test_default_no_strip(self):
        """Should not strip when strip_at is -1 (default)"""
        content = "<p>" + "a" * 500 + "</p>"
        result = get_text(content)
        assert result == "a" * 500

    def test_negative_strip_at(self):
        """Should not strip when strip_at is negative"""
        content = "<p>This is a long text</p>"
        result = get_text(content, strip_at=-1)
        assert result == "This is a long text"

    def test_strip_at_word_boundary(self):
        """Should strip at word boundary, not mid-word"""
        content = "<p>This is a test sentence</p>"
        result = get_text(content, strip_at=10)
        assert result == "This is a…"

    def test_strip_at_zero(self):
        """Should handle strip_at=0"""
        content = "<p>Any text here</p>"
        result = get_text(content, strip_at=0)
        # strip_at=0 is falsy in the condition, should not strip
        assert result == "Any text here"

    def test_html_with_code_blocks(self):
        """Should handle code blocks"""
        content = "<p>Here is code: <code>print('hello')</code> and more text</p>"
        result = get_text(content, strip_at=45)
        assert result == "Here is code: print(&#x27;hello&#x27;) and more text"

    def test_html_with_links(self):
        """Should handle links"""
        content = (
            '<p>Visit <a href="http://example.com"> this link</a> for more '
            "information</p>"
        )
        result = get_text(content, strip_at=20)
        assert result == "Visit this link for…"

    def test_html_with_line_breaks(self):
        """Should handle line breaks"""
        content = "<p>Line one<br/>Line two<br/>Line three with more text</p>"
        result = get_text(content, strip_at=15)
        assert result == "Line one Line…"

    def test_html_entities(self):
        """Should handle HTML entities correctly"""
        content = "<p>This &amp; that &lt;tag&gt; and more</p>"
        result = get_text(content, strip_at=30)
        # BeautifulSoup decodes HTML entities, then we strip,
        # then we escape again, so here no stripping should be
        # made even if final result is more than 30 characters
        assert result == "This &amp; that &lt;tag&gt; and more"

    def test_very_long_single_word(self):
        """Should handle very long single word"""
        content = "<p>" + "a" * 300 + "</p>"
        result = get_text(content, strip_at=100)
        # Since there's no space, rsplit won't work well
        # This tests edge case behavior
        assert result == "a" * 100 + "…"

    def test_whitespace_handling(self):
        """Should handle multiple spaces and newlines in HTML"""
        content = """<p>Word1


        Word2   Word3     Word4</p>"""
        result = get_text(content, strip_at=24)
        # Whitespace should be normalized before stripping
        assert result == "Word1 Word2 Word3 Word4"

    def test_empty_tags(self):
        """Should handle empty tags"""
        content = "<p>Before<strong></strong>After</p>"
        result = get_text(content)
        assert result == "Before After"

    def test_strip_at_exactly_content_length(self):
        """Should handle strip_at equal to content length"""
        content = "<p>Exactly twenty chars</p>"  # 20 chars
        result = get_text(content, strip_at=20)
        # Content is not longer than strip_at, should not strip
        assert result == "Exactly twenty chars"

    def test_strip_at_one_more_than_content(self):
        """Should not strip if content is exactly at limit"""
        content = "<p>Exactly twenty chars</p>"  # 20 chars
        result = get_text(content, strip_at=21)
        # Content is not longer than strip_at, should not strip
        assert result == "Exactly twenty chars"

    def test_only_spaces_after_strip_point(self):
        """Should handle case where only spaces after strip point"""
        content = "<p>Some text        </p>"
        result = get_text(content, strip_at=9)
        assert result == "Some text"

    def test_mixed_content_types(self):
        """Should handle mixed content with lists, paragraphs, etc."""
        content = """
        <div>
            <p>First
            paragraph with some text</p>
            <ul>
                <li>List item one</li>
                <li>List item two</li>
            </ul>
            <p>Second paragraph here</p>
        </div>
        """
        result = get_text(content, strip_at=30)
        assert result == "First paragraph with some…"

    def test_escaped_code(self):
        """Should handle mixed content with lists, paragraphs, etc."""
        content = """<code>&lt;?php if(current_user_can('editor')) { ?&gt;</code>
        """
        result = get_text(content, strip_at=40)
        assert result == "&lt;?php if(current_user_can(&#x27;editor&#x27;)) {…"
