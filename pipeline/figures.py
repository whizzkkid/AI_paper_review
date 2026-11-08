"""Download a paper's numbered figures (image + caption) from the arXiv HTML version.

Most recent arXiv papers have an HTML rendering (https://arxiv.org/html/<id>) whose figures are
plain image files. These become `figure` scenes in the Shorts and are shown to Claude so it can
pick the most telling one (e.g. a qualitative comparison) and the region to zoom into.
"""

from __future__ import annotations

import html
import io
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

from .common import USER_AGENT, http_get

_FIG_RE = re.compile(r"<figure\b([^>]*)>(.*?)</figure>", re.S)
_IMG_RE = re.compile(r'<img\b[^>]*\bsrc="([^"]+)"', re.S)
_CAP_RE = re.compile(r"<figcaption[^>]*>(.*?)</figcaption>", re.S)
_NUM_RE = re.compile(r"^(Figure|Fig\.)\s*(\d+)\s*[:.]", re.I)


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def fetch_figures(arxiv_id: str, dest_dir: Path, max_figures: int = 10) -> list[dict[str, Any]]:
    """Return [{id: 'Figure 3', file, caption, width, height}] (empty list if no HTML version)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    cache = dest_dir / "figures.json"
    if cache.exists():
        figs = json.loads(cache.read_text(encoding="utf-8"))
        if all(Path(f["file"]).exists() for f in figs):
            return figs
    try:
        req = urllib.request.Request(f"https://arxiv.org/html/{arxiv_id}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            base, page = resp.geturl(), resp.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"[figures] arXiv HTML 없음({arxiv_id}): {e}", file=sys.stderr)
        return []

    figs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for attrs, body in _FIG_RE.findall(page):
        if "ltx_table" in attrs or "ltx_figure_panel" in attrs:
            continue
        imgs = _IMG_RE.findall(body)
        cap_m = _CAP_RE.search(body)
        if len(imgs) != 1 or not cap_m:
            continue
        caption = _text(cap_m.group(1))
        num = _NUM_RE.match(caption)
        if not num or num.group(2) in seen:
            continue
        src = urllib.parse.urljoin(base, imgs[0])
        if not re.search(r"\.(png|jpe?g|gif|webp)$", src, re.I):
            continue
        try:
            im = Image.open(io.BytesIO(http_get(src, timeout=60))).convert("RGB")
        except Exception as e:
            print(f"[figures] 다운로드 실패 {src}: {e}", file=sys.stderr)
            continue
        if min(im.size) < 200:
            continue
        if im.width > 2400:
            im = im.resize((2400, round(im.height * 2400 / im.width)), Image.LANCZOS)
        seen.add(num.group(2))
        path = dest_dir / f"figure{num.group(2)}.png"
        im.save(path)
        figs.append({"id": f"Figure {num.group(2)}", "file": str(path), "caption": caption[:400],
                     "width": im.width, "height": im.height})
        if len(figs) >= max_figures:
            break
    cache.write_text(json.dumps(figs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[figures] {arxiv_id}: {len(figs)} figures", file=sys.stderr)
    return figs


FIG_PLACEHOLDER = re.compile(r"\{\{\s*figure:\s*(Figure\s*\d+)\s*(?:\|\s*([^}]*))?\}\}")


def embed_figures(markdown: str, arxiv_id: str, figures: list[dict[str, Any]], assets_root: Path) -> tuple[str, list[Path]]:
    """Replace `{{figure:Figure 3|설명}}` in a post with the paper figure (copied to assets/papers/<id>/)."""
    by_id = {re.sub(r"\s+", " ", f["id"]): f for f in figures}
    written: list[Path] = []

    def repl(m: re.Match) -> str:
        fid = re.sub(r"\s+", " ", m.group(1))
        desc = (m.group(2) or "").strip()
        fig = by_id.get(fid)
        if not fig:
            return ""
        out_dir = assets_root / "papers" / arxiv_id
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"{fid.replace(' ', '').lower()}.png"
        im = Image.open(fig["file"]).convert("RGB")
        if im.width > 1600:
            im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
        im.save(dest, optimize=True)
        written.append(dest)
        web = f"/assets/papers/{arxiv_id}/{dest.name}"
        cap = f"{fid}" + (f" — {desc}" if desc else "")
        return (f'![{desc or fid}]({{{{ "{web}" | relative_url }}}})\n\n'
                f'<p class="fig-cap">그림: 논문 {cap} (출처: arXiv:{arxiv_id})</p>')

    return FIG_PLACEHOLDER.sub(repl, markdown), written
