"""TSU-55 — server-side render of a shareable session-replay GIF.

The share-pivot artifact for the replay: an animated GIF the owner exports from
their OWN session and shares (the image, not a hosted viewer). Approach A
(cto-confirmed): render server-side with Pillow — which encodes animated GIF
NATIVELY (zero video deps, no ffmpeg) — so the **single** TSU-44 redaction
scrub (`_scrub_public_text`) is reused, never duplicated in client JS. One
scrub > zero video deps.

Each frame is one EVENT step (event-indexed, so the idle gaps of an overnight
run collapse — an hours-long session steps in seconds). Bounded for server CPU:
≤``MAX_FRAMES`` steps (flagged events always kept; the rest evenly sampled),
800×420 canvas. The final frame is the grade payoff (mirrors the receipt card).

Reuses receipt_card's palette + fonts so the GIF and the PNG look like one
family. Caller MUST pre-scrub every per-frame label (TSU-44) before passing it.
"""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

from .receipt_card import (
    _ACCENT,
    _INK,
    _MUTED,
    _PAPER,
    _font,
    _text_width,
    _wrap,
)

_W, _H = 800, 420
_PAD = 56
_RULE = 12

# Server-CPU bound: never encode more than this many frames. More events ->
# evenly downsample (flagged events are always retained — they carry the story).
MAX_FRAMES = 40

# Per-step display ms; the final grade frame holds longer so the payoff lands.
_STEP_MS = 700
_FINAL_MS = 2200

# Human label per event kind (compact — the GIF is glanceable, not a log).
_KIND_LABEL = {
    "tool_use": "tool",
    "file_change": "file",
    "session_start": "start",
    "session_end": "end",
    "error": "error",
    "message": "msg",
}


def _select_steps(events: list[dict]) -> list[dict]:
    """Cap to MAX_FRAMES: keep every flagged event, evenly sample the rest."""
    if len(events) <= MAX_FRAMES:
        return events
    flagged = [e for e in events if e.get("flagged")]
    budget = max(0, MAX_FRAMES - len(flagged))
    rest = [e for e in events if not e.get("flagged")]
    if budget and rest:
        stride = len(rest) / budget
        sampled = [rest[int(i * stride)] for i in range(budget)]
    else:
        sampled = []
    # Keep original chronological order (events carry an "i" index).
    chosen = {id(e) for e in flagged} | {id(e) for e in sampled}
    return [e for e in events if id(e) in chosen][:MAX_FRAMES]


def _base_frame() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (_W, _H), _PAPER)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, _RULE, _H], fill=_ACCENT)
    return img, draw


def _progress(draw: ImageDraw.ImageDraw, frac: float) -> None:
    """Bottom progress rail — accent fill up to `frac` (0..1)."""
    x0, x1 = _RULE + _PAD, _W - _PAD
    y = _H - _PAD
    draw.rectangle([x0, y, x1, y + 6], fill=(38, 38, 44))
    if frac > 0:
        draw.rectangle([x0, y, x0 + int((x1 - x0) * frac), y + 6], fill=_ACCENT)


def _step_frame(*, idx: int, total: int, kind: str, tool: str | None,
                label: str, flagged: bool) -> Image.Image:
    img, draw = _base_frame()
    x0 = _RULE + _PAD

    # Header: yoru.sh · replay   +   step k / N (right-aligned).
    draw.text((x0, _PAD), "yoru.sh", font=_font(True, 26), fill=_ACCENT)
    yw = _text_width(draw, "yoru.sh", _font(True, 26))
    draw.text((x0 + yw + 14, _PAD), "· replay", font=_font(False, 26), fill=_MUTED)
    step_txt = f"step {idx} / {total}"
    draw.text((_W - _PAD - _text_width(draw, step_txt, _font(False, 24)), _PAD),
              step_txt, font=_font(False, 24), fill=_MUTED)

    # Kind chip + tool name.
    chip = _KIND_LABEL.get(kind, kind)
    chip_col = _ACCENT if flagged else _MUTED
    draw.text((x0, 150), f"[{chip}]", font=_font(True, 30), fill=chip_col)
    cw = _text_width(draw, f"[{chip}]", _font(True, 30))
    if tool:
        draw.text((x0 + cw + 16, 150), tool, font=_font(True, 30), fill=_INK)

    # Label (scrubbed path / command / snippet) — up to 2 wrapped lines.
    lines = _wrap(draw, label or "", _font(False, 28), _W - x0 - _PAD, 2)
    ly = 200
    for ln in lines:
        draw.text((x0, ly), ln, font=_font(False, 28), fill=_INK if not flagged else _ACCENT)
        ly += 40

    _progress(draw, idx / total if total else 1.0)
    return img


