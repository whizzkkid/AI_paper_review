"""arXiv metadata, conference/venue detection, PDF download and page rendering."""

from __future__ import annotations

import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .common import http_get, normalize_arxiv_id

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV = "{http://arxiv.org/schemas/atom}"

VENUES = [
    "NeurIPS", "ICLR", "ICML", "CVPR", "ICCV", "ECCV", "ACL", "EMNLP", "NAACL", "COLM",
    "AAAI", "IJCAI", "KDD", "SIGGRAPH", "CoRL", "RSS", "ICRA", "IROS", "AISTATS", "UAI",
    "WWW", "SIGIR", "INTERSPEECH", "ICASSP", "WACV", "TMLR", "JMLR", "TPAMI", "MICCAI",
]
_VENUE_RE = re.compile(
    r"\b(" + "|".join(VENUES) + r")(?:\s*['’]?\s*(\d{4}|\d{2}))?\b", re.I
)
_NOT_ACCEPTED_RE = re.compile(r"(submitted|under review|in review|preprint for|submission to)", re.I)
_HONOR_RE = re.compile(r"\b(best paper|outstanding paper|oral|spotlight|highlight)\b", re.I)


def detect_venue(comment: str, journal_ref: str = "") -> dict[str, str] | None:
    """Find an *accepted* venue in arXiv comment/journal_ref, e.g. 'Accepted at NeurIPS 2026 (Oral)'."""
    text = f"{comment} {journal_ref}".strip()
    if not text:
        return None
    m = _VENUE_RE.search(text)
    if not m:
        return None
    if _NOT_ACCEPTED_RE.search(text[: m.start()][-60:]):
        return None
    canon = next(v for v in VENUES if v.lower() == m.group(1).lower())
    year = m.group(2) or ""
    if len(year) == 2:
        year = "20" + year
    venue = f"{canon} {year}".strip()
    window = text[max(0, m.start() - 80): m.end() + 80]
    track = "workshop" if re.search(r"workshop", window, re.I) else "main"
    honor = ""
    h = _HONOR_RE.search(window)
    if h:
        honor = h.group(1).title()
    return {"venue": venue, "track": track, "honor": honor, "raw": text[:300]}


def fetch_arxiv_metadata(ids: list[str]) -> dict[str, dict[str, Any]]:
    """Batch-fetch metadata from the arXiv API (50 IDs per call, 3 s apart as arXiv asks)."""
    out: dict[str, dict[str, Any]] = {}
    ids = [normalize_arxiv_id(i) for i in ids]
    for start in range(0, len(ids), 50):
        chunk = ids[start:start + 50]
        url = f"https://export.arxiv.org/api/query?id_list={','.join(chunk)}&max_results={len(chunk)}"
        root = ET.fromstring(http_get(url, timeout=90))
        for e in root.findall(ATOM + "entry"):
            id_el = e.find(ATOM + "id")
            if id_el is None or "/abs/" not in (id_el.text or ""):
                continue
            aid = normalize_arxiv_id(id_el.text.rsplit("/abs/", 1)[-1])

            def text(tag: str, ns: str = ATOM) -> str:
                el = e.find(ns + tag)
                return re.sub(r"\s+", " ", el.text).strip() if el is not None and el.text else ""

            cat = e.find(ARXIV + "primary_category")
            comment, journal_ref = text("comment", ARXIV), text("journal_ref", ARXIV)
            out[aid] = {
                "arxiv_id": aid,
                "title": text("title"),
                "abstract": text("summary"),
                "authors": [
                    re.sub(r"\s+", " ", a.find(ATOM + "name").text).strip()
                    for a in e.findall(ATOM + "author")
                ],
                "published": text("published")[:10],
                "updated": text("updated")[:10],
                "comment": comment,
                "journal_ref": journal_ref,
                "primary_category": cat.get("term") if cat is not None else "",
                "venue": detect_venue(comment, journal_ref),
                "abs_url": f"https://arxiv.org/abs/{aid}",
                "pdf_url": f"https://arxiv.org/pdf/{aid}",
            }
        if start + 50 < len(ids):
            time.sleep(3)
    return out


def fetch_paper(arxiv_id: str) -> dict[str, Any]:
    aid = normalize_arxiv_id(arxiv_id)
    meta = fetch_arxiv_metadata([aid])
    if aid not in meta:
        raise ValueError(f"arXiv:{aid} 를 찾을 수 없습니다.")
    return meta[aid]


def download_pdf(paper: dict[str, Any], dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / "paper.pdf"
    if not path.exists() or path.stat().st_size < 10_000:
        data = http_get(paper["pdf_url"], timeout=180)
        if not data.startswith(b"%PDF"):
            raise ValueError(f"{paper['pdf_url']} 가 PDF가 아닙니다.")
        path.write_bytes(data)
    return path


def render_first_page(pdf_path: Path, dest: Path, dpi: int = 130) -> Path | None:
    """Render page 1 to PNG with poppler's pdftoppm (used as the 'paper card' visual)."""
    if not shutil.which("pdftoppm"):
        return None
    prefix = dest.with_suffix("")
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), "-f", "1", "-l", "1", "-singlefile", str(pdf_path), str(prefix)],
        check=True, capture_output=True,
    )
    out = prefix.with_suffix(".png")
    return out if out.exists() else None


def pdf_text(pdf_path: Path) -> str:
    """Plain-text fallback (pdftotext) for PDFs too large to send as a document block."""
    if not shutil.which("pdftotext"):
        return ""
    res = subprocess.run(["pdftotext", "-layout", str(pdf_path), "-"], capture_output=True, text=True)
    return res.stdout
