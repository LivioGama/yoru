"""TSU-54 — server-side render of a self-contained shareable receipt PNG.

The PIVOT (owner steer, 2026-06-27): sharing is **local image export**, not
public hosting. A self-hoster exports a PNG of their OWN session and shares the
image itself — nothing leaves their instance but the picture they choose to
send. So this renders a 1200×630 card with EVERYTHING baked in (grade + the
Throughput/Reliability/Safety subscores + tool/file/flag counts + title) and a
plain ``yoru.sh`` wordmark — deliberately NO ``/s/<id>`` URL (there is no hosted
viewer to point at).

Design mirrors the marketing OG card (marketing/api/og-image.tsx) 1:1 — same
PAPER/INK/ACCENT palette + Inter — but is drawn with Pillow so it runs on the
Python-only self-hosted backend with zero JS/Node runtime (satori is JS; a Node
sidecar would violate yoru's self-host-minimal ethos). Output is consistent and
server-rendered, no client drift.

Caller MUST scrub any baked text (title) via ``_scrub_public_text`` before
handing it here — TSU-44 redaction applies to whatever lands in the pixels.
"""
from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Card geometry (matches the OG card: 1200×630, 16px accent rule, 72px pad).
_W, _H = 1200, 630
_PAD = 72
_RULE = 16

# Palette — identical to marketing/api/og-image.tsx.
_PAPER = (13, 13, 15)      # #0d0d0f
_INK = (237, 237, 240)     # #ededf0
_MUTED = (160, 160, 170)   # #a0a0aa
_ACCENT = (245, 158, 11)   # #f59e0b

# Inter, vendored as .woff (SIL OFL) — FreeType loads woff directly.
_FONT_DIR = Path(__file__).resolve().parents[3] / "assets" / "fonts"
_REGULAR = _FONT_DIR / "inter-400-normal.woff"
_BOLD = _FONT_DIR / "inter-700-normal.woff"


@lru_cache(maxsize=16)
def _font(bold: bool, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(_BOLD if bold else _REGULAR), size)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> float:
    return draw.textlength(text, font=font)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
          max_w: int, max_lines: int) -> list[str]:
    """Greedy word-wrap to ``max_lines``; last line ellipsised if it overflows."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if _text_width(draw, trial, font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
            if len(lines) == max_lines:
                break
    if len(lines) < max_lines and cur:
        lines.append(cur)
    # Ellipsise the final line if the text didn't fully fit.
    if lines and (len(lines) == max_lines):
        consumed = " ".join(lines)
        if consumed.strip() != text.strip():
            last = lines[-1]
            while last and _text_width(draw, last + "…", font) > max_w:
                last = last[:-1].rstrip()
            lines[-1] = (last + "…") if last else "…"
    return lines or ["—"]


def _plural(n: int, unit: str) -> str:
    return f"{n} {unit}{'' if n == 1 else 's'}"


def render_receipt_png(
    *,
    title: str,
    grade: str | None,
    overall: int | None,
    throughput: int | None,
    reliability: int | None,
    safety: int | None,
    tools_count: int,
    files_count: int,
    flag_count: int,
) -> bytes:
    """Render the self-contained receipt card → PNG bytes.

    ``title`` must already be redaction-scrubbed by the caller. All score args
    are optional (a session may be unscored); the card degrades gracefully.
    """
    img = Image.new("RGB", (_W, _H), _PAPER)
    draw = ImageDraw.Draw(img)

    # Accent left rule.
    draw.rectangle([0, 0, _RULE, _H], fill=_ACCENT)

    x0 = _RULE + _PAD

    # Header: "yoru.sh · session trail".
    f_head = _font(True, 34)
    f_head_m = _font(False, 34)
    draw.text((x0, _PAD), "yoru.sh", font=f_head, fill=_ACCENT)
    yoru_w = _text_width(draw, "yoru.sh", f_head)
    draw.text((x0 + yoru_w + 18, _PAD), "· session trail", font=f_head_m, fill=_MUTED)

    # Grade medallion (left) — 200×200 rounded square, accent border.
    box_top = 196
    box = 200
    if grade:
        draw.rounded_rectangle(
            [x0, box_top, x0 + box, box_top + box], radius=24,
            outline=_ACCENT, width=6,
        )
        f_grade = _font(True, 130)
        gw = _text_width(draw, grade, f_grade)
        gbbox = f_grade.getbbox(grade)
        gh = gbbox[3] - gbbox[1]
        draw.text(
            (x0 + (box - gw) / 2, box_top + (box - gh) / 2 - gbbox[1]),
            grade, font=f_grade, fill=_ACCENT,
        )
        text_x = x0 + box + 56
    else:
        text_x = x0

    text_w = _W - text_x - _PAD

    # Title (up to 2 lines, 56px bold).
    f_title = _font(True, 56)
    title_lines = _wrap(draw, title or "Agent session trail", f_title, text_w, 2)
    ty = box_top
    for ln in title_lines:
        draw.text((text_x, ty), ln, font=f_title, fill=_INK)
        ty += 70

    # Subscores line: Throughput / Reliability / Safety (only if scored).
    f_sub = _font(False, 36)
    ty += 14
    sub_parts = []
    if throughput is not None:
        sub_parts.append(("Throughput ", str(throughput)))
    if reliability is not None:
        sub_parts.append(("  Reliability ", str(reliability)))
    if safety is not None:
        sub_parts.append(("  Safety ", str(safety)))
    if sub_parts:
        cx = text_x
        for label, val in sub_parts:
            draw.text((cx, ty), label, font=f_sub, fill=_MUTED)
            cx += _text_width(draw, label, f_sub)
            draw.text((cx, ty), val, font=_font(True, 36), fill=_INK)
            cx += _text_width(draw, val, _font(True, 36))
        ty += 56

    # Counts line: tool calls · files · red flags. Flag count flips to accent
    # when non-zero (the "confession" angle); a clean run stays muted ink.
    counts = "  ·  ".join([
        _plural(tools_count, "tool call"),
        _plural(files_count, "file"),
        _plural(flag_count, "red flag"),
    ])
    draw.text((text_x, ty), counts, font=_font(False, 36),
              fill=_ACCENT if flag_count else _MUTED)

    # Watermark — brand wordmark ONLY. No /s/<id> URL (pivot: share = the PNG,
    # there is no hosted viewer).
    f_wm = _font(True, 28)
    draw.text((x0, _H - _PAD - 28), "yoru.sh", font=f_wm, fill=_MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
