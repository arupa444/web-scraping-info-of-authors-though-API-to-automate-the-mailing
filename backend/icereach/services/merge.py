"""Merge-tag rendering and deterministic HTML-to-text conversion.

Ports the legacy ``render_template`` from ``app.py`` (~246): a ``{column}``
merge renderer where unknown keys are left intact and which never raises.
Also provides a stdlib-only ``html_to_text`` so every message can carry a
deterministic ``multipart/alternative`` plaintext part (spec §7.5/§8.7).
"""

import re
from html import unescape
from html.parser import HTMLParser

# Legacy merge regex (app.py ~246): a brace-wrapped word-class token.
_MERGE_RE = re.compile(r"{(\w+)}")

# Collapses any run of whitespace (incl. newlines) into a single space.
_WS_RE = re.compile(r"[^\S\n]+")
# Collapses three-or-more newlines down to a blank-line-separated pair.
_NL_RE = re.compile(r"\n{3,}")


def render(content: str, row: dict) -> str:
    """Render ``{column}`` merge tags in *content* from *row*.

    Each ``{key}`` is replaced by ``str(row[key])`` when the key is present.
    Keys missing from *row* are left intact (the literal ``{key}`` survives),
    matching the legacy literal-passthrough contract. Stray ``{`` / ``}`` that
    do not form a word-class token are ignored, so this never raises.

    Args:
        content: Template text containing zero or more ``{column}`` tags.
        row: Mapping of merge-tag names to substitution values.

    Returns:
        The rendered string with known tags substituted.
    """

    def _replace(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key in row:
            return str(row[key])
        # Leave unknown tags intact for downstream render-time validation.
        return "{" + key + "}"

    return _MERGE_RE.sub(_replace, content)


class _TextExtractor(HTMLParser):
    """Collect visible text from HTML, deterministically and stdlib-only.

    Block-ish tags (``<br>``, ``<p>``, headings, ``<div>``, ``<li>``) emit
    newlines; anchors are rendered as ``text (href)`` so the destination URL
    survives in the plaintext part. ``<script>``/``<style>`` content is dropped.
    """

    _NEWLINE_TAGS = frozenset(
        {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
    )
    _SKIP_TAGS = frozenset({"script", "style"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0
        self._href: str | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "br":
            self._parts.append("\n")
        elif tag in self._NEWLINE_TAGS:
            self._parts.append("\n")
        if tag == "a":
            self._href = dict(attrs).get("href")

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        # Self-closing form, e.g. ``<br/>``.
        if tag == "br" or tag in self._NEWLINE_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if tag == "a" and self._href:
            self._parts.append(f" ({self._href})")
            self._href = None
        if tag in self._NEWLINE_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        return "".join(self._parts)


def html_to_text(html: str) -> str:
    """Convert *html* to deterministic plaintext using stdlib only.

    Strips tags and collapses whitespace; renders ``<a href="u">t</a>`` as
    ``t (u)`` so the link URL is preserved; treats ``<br>`` and block tags
    (``<p>``, ``<div>``, headings, ``<li>``) as line breaks. Character
    references are unescaped. No external dependencies.

    Args:
        html: The HTML source to convert.

    Returns:
        A whitespace-normalized plaintext rendering.
    """
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()

    text = unescape(parser.get_text())
    # Collapse intra-line whitespace, trim each line, drop excess blank lines.
    lines = [_WS_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _NL_RE.sub("\n\n", text)
    return text.strip()
