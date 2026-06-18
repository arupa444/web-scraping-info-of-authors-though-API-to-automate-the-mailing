"""Tests for icereach.services.merge (render + html_to_text)."""

from icereach.services.merge import html_to_text, render


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------
def test_render_fills_known_tag():
    assert render("Hi {name}!", {"name": "Ada"}) == "Hi Ada!"


def test_render_leaves_missing_tag_intact():
    assert render("Hi {name}, your {missing} is ready", {"name": "Ada"}) == (
        "Hi Ada, your {missing} is ready"
    )


def test_render_coerces_non_string_values():
    assert render("count={n}", {"n": 3}) == "count=3"


def test_render_does_not_raise_on_stray_brace():
    # A lone '{' that is not a word-class token must pass through untouched.
    assert render("price is {} or { not a tag", {}) == "price is {} or { not a tag"


def test_render_multiple_tags():
    out = render("{a}-{b}-{a}", {"a": "x", "b": "y"})
    assert out == "x-y-x"


def test_render_empty_template_and_row():
    assert render("", {}) == ""


# --------------------------------------------------------------------------
# html_to_text
# --------------------------------------------------------------------------
def test_html_to_text_strips_tags():
    assert html_to_text("<p>Hello <b>world</b></p>") == "Hello world"


def test_html_to_text_keeps_link_url():
    out = html_to_text('Visit <a href="https://ex.com">our site</a> now')
    assert "our site (https://ex.com)" in out
    assert "https://ex.com" in out


def test_html_to_text_collapses_whitespace():
    # Runs of spaces/tabs within a line collapse to a single space.
    out = html_to_text("<p>foo    bar\t\t  baz</p>")
    assert out == "foo bar baz"


def test_html_to_text_br_and_p_become_newlines():
    out = html_to_text("line one<br>line two<p>para two</p>")
    lines = [ln for ln in out.split("\n") if ln]
    assert lines == ["line one", "line two", "para two"]


def test_html_to_text_drops_script_and_style():
    html = "<style>p{color:red}</style><p>visible</p><script>alert(1)</script>"
    assert html_to_text(html) == "visible"


def test_html_to_text_unescapes_entities():
    assert html_to_text("<p>Tom &amp; Jerry</p>") == "Tom & Jerry"