def _final_frame(*, grade: str | None, throughput: int | None,
                 reliability: int | None, safety: int | None,
                 tools_count: int, files_count: int, flag_count: int) -> Image.Image:
    img, draw = _base_frame()
    x0 = _RULE + _PAD

    draw.text((x0, _PAD), "yoru.sh", font=_font(True, 26), fill=_ACCENT)
    yw = _text_width(draw, "yoru.sh", _font(True, 26))
    draw.text((x0 + yw + 14, _PAD), "· session graded", font=_font(False, 26), fill=_MUTED)

    # Grade medallion.
    if grade:
        box_t, box = 140, 150
        draw.rounded_rectangle([x0, box_t, x0 + box, box_t + box], radius=20,
                               outline=_ACCENT, width=5)
        gf = _font(True, 100)
        gw = _text_width(draw, grade, gf)
        gb = gf.getbbox(grade)
        draw.text((x0 + (box - gw) / 2, box_t + (box - (gb[3] - gb[1])) / 2 - gb[1]),
                  grade, font=gf, fill=_ACCENT)
        tx = x0 + box + 44
    else:
        tx = x0

    sub = []
    if throughput is not None:
        sub.append(f"Throughput {throughput}")
    if reliability is not None:
        sub.append(f"Reliability {reliability}")
    if safety is not None:
        sub.append(f"Safety {safety}")
    if sub:
        draw.text((tx, 160), "   ".join(sub), font=_font(False, 28), fill=_MUTED)

    def _plur(n, u):
        return f"{n} {u}{'' if n == 1 else 's'}"

    counts = "   ·   ".join([
        _plur(tools_count, "tool call"),
        _plur(files_count, "file"),
        _plur(flag_count, "red flag"),
    ])
    draw.text((tx, 210), counts, font=_font(False, 28),
              fill=_ACCENT if flag_count else _MUTED)

    draw.text((x0, _H - _PAD - 24), "yoru.sh", font=_font(True, 24), fill=_MUTED)
    return img


def render_replay_gif(
    *,
    events: list[dict],
    grade: str | None,
    throughput: int | None,
    reliability: int | None,
    safety: int | None,
    tools_count: int,
    files_count: int,
    flag_count: int,
) -> bytes:
    """Render the session replay as an animated GIF → bytes.

    ``events`` is chronological dicts: ``{kind, tool, label, flagged}`` with
    ``label`` ALREADY redaction-scrubbed by the caller. Returns a single-frame
    GIF (just the grade payoff) when there are no events.
    """
    steps = _select_steps(events)
    total = len(steps)
    frames = [
        _step_frame(
            idx=i + 1, total=total,
            kind=e.get("kind", ""), tool=e.get("tool"),
            label=e.get("label", ""), flagged=bool(e.get("flagged")),
        )
        for i, e in enumerate(steps)
    ]
    frames.append(_final_frame(
        grade=grade, throughput=throughput, reliability=reliability,
        safety=safety, tools_count=tools_count, files_count=files_count,
        flag_count=flag_count,
    ))
    durations = [_STEP_MS] * total + [_FINAL_MS]

    buf = io.BytesIO()
    frames[0].save(
        buf, format="GIF", save_all=True, append_images=frames[1:],
        duration=durations, loop=0, optimize=True, disposal=2,
    )
    return buf.getvalue()
