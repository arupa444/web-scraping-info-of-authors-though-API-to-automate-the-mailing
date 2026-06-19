from icereach.services.blocks import blocks_to_text, render_blocks


def test_renders_container_and_blocks():
    html = render_blocks([
        {"type": "heading", "text": "Welcome {name}", "level": 1},
        {"type": "text", "html": "<b>Hi</b> there"},
        {"type": "button", "text": "Shop", "url": "https://acme.com"},
        {"type": "divider"},
        {"type": "image", "src": "https://acme.com/logo.png", "alt": "logo"},
        {"type": "spacer", "height": 32},
    ])
    assert "<table" in html and "max-width:600px" in html
    assert "<h1" in html
    assert "Welcome {name}" in html          # merge tag preserved verbatim
    assert "https://acme.com" in html
    assert "<img" in html and "logo" in html
    assert "height:32px" in html


def test_list_and_quote_blocks_render():
    html = render_blocks([
        {"type": "list", "items": ["One", "Two", ""], "ordered": False},
        {"type": "list", "items": ["A"], "ordered": True},
        {"type": "quote", "text": "Be bold {name}", "cite": "Jane"},
    ])
    assert "<ul" in html and "<li" in html
    assert "<ol" in html
    assert "One" in html and "Two" in html
    assert "<blockquote" in html and "Be bold {name}" in html and "Jane" in html


def test_columns_render_two_cells():
    html = render_blocks([
        {"type": "columns", "columns": [
            [{"type": "text", "html": "Left"}],
            [{"type": "text", "html": "Right"}],
        ]}
    ])
    assert html.count('width="50%"') == 2
    assert "Left" in html and "Right" in html


def test_unknown_block_skipped():
    html = render_blocks([{"type": "mystery"}, {"type": "heading", "text": "Real"}])
    assert "Real" in html


def test_text_alternative_extracts_content():
    text = blocks_to_text([{"type": "heading", "text": "Hello"}, {"type": "text", "html": "<p>World</p>"}])
    assert "Hello" in text and "World" in text


def test_escapes_heading_but_not_text_html():
    html = render_blocks([
        {"type": "heading", "text": "<script>bad</script>"},
        {"type": "text", "html": "<em>ok</em>"},
    ])
    assert "<script>bad" not in html         # heading text is escaped
    assert "&lt;script&gt;" in html
    assert "<em>ok</em>" in html             # text block HTML preserved
