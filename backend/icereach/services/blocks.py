"""Render a block document into client-safe, inline-styled, table-based email HTML.

Merge tags like ``{name}`` are emitted verbatim so the send-time renderer
(``services.merge.render``) fills them. Unknown block types are skipped, never
raised, so a malformed document still produces a sendable email.
"""

from __future__ import annotations

from html import escape

from .merge import html_to_text

_FONT = "Arial, Helvetica, sans-serif"
_TEXT_COLOR = "#333333"
_MAX_WIDTH = 600


def _align(block: dict) -> str:
    a = str(block.get("align", "left")).lower()
    return a if a in ("left", "center", "right") else "left"


def _heading(b: dict) -> str:
    level = b.get("level", 2)
    level = level if level in (1, 2, 3) else 2
    size = {1: 28, 2: 22, 3: 18}[level]
    return (
        f'<h{level} style="margin:0;font-family:{_FONT};font-size:{size}px;'
        f'line-height:1.3;color:{_TEXT_COLOR};text-align:{_align(b)};font-weight:700;">'
        f'{escape(str(b.get("text", "")))}</h{level}>'
    )


def _text(b: dict) -> str:
    # The text block intentionally allows inline HTML authored in the builder.
    inner = b.get("html", b.get("text", ""))
    return (
        f'<div style="font-family:{_FONT};font-size:16px;line-height:1.6;'
        f'color:{_TEXT_COLOR};text-align:{_align(b)};">{inner}</div>'
    )


def _button(b: dict) -> str:
    bg = b.get("bg", "#2563eb")
    color = b.get("color", "#ffffff")
    url = escape(str(b.get("url", "#")), quote=True)
    text = escape(str(b.get("text", "Click here")))
    return (
        f'<div style="text-align:{_align(b)};">'
        f'<a href="{url}" style="display:inline-block;padding:12px 24px;background:{bg};'
        f'color:{color};text-decoration:none;border-radius:6px;font-family:{_FONT};'
        f'font-size:16px;font-weight:600;">{text}</a></div>'
    )


def _image(b: dict) -> str:
    src = escape(str(b.get("src", "")), quote=True)
    alt = escape(str(b.get("alt", "")), quote=True)
    width = b.get("width")
    width_attr = f' width="{int(width)}"' if isinstance(width, (int, float)) else ""
    img = (
        f'<img src="{src}" alt="{alt}"{width_attr} '
        f'style="display:block;max-width:100%;height:auto;border:0;margin:0 auto;" />'
    )
    if b.get("href"):
        href = escape(str(b["href"]), quote=True)
        img = f'<a href="{href}">{img}</a>'
    return f'<div style="text-align:{_align(b)};">{img}</div>'


def _divider(b: dict) -> str:
    return '<div style="border-top:1px solid #e5e7eb;font-size:0;line-height:0;">&nbsp;</div>'


def _spacer(b: dict) -> str:
    height = b.get("height", 24)
    height = int(height) if isinstance(height, (int, float)) else 24
    return f'<div style="height:{height}px;line-height:{height}px;font-size:0;">&nbsp;</div>'


def _columns(b: dict) -> str:
    cols = b.get("columns") or []
    cols = cols[:2] if len(cols) >= 2 else (cols + [[]])[:2]
    width_pct = 50
    cells = ""
    for col in cols:
        inner = "".join(_block_inner(sub) + '<div style="height:8px;"></div>' for sub in col if isinstance(sub, dict))
        cells += (
            f'<td valign="top" width="{width_pct}%" '
            f'style="width:{width_pct}%;padding:0 8px;vertical-align:top;">{inner}</td>'
        )
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{cells}</tr></table>'


_RENDERERS = {
    "heading": _heading,
    "text": _text,
    "button": _button,
    "image": _image,
    "divider": _divider,
    "spacer": _spacer,
    "columns": _columns,
}


def _block_inner(block: dict) -> str:
    fn = _RENDERERS.get(str(block.get("type")))
    return fn(block) if fn else ""


def render_blocks(blocks: list[dict], *, preheader: str = "") -> str:
    """Render a block list into a full email-safe HTML document."""
    rows = ""
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        inner = _block_inner(block)
        if inner:
            rows += f'<tr><td style="padding:8px 0;">{inner}</td></tr>'

    preheader_html = (
        f'<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(preheader)}</div>'
        if preheader else ""
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1"></head>'
        '<body style="margin:0;padding:0;background:#f3f4f6;">'
        f"{preheader_html}"
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;">'
        '<tr><td align="center" style="padding:24px 12px;">'
        f'<table role="presentation" width="{_MAX_WIDTH}" cellpadding="0" cellspacing="0" '
        f'style="max-width:{_MAX_WIDTH}px;width:100%;background:#ffffff;border-radius:8px;'
        'padding:24px;font-family:' + _FONT + ';">'
        f"{rows}"
        "</table></td></tr></table></body></html>"
    )


def blocks_to_text(blocks: list[dict]) -> str:
    """Plaintext alternative derived from the rendered HTML."""
    return html_to_text(render_blocks(blocks))
