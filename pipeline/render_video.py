#!/usr/bin/env python3
"""Render a vertical YouTube Shorts video (1080x1920) from a shorts spec JSON.

    python -m pipeline.render_video shorts/2026-11-08-some-paper.json [--fast]

Outputs
  build/<stem>/<stem>.mp4               the video (not committed; uploaded on publish)
  assets/shorts/<stem>-thumb.jpg        hook frame (blog og:image, PR preview)
  assets/shorts/<stem>-sheet.jpg        contact sheet of every scene (PR preview)
  shorts/<stem>.md                      human-readable script with real timings
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .common import ASSETS_SHORTS_DIR, BUILD_DIR, FONTS_DIR, ROOT, SHORTS_DIR, http_get, load_config
from .tts import Word, synthesize

# ── look & feel ───────────────────────────────────────────────
TEXT = (240, 246, 252)
MUTED = (150, 160, 172)
ACCENT = (88, 166, 255)
HILITE = (255, 214, 64)
DARK = (13, 17, 23)
RED = (255, 48, 64)
MARGIN = 72
CAPTION_CY = 1335           # caption block centre (above the Shorts title/UI overlay)
CAPTION_MAX_W = 860
CONTENT_TOP = 270
CONTENT_BOTTOM = 1200

LEAD, GAP, TAIL = 0.30, 0.30, 1.20   # seconds of silence: start, between scenes, end
SAMPLE_RATE = 48000

PRETENDARD = {
    "medium": "Pretendard-Medium.otf",
    "semibold": "Pretendard-SemiBold.otf",
    "bold": "Pretendard-Bold.otf",
    "extrabold": "Pretendard-ExtraBold.otf",
    "black": "Pretendard-Black.otf",
}
PRETENDARD_URL = "https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/public/static/{}"
SYSTEM_FALLBACKS = [  # (path, ttc index for Korean)
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc", 1),
    ("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf", 0),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
]


# ── fonts ─────────────────────────────────────────────────────

def ensure_fonts() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    for name in PRETENDARD.values():
        path = FONTS_DIR / name
        if path.exists() and path.stat().st_size > 100_000:
            continue
        try:
            path.write_bytes(http_get(PRETENDARD_URL.format(name), timeout=60))
        except Exception as e:
            print(f"[warn] Pretendard 다운로드 실패({name}): {e} — 시스템 폰트로 대체", file=sys.stderr)


@lru_cache(maxsize=256)
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONTS_DIR / PRETENDARD[weight]
    if path.exists():
        return ImageFont.truetype(str(path), size)
    for fp, idx in SYSTEM_FALLBACKS:
        if Path(fp).exists():
            return ImageFont.truetype(fp, size, index=idx)
    raise RuntimeError("한글 폰트를 찾을 수 없습니다. assets/fonts/ 에 Pretendard를 넣거나 fonts-noto-cjk를 설치하세요.")


# ── rich text: **강조** + wrapping ─────────────────────────────

Token = tuple[str, bool]  # (text incl. trailing space, highlighted)


def tokenize(text: str, auto_hl_numbers: bool = False) -> list[list[Token]]:
    """Split into paragraphs (explicit newlines) of word tokens with highlight flags."""
    paras: list[list[Token]] = []
    for para in text.split("\n"):
        toks: list[Token] = []
        for i, seg in enumerate(re.split(r"\*\*", para)):
            hl = i % 2 == 1
            if seg[:1].isspace() and toks and not toks[-1][0].endswith(" "):
                toks[-1] = (toks[-1][0] + " ", toks[-1][1])  # keep the space after a **highlight**
            for w in re.findall(r"\S+\s*", seg):
                toks.append((w, hl or (auto_hl_numbers and bool(re.search(r"\d", w)))))
        paras.append(toks)
    return paras


def wrap(text: str, fnt: ImageFont.FreeTypeFont, max_w: int, auto_hl_numbers: bool = False) -> list[list[Token]]:
    lines: list[list[Token]] = []
    for toks in tokenize(text, auto_hl_numbers):
        line: list[Token] = []
        width = 0.0
        for w, hl in toks:
            ww = fnt.getlength(w.rstrip())
            if line and width + ww > max_w:
                lines.append(line)
                line, width = [], 0.0
            if ww > max_w:  # a single over-long word → break by characters
                buf = ""
                for ch in w:
                    if fnt.getlength(buf + ch) > max_w and buf:
                        lines.append([(buf, hl)])
                        buf = ""
                    buf += ch
                line, width = [(buf, hl)], fnt.getlength(buf)
                continue
            line.append((w, hl))
            width += fnt.getlength(w)
        lines.append(line)
    return [ln for ln in lines if ln] or [[("", False)]]


def line_width(line: list[Token], fnt: ImageFont.FreeTypeFont) -> float:
    s = "".join(t for t, _ in line).rstrip()
    return fnt.getlength(s)


def fit(text: str, weight: str, max_size: int, min_size: int, max_w: int, max_lines: int,
        auto_hl_numbers: bool = False) -> tuple[ImageFont.FreeTypeFont, list[list[Token]]]:
    size = max_size
    while True:
        fnt = font(weight, size)
        lines = wrap(text, fnt, max_w, auto_hl_numbers)
        if (len(lines) <= max_lines and all(line_width(ln, fnt) <= max_w for ln in lines)) or size <= min_size:
            return fnt, lines
        size -= 4


class Layer:
    """Full-frame RGBA layer with correctly blended drawing helpers."""

    def __init__(self, w: int, h: int):
        self.im = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    def _over(self, overlay: Image.Image) -> None:
        self.im = Image.alpha_composite(self.im, overlay)

    def rect(self, box, radius: int, fill, outline=None, width: int = 0) -> None:
        ov = Image.new("RGBA", self.im.size, (0, 0, 0, 0))
        ImageDraw.Draw(ov).rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
        self._over(ov)

    def ellipse(self, box, fill) -> None:
        ov = Image.new("RGBA", self.im.size, (0, 0, 0, 0))
        ImageDraw.Draw(ov).ellipse(box, fill=fill)
        self._over(ov)

    def polygon(self, pts, fill) -> None:
        ov = Image.new("RGBA", self.im.size, (0, 0, 0, 0))
        ImageDraw.Draw(ov).polygon(pts, fill=fill)
        self._over(ov)

    def text(self, lines: list[list[Token]], fnt: ImageFont.FreeTypeFont, x: float, y: float, *,
             align: str = "center", color=TEXT, hl_color=HILITE, line_gap: float = 1.22,
             stroke: int = 0, stroke_color=(0, 0, 0), shadow: bool = False) -> float:
        """Draw wrapped rich text; x is the centre (align=center) or left edge. Returns block height."""
        size = fnt.size
        lh = size * line_gap
        masks: dict[tuple, Image.Image] = {}

        def mask(key) -> ImageDraw.ImageDraw:
            if key not in masks:
                masks[key] = Image.new("L", self.im.size, 0)
            return ImageDraw.Draw(masks[key])

        for i, line in enumerate(lines):
            lw = line_width(line, fnt)
            cx = x - lw / 2 if align == "center" else x
            cy = y + i * lh
            for t, hl in line:
                if stroke:
                    mask(("stroke",)).text((cx, cy), t, font=fnt, fill=255, stroke_width=stroke)
                if shadow:
                    mask(("shadow",)).text((cx + 4, cy + 6), t, font=fnt, fill=255)
                mask(("fill", hl)).text((cx, cy), t, font=fnt, fill=255)
                cx += fnt.getlength(t)

        def paint(key, rgb, alpha=255):
            if key in masks:
                m = masks[key]
                if key == ("shadow",):
                    m = m.filter(ImageFilter.GaussianBlur(6))
                if alpha != 255:
                    m = m.point(lambda a: a * alpha // 255)
                solid = Image.new("RGBA", self.im.size, tuple(rgb) + (0,))
                solid.putalpha(m)
                self._over(solid)

        paint(("shadow",), (0, 0, 0), 150)
        paint(("stroke",), stroke_color)
        paint(("fill", False), color)
        paint(("fill", True), hl_color)
        return len(lines) * lh

    def paste(self, img: Image.Image, xy: tuple[int, int]) -> None:
        ov = Image.new("RGBA", self.im.size, (0, 0, 0, 0))
        ov.paste(img, xy, img if img.mode == "RGBA" else None)
        self._over(ov)


def block_height(lines, fnt, line_gap=1.22) -> float:
    return len(lines) * fnt.size * line_gap


# ── backgrounds & chrome ──────────────────────────────────────

def make_background(w: int, h: int, pad: int = 120) -> Image.Image:
    W2, H2 = w + pad, h + pad
    sw, sh = W2 // 4, H2 // 4
    small = Image.new("RGB", (sw, sh))
    px = small.load()
    for yy in range(sh):
        t = yy / sh
        c = tuple(int(a + (b - a) * t) for a, b in zip((14, 19, 32), (6, 8, 18)))
        for xx in range(sw):
            px[xx, yy] = c
    glow = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    for (cx, cy, r, col) in [(0.85, 0.12, 0.42, (88, 166, 255, 95)), (0.05, 0.55, 0.40, (163, 113, 247, 70)),
                             (0.75, 0.92, 0.38, (45, 212, 191, 55))]:
        d.ellipse([(cx - r) * sw, (cy - r * 0.6) * sh, (cx + r) * sw, (cy + r * 0.6) * sh], fill=col)
    glow = glow.filter(ImageFilter.GaussianBlur(sw * 0.09))
    small = Image.alpha_composite(small.convert("RGBA"), glow).convert("RGB")
    bg = small.resize((W2, H2), Image.BICUBIC)
    grid = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    g = ImageDraw.Draw(grid)
    for gx in range(0, W2, 90):
        g.line([(gx, 0), (gx, H2)], fill=(255, 255, 255, 9), width=1)
    for gy in range(0, H2, 90):
        g.line([(0, gy), (W2, gy)], fill=(255, 255, 255, 9), width=1)
    return Image.alpha_composite(bg.convert("RGBA"), grid).convert("RGB")


def make_chrome(spec: dict[str, Any], w: int, h: int, channel: str) -> Image.Image:
    L = Layer(w, h)
    # brand pill (top-left)
    f = font("semibold", 36)
    tw = f.getlength(channel)
    L.rect((MARGIN, 64, MARGIN + 74 + tw, 64 + 66), 33, (255, 255, 255, 26))
    L.ellipse((MARGIN + 24, 64 + 25, MARGIN + 40, 64 + 41), ACCENT + (255,))
    L.text([[(channel, False)]], f, MARGIN + 52, 64 + 11, align="left")
    # venue badge (top-right)
    paper = spec["paper"]
    v = paper.get("venue")
    badge = (v["venue"] + (f" {v['honor']}" if v.get("honor") else "")) if v else "HOT PAPER"
    fb = font("bold", 34)
    bw = fb.getlength(badge)
    L.rect((w - MARGIN - bw - 44, 64, w - MARGIN, 64 + 66), 33, ACCENT + (255,) if v else (255, 255, 255, 40))
    L.text([[(badge, False)]], fb, w - MARGIN - bw - 22, 64 + 13, align="left", color=DARK if v else TEXT)
    # reference line
    ref = f"arXiv {paper['arxiv_id']}" + (f"  ·  {paper['organization']}" if paper.get("organization") else "")
    fr = font("medium", 30)
    while fr.getlength(ref) > w - 2 * MARGIN and len(ref) > 10:
        ref = ref[:-2]
    L.text([[(ref, False)]], fr, MARGIN + 4, 158, align="left", color=MUTED)
    # bottom fade so the Shorts UI stays readable
    fade = Image.new("L", (1, 480))
    for i in range(480):
        fade.putpixel((0, i), int(185 * (i / 480) ** 1.6))
    shade = Image.new("RGBA", (w, 480), (0, 0, 0, 255))
    shade.putalpha(fade.resize((w, 480)))
    L.paste(shade, (0, h - 480))
    return L.im


# ── scene layouts ─────────────────────────────────────────────

def _headline_top(L: Layer, s: dict, w: int, size: int = 88) -> float:
    fnt, lines = fit(s["headline"], "extrabold", size, 60, w - 2 * MARGIN, 3)
    L.text(lines, fnt, w / 2, CONTENT_TOP + 20, shadow=True)
    return CONTENT_TOP + 20 + block_height(lines, fnt)


def _headline(s: dict, w: int, size: int = 88):
    fnt, lines = fit(s["headline"], "extrabold", size, 60, w - 2 * MARGIN, 3)
    return fnt, lines, block_height(lines, fnt)


def _centered_top(total_h: float) -> float:
    """Top y that vertically centres a block in the content zone (never above CONTENT_TOP)."""
    return max(CONTENT_TOP + 20, (CONTENT_TOP + CONTENT_BOTTOM) / 2 - total_h / 2 - 30)


def render_scene(s: dict[str, Any], spec: dict[str, Any], w: int, h: int, paper_img: Image.Image | None,
                 stat_progress: float = 1.0) -> Image.Image:
    L = Layer(w, h)
    lay = s["layout"]
    if lay == "hook":
        fnt, lines = fit(s["headline"], "black", 112, 72, w - 2 * MARGIN, 3)
        hh = block_height(lines, fnt)
        sub_f, sub_lines = fit(s.get("subtext") or "", "semibold", 48, 36, w - 2 * MARGIN - 40, 2) \
            if s.get("subtext") else (None, [])
        sh = block_height(sub_lines, sub_f) + 70 if sub_f else 0
        top = (CONTENT_TOP + CONTENT_BOTTOM) / 2 - (hh + 60 + sh) / 2
        L.text(lines, fnt, w / 2, top, shadow=True)
        bar_y = top + hh + 30
        L.rect((w / 2 - 70, bar_y, w / 2 + 70, bar_y + 10), 5, ACCENT + (255,))
        if sub_f:
            L.text(sub_lines, sub_f, w / 2, bar_y + 50, color=MUTED)

    elif lay == "paper":
        y = _headline_top(L, s, w, 80) + 40
        max_h = CONTENT_BOTTOM - y - (70 if s.get("subtext") else 10)
        if paper_img is not None:
            card = paper_img.copy()
            scale = min(820 / card.width, max_h / card.height)
            card = card.resize((int(card.width * scale), int(card.height * scale)), Image.LANCZOS)
            framed = Image.new("RGBA", (card.width + 24, card.height + 24), (255, 255, 255, 255))
            framed.paste(card, (12, 12))
            rmask = Image.new("L", framed.size, 0)
            ImageDraw.Draw(rmask).rounded_rectangle((0, 0, *framed.size), radius=18, fill=255)
            framed.putalpha(rmask)
            rot = framed.rotate(2.2, resample=Image.BICUBIC, expand=True)
            pad = 60
            sh_alpha = Image.new("L", (rot.width + 2 * pad, rot.height + 2 * pad), 0)
            sh_alpha.paste(rot.getchannel("A").point(lambda a: a * 150 // 255), (pad, pad))
            shadow = Image.new("RGBA", sh_alpha.size, (0, 0, 0, 0))
            shadow.putalpha(sh_alpha.filter(ImageFilter.GaussianBlur(18)))
            x0 = int(w / 2 - rot.width / 2)
            L.paste(shadow, (x0 + 10 - pad, int(y) + 22 - pad))
            L.paste(rot, (x0, int(y)))
            y += rot.height
        else:  # no PDF render available → title card
            tf, tl = fit(spec["paper"]["title"], "bold", 58, 40, w - 2 * MARGIN - 80, 5)
            bh = block_height(tl, tf) + 100
            L.rect((MARGIN, y, w - MARGIN, y + bh), 28, (255, 255, 255, 236))
            L.text(tl, tf, w / 2, y + 50, color=DARK)
            y += bh
        if s.get("subtext"):
            sf, sl = fit(s["subtext"], "semibold", 44, 34, w - 2 * MARGIN, 1)
            L.text(sl, sf, w / 2, y + 22, color=MUTED)

    elif lay == "bullets":
        hf, hl_lines, hh = _headline(s, w)
        bullets = [b for b in s.get("bullets", []) if b.strip()][:3]
        bf = font("semibold", 54)
        cards = []
        for b in bullets:
            lines = wrap(b, bf, w - 2 * MARGIN - 170)
            th = block_height(lines, bf, 1.25)
            cards.append((lines, th, max(124, th + 70)))
        total = hh + 70 + sum(c[2] for c in cards) + 30 * max(0, len(cards) - 1)
        y = _centered_top(total)
        L.text(hl_lines, hf, w / 2, y, shadow=True)
        y += hh + 70
        for i, (lines, th, ch) in enumerate(cards):
            L.rect((MARGIN, y, w - MARGIN, y + ch), 26, (255, 255, 255, 20), outline=(255, 255, 255, 38), width=2)
            cy = y + ch / 2
            L.ellipse((MARGIN + 34, cy - 34, MARGIN + 102, cy + 34), ACCENT + (255,))
            nf = font("black", 40)
            L.text([[(str(i + 1), False)]], nf, MARGIN + 68, cy - 26, color=DARK)
            L.text(lines, bf, MARGIN + 132, cy - th / 2 + 4, align="left", line_gap=1.25)
            y += ch + 30

    elif lay == "stat":
        hf, hl_lines, hh = _headline(s, w)
        value = s.get("stat_value", "")
        vf, _ = fit(value, "black", 260, 120, w - 2 * MARGIN, 1)  # size fixed by the final value
        lf, ll = fit(s["stat_label"], "bold", 58, 40, w - 2 * MARGIN, 2) if s.get("stat_label") else (None, [])
        sf, sl = fit(s["subtext"], "semibold", 42, 32, w - 2 * MARGIN, 2) if s.get("subtext") else (None, [])
        total = hh + 50 + vf.size * 1.15 + (10 + block_height(ll, lf) if lf else 0) + (30 + block_height(sl, sf) if sf else 0)
        y = _centered_top(total)
        L.text(hl_lines, hf, w / 2, y, shadow=True)
        y += hh + 50
        L.text([[(animate_number(value, stat_progress), False)]], vf, w / 2, y, color=HILITE, shadow=True, line_gap=1.1)
        y += vf.size * 1.15
        if lf:
            L.text(ll, lf, w / 2, y + 10)
            y += 10 + block_height(ll, lf)
        if sf:
            L.text(sl, sf, w / 2, y + 30, color=MUTED)

    elif lay == "compare":
        hf, hl_lines, hh = _headline(s, w)
        cw, chh, gap = 410, 430, w - 2 * MARGIN - 2 * 410
        sf, sl = fit(s["subtext"], "semibold", 42, 32, w - 2 * MARGIN, 2) if s.get("subtext") else (None, [])
        y = _centered_top(hh + 70 + chh + (46 + block_height(sl, sf) if sf else 0))
        L.text(hl_lines, hf, w / 2, y, shadow=True)
        y += hh + 70
        boxes = [(MARGIN, s.get("left_label", ""), s.get("left_value", ""), False),
                 (MARGIN + cw + gap, s.get("right_label", ""), s.get("right_value", ""), True)]
        for x0, label, value, hot in boxes:
            L.rect((x0, y, x0 + cw, y + chh), 30,
                   (88, 166, 255, 46) if hot else (255, 255, 255, 18),
                   outline=ACCENT + (255,) if hot else (255, 255, 255, 40), width=4 if hot else 2)
            lf, ll = fit(label, "bold", 44, 30, cw - 50, 2)
            L.text(ll, lf, x0 + cw / 2, y + 44, color=ACCENT if hot else MUTED)
            vf, vl = fit(value, "black", 130, 60, cw - 40, 2)
            vh = block_height(vl, vf, 1.1)
            L.text(vl, vf, x0 + cw / 2, y + chh / 2 - vh / 2 + 40, color=HILITE if hot else TEXT, line_gap=1.1)
        ax = MARGIN + cw + gap / 2
        ay = y + chh / 2
        L.polygon([(ax - 22, ay - 34), (ax + 26, ay), (ax - 22, ay + 34)], ACCENT + (255,))
        if sf:
            L.text(sl, sf, w / 2, y + chh + 46, color=MUTED)

    elif lay == "cta":
        fnt, lines = fit(s["headline"], "extrabold", 92, 60, w - 2 * MARGIN, 3)
        top = CONTENT_TOP + 150
        L.text(lines, fnt, w / 2, top, shadow=True)
        y = top + block_height(lines, fnt) + 80
        url = spec["blog_url"].replace("https://", "").rstrip("/")
        url = re.sub(r"/posts/.*$", "", url)
        lf = font("semibold", 44)
        uf = font("medium", 34)
        bw = max(lf.getlength("블로그에서 전체 리뷰 보기"), uf.getlength(url)) + 90
        L.rect((w / 2 - bw / 2, y, w / 2 + bw / 2, y + 160), 34, (255, 255, 255, 22), outline=(255, 255, 255, 50), width=2)
        L.text([[("블로그에서 전체 리뷰 보기", False)]], lf, w / 2, y + 30)
        L.text([[(url, False)]], uf, w / 2, y + 96, color=ACCENT)
        y += 160 + 60
        L.rect((w / 2 - 230, y, w / 2 + 230, y + 116), 58, RED + (255,))
        L.text([[("구독하고 다음 논문 받기", False)]], font("bold", 44), w / 2, y + 32)
        if s.get("subtext"):
            sf, sl = fit(s["subtext"], "semibold", 40, 32, w - 2 * MARGIN, 2)
            L.text(sl, sf, w / 2, y + 170, color=MUTED)
    return L.im


def animate_number(value: str, p: float) -> str:
    """'-39%' at p=0.5 → '-20%'. Non-numeric values are returned unchanged."""
    m = re.search(r"\d+(?:[.,]\d+)?", value)
    if not m or p >= 1:
        return value
    num_s = m.group(0).replace(",", "")
    decimals = len(num_s.split(".")[1]) if "." in num_s else 0
    eased = 1 - (1 - p) ** 3
    cur = float(num_s) * eased
    txt = f"{cur:,.{decimals}f}" if "," in m.group(0) else f"{cur:.{decimals}f}"
    return value[: m.start()] + txt + value[m.end():]


# ── captions ─────────────────────────────────────────────────

def chunk_caption(text: str, max_chars: int = 15) -> list[str]:
    clauses = [c.strip() for c in re.split(r"(?<=[.?!,])\s+", text.strip()) if c.strip()]
    chunks: list[str] = []
    for clause in clauses:
        words, cur = clause.split(), ""
        for wd in words:
            cand = f"{cur} {wd}".strip()
            if cur and len(cand) > max_chars:
                chunks.append(cur)
                cur = wd
            else:
                cur = cand
        if cur:
            chunks.append(cur)
    # merge a dangling 1-word tail into the previous chunk
    out: list[str] = []
    for c in chunks:
        if out and len(c) <= 3 and len(out[-1]) + len(c) + 1 <= max_chars + 4:
            out[-1] = f"{out[-1]} {c}"
        else:
            out.append(c)
    return [re.sub(r"[.,]$", "", c) for c in out]


def _norm(s: str) -> str:
    return re.sub(r"[^\w]", "", s)


def caption_times(chunks: list[str], narration: str, words: list[Word] | None, dur: float) -> list[float]:
    """Start time (relative to the scene's audio) of each caption chunk."""
    total_chars = len(_norm(narration)) or 1
    starts_chars, acc = [], 0
    for c in chunks:
        starts_chars.append(acc)
        acc += len(_norm(c))
    if words:
        # piecewise-linear map from character position → time, built from word boundaries
        pts, pos = [(0, words[0][0])], 0
        for s, e, t in words:
            n = len(_norm(t))
            pts.append((pos, s))
            pos += n
            pts.append((pos, e))
        if abs(pos - total_chars) / total_chars < 0.25:
            def at(c: float) -> float:
                for (c0, t0), (c1, t1) in zip(pts, pts[1:]):
                    if c0 <= c <= c1:
                        return t0 if c1 == c0 else t0 + (t1 - t0) * (c - c0) / (c1 - c0)
                return pts[-1][1]
            return [max(0.0, at(c) - 0.05) for c in starts_chars]
    return [dur * c / total_chars for c in starts_chars]


def render_caption(text: str, w: int) -> tuple[Image.Image, tuple[int, int]]:
    fnt, lines = fit(text, "bold", 64, 48, CAPTION_MAX_W, 2, auto_hl_numbers=True)
    L = Layer(w, 400)
    L.text(lines, fnt, w / 2 - 20, 40, stroke=9, stroke_color=(0, 0, 0), line_gap=1.18)
    im = L.im
    bbox = im.getbbox() or (0, 0, 1, 1)
    crop = im.crop(bbox)
    block_h = block_height(lines, fnt, 1.18)
    y0 = int(CAPTION_CY - block_h / 2 - 40 + bbox[1])
    return crop, (bbox[0], y0)


# ── audio ────────────────────────────────────────────────────

def decode_pcm(path: Path, tempo: float = 1.0) -> bytes:
    af = [f"atempo={tempo:.4f}"] if abs(tempo - 1.0) > 1e-3 else []
    cmd = ["ffmpeg", "-loglevel", "error", "-i", str(path)]
    if af:
        cmd += ["-af", ",".join(af)]
    cmd += ["-ar", str(SAMPLE_RATE), "-ac", "1", "-f", "s16le", "-"]
    return subprocess.run(cmd, check=True, capture_output=True).stdout


def silence(sec: float) -> bytes:
    return b"\x00\x00" * int(round(sec * SAMPLE_RATE))


# ── main render ──────────────────────────────────────────────

def load_paper_image(spec: dict[str, Any], work: Path) -> Image.Image | None:
    from .paper import download_pdf, render_first_page

    try:
        pdf = download_pdf(spec["paper"], ROOT / "build" / spec["paper"]["arxiv_id"])
        png = render_first_page(pdf, work / "page1.png")
        if not png:
            return None
        page = Image.open(png).convert("RGB")
        return page.crop((0, 0, page.width, int(page.height * 0.52)))
    except Exception as e:
        print(f"[warn] 논문 첫 페이지 렌더 실패: {e}", file=sys.stderr)
        return None


def render(spec_path: Path, fast: bool = False) -> dict[str, Any]:
    cfg = load_config()
    vcfg = cfg["video"]
    W, H, FPS = vcfg["width"], vcfg["height"], vcfg["fps"]
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    stem = spec["stem"]
    scenes = spec["shorts"]["scenes"]
    work = BUILD_DIR / stem
    (work / "audio").mkdir(parents=True, exist_ok=True)
    ensure_fonts()

    # 1) narration audio per scene
    print(f"[render] TTS ({vcfg['tts']}) for {len(scenes)} scenes...", file=sys.stderr)
    raw: list[tuple[Path, list[Word] | None]] = []
    for i, s in enumerate(scenes):
        raw.append(synthesize(s["narration"], work / "audio" / f"{i:02d}.mp3", vcfg))
    pcm = [decode_pcm(p) for p, _ in raw]
    speech = sum(len(b) / 2 / SAMPLE_RATE for b in pcm)
    fixed = LEAD + GAP * (len(scenes) - 1) + TAIL
    tempo = 1.0
    if speech + fixed > vcfg["max_seconds"]:
        tempo = min(1.25, speech / max(1.0, vcfg["max_seconds"] - fixed))
        print(f"[render] {speech + fixed:.1f}s > {vcfg['max_seconds']}s → 음성 {tempo:.2f}배속", file=sys.stderr)
        pcm = [decode_pcm(p, tempo) for p, _ in raw]

    # 2) timeline
    audio = bytearray(silence(LEAD))
    timeline = []  # per scene: narration start/end
    t = LEAD
    for i, b in enumerate(pcm):
        d = len(b) / 2 / SAMPLE_RATE
        timeline.append((t, t + d))
        audio += b
        t += d
        audio += silence(GAP if i < len(pcm) - 1 else TAIL)
        t += GAP if i < len(pcm) - 1 else TAIL
    total = t
    voice_wav = work / "voice.wav"
    import wave
    with wave.open(str(voice_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(bytes(audio))
    starts = [0.0] + [max(0.0, a - 0.15) for a, _ in timeline[1:]]
    ends = starts[1:] + [total]

    # 3) static visuals
    bg = make_background(W, H)
    chrome = make_chrome(spec, W, H, cfg["site"]["channel_name"])
    chrome_bbox = chrome.getbbox()
    chrome_c = chrome.crop(chrome_bbox)
    paper_img = load_paper_image(spec, work) if any(s["layout"] == "paper" for s in scenes) else None
    layers = [render_scene(s, spec, W, H, paper_img) for s in scenes]

    captions = []  # (start, end, image, xy)
    for i, s in enumerate(scenes):
        chunks = chunk_caption(s["narration"])
        n0, n1 = timeline[i]
        rel = caption_times(chunks, s["narration"], [(a / tempo, b / tempo, x) for a, b, x in (raw[i][1] or [])] or None, n1 - n0)
        for j, c in enumerate(chunks):
            cs = n0 + rel[j]
            ce = n0 + rel[j + 1] if j + 1 < len(chunks) else min(ends[i], n1 + 0.35)
            img, xy = render_caption(c, W)
            captions.append((cs, ce, img, xy))

    def compose(ti: float, k: int, with_caption: bool = True) -> Image.Image:
        ox = int(60 + 50 * math.sin(2 * math.pi * ti / 14))
        oy = int(60 + 50 * math.cos(2 * math.pi * ti / 17))
        frame = bg.crop((ox, oy, ox + W, oy + H))
        frame.paste(chrome_c, chrome_bbox[:2], chrome_c)
        local = ti - starts[k]
        layer = layers[k]
        if scenes[k]["layout"] == "stat" and local < 0.9:
            layer = render_scene(scenes[k], spec, W, H, paper_img, stat_progress=max(0.0, local / 0.9))
        bbox = layer.getbbox()
        if bbox:
            content = layer.crop(bbox)
            p = min(1.0, local / 0.32)
            if p < 1.0:
                e = 1 - (1 - p) ** 3
                alpha = content.getchannel("A").point(lambda a: int(a * e))
                content = content.copy()
                content.putalpha(alpha)
                frame.paste(content, (bbox[0], bbox[1] + int(46 * (1 - e))), content)
            else:
                frame.paste(content, bbox[:2], content)
        if with_caption:
            for cs, ce, img, xy in captions:
                if cs <= ti < ce:
                    frame.paste(img, xy, img)
                    break
        d = ImageDraw.Draw(frame)
        d.rectangle((0, 0, int(W * ti / total), 9), fill=ACCENT)
        return frame

    # 4) encode
    out_mp4 = work / f"{stem}.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(voice_wav)]
    bgm = (vcfg.get("bgm") or "").strip()
    voice_chain = "[1:a]loudnorm=I=-15:TP=-1.5:LRA=11,aresample=48000[v]"
    if bgm and (ROOT / bgm).exists():
        cmd += ["-stream_loop", "-1", "-i", str(ROOT / bgm)]
        fc = (f"{voice_chain};[2:a]volume={vcfg.get('bgm_volume', 0.07)},"
              f"afade=t=out:st={max(0.0, total - 1.5):.2f}:d=1.5,aresample=48000[b];"
              "[v][b]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        fc = voice_chain.replace("[v]", "[a]")
    cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast" if fast else "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.3f}", str(out_mp4)]
    n_frames = int(math.ceil(total * FPS))
    print(f"[render] encoding {n_frames} frames ({total:.1f}s)...", file=sys.stderr)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    k = 0
    for fi in range(n_frames):
        ti = fi / FPS
        while k + 1 < len(scenes) and ti >= starts[k + 1]:
            k += 1
        proc.stdin.write(compose(ti, k).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg 인코딩 실패")

    # 5) previews
    ASSETS_SHORTS_DIR.mkdir(parents=True, exist_ok=True)
    thumb = ASSETS_SHORTS_DIR / f"{stem}-thumb.jpg"
    compose(starts[0] + 0.6, 0, with_caption=False).save(thumb, quality=86)
    tiles = []
    for i in range(len(scenes)):
        ti = min(ends[i] - 0.05, starts[i] + 1.2)
        tiles.append(compose(ti, i).resize((270, 480), Image.LANCZOS))
    cols = min(4, len(tiles))
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * 270 + (cols + 1) * 12, rows * 480 + (rows + 1) * 12), (30, 34, 40))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (12 + (i % cols) * 282, 12 + (i // cols) * 492))
    sheet_path = ASSETS_SHORTS_DIR / f"{stem}-sheet.jpg"
    sheet.save(sheet_path, quality=82)

    timings = [(starts[i], ends[i]) for i in range(len(scenes))]
    md_path = SHORTS_DIR / f"{stem}.md"
    md_path.write_text(script_markdown(spec, timings, total, tempo), encoding="utf-8")
    result = {"video": str(out_mp4), "thumb": str(thumb), "sheet": str(sheet_path), "script": str(md_path),
              "duration": round(total, 2), "tempo": round(tempo, 3)}
    print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
    return result


def _ts(sec: float) -> str:
    return f"{int(sec // 60):02d}:{sec % 60:04.1f}"


def script_markdown(spec: dict[str, Any], timings, total: float, tempo: float) -> str:
    sh = spec["shorts"]
    p = spec["paper"]
    venue = p["venue"]["venue"] if p.get("venue") else "—"
    out = [
        f"# 🎬 60초 쇼츠 대본 — {p['title']}",
        "",
        f"- **유튜브 제목**: {sh['title']} #Shorts",
        "- **제목 후보**: " + " / ".join(sh.get("title_candidates", [])),
        f"- **러닝타임**: {total:.1f}초" + (f" (음성 {tempo:.2f}배속 적용)" if tempo > 1.001 else ""),
        f"- **논문**: [{p['title']}]({p['abs_url']}) · 학회: {venue}",
        f"- **블로그**: {spec['blog_url']}",
        "",
        "## ⏱️ 타임라인",
        "",
        "| 시간 | 레이아웃 | 화면 문구 | 내레이션 | 연출 메모 |",
        "|---|---|---|---|---|",
    ]
    for (a, b), s in zip(timings, sh["scenes"]):
        screen = s["headline"].replace("\n", " ").replace("|", "\\|")
        extra = s.get("stat_value") or " vs ".join(x for x in (s.get("left_value"), s.get("right_value")) if x)
        if s.get("bullets"):
            extra = " · ".join(s["bullets"])
        if extra:
            screen += f"<br/><sub>{extra}</sub>"
        out.append(f"| {_ts(a)}~{_ts(b)} | `{s['layout']}` | {screen} | {s['narration']} | {s.get('broll_note', '')} |")
    out += ["", "## 📝 유튜브 설명란", "", "```", youtube_description(spec), "```", "",
            "## ✅ 사실 확인 체크리스트 (논문 원문 근거)", ""]
    for f in spec.get("facts", []):
        out.append(f"- [ ] **{f['claim']}** — “{f['evidence_quote']}” ({f['location']})")
    return "\n".join(out) + "\n"


def youtube_description(spec: dict[str, Any]) -> str:
    p = spec["paper"]
    venue = p["venue"]["venue"] if p.get("venue") else ""
    tags = ["#Shorts", "#AI", "#논문리뷰", "#인공지능"]
    if venue:
        tags.append("#" + venue.replace(" ", ""))
    return "\n".join([
        spec["shorts"]["description"].strip(),
        "",
        f"📝 블로그 상세 리뷰: {spec['blog_url']}",
        f"📄 논문: {p['title']}" + (f" ({venue})" if venue else ""),
        f"🔗 arXiv: {p['abs_url']}",
        "",
        "※ 이 영상은 AI(Claude)로 논문 원문을 분석해 대본을 만들고, AI 음성으로 낭독했습니다.",
        "",
        " ".join(tags),
    ])


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a YouTube Shorts video from a shorts spec")
    ap.add_argument("spec", type=Path)
    ap.add_argument("--fast", action="store_true", help="faster, slightly larger encode (preview)")
    args = ap.parse_args()
    render(args.spec, fast=args.fast)


if __name__ == "__main__":
    main()
