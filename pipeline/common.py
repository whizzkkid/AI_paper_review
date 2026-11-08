"""Shared helpers: paths, config, time, slugs, front matter, HTTP."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "_posts"
SHORTS_DIR = ROOT / "shorts"
ASSETS_SHORTS_DIR = ROOT / "assets" / "shorts"
BUILD_DIR = ROOT / "build"
FONTS_DIR = ROOT / "assets" / "fonts"
EDITORIAL_DIR = ROOT / "editorial"
DRAFTS_DIR = EDITORIAL_DIR / "drafts"

KST = timezone(timedelta(hours=9))
USER_AGENT = "AI-Paper-Review-Bot/2.0 (+https://github.com/whizzkkid/AI_paper_review)"


def load_config() -> dict[str, Any]:
    with open(ROOT / "pipeline" / "config.yml", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Shorts spec (human-editable YAML) ─────────────────────────

class _SpecDumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper: yaml.SafeDumper, data: str):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_SpecDumper.add_representer(str, _str_presenter)

SPEC_HEADER = (
    "# ─────────────────────────────────────────────────────────────\n"
    "#  쇼츠 대본 원본 — 이 파일을 고치면 승인(머지) 후 영상이 이 내용대로 렌더링됩니다.\n"
    "#  scenes[].headline: 화면 상단 문구(**강조**, 줄바꿈 가능) / narration: 음성+자막\n"
    "#  scenes[].visual: 장면의 시각화 (type별 필드는 editorial/README.md 참고)\n"
    "# ─────────────────────────────────────────────────────────────\n"
)


def spec_path_for(stem: str) -> Path:
    return SHORTS_DIR / f"{stem}.yml"


def load_spec(path: Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    return json.loads(text) if str(path).endswith(".json") else yaml.safe_load(text)


def save_spec(path: Path, spec: dict[str, Any]) -> None:
    body = yaml.dump({k: v for k, v in spec.items() if not k.startswith("_")}, Dumper=_SpecDumper,
                     allow_unicode=True, sort_keys=False, width=1000)
    Path(path).write_text(SPEC_HEADER + body, encoding="utf-8")


def list_specs() -> list[Path]:
    return sorted(list(SHORTS_DIR.glob("*.yml")) + list(SHORTS_DIR.glob("*.json")))


def load_queue() -> dict[str, list[str]]:
    path = ROOT / "pipeline" / "queue.yml"
    if not path.exists():
        return {"queue": [], "skip": []}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        "queue": [normalize_arxiv_id(str(x)) for x in (data.get("queue") or [])],
        "skip": [normalize_arxiv_id(str(x)) for x in (data.get("skip") or [])],
    }


def now_kst() -> datetime:
    return datetime.now(KST)


def normalize_arxiv_id(value: str) -> str:
    """'arXiv:2505.06120v2' / 'https://arxiv.org/abs/2505.06120' -> '2505.06120'."""
    v = value.strip()
    v = re.sub(r"^https?://(www\.)?arxiv\.org/(abs|pdf|html)/", "", v, flags=re.I)
    v = re.sub(r"^arxiv:\s*", "", v, flags=re.I)
    v = re.sub(r"\.pdf$", "", v)
    v = re.sub(r"v\d+$", "", v)
    return v


def slugify(text: str, max_len: int = 50) -> str:
    words = re.sub(r"[^a-z0-9\s-]", " ", text.lower()).split()
    slug = ""
    for w in words:
        candidate = f"{slug}-{w}" if slug else w
        if len(candidate) > max_len:
            break
        slug = candidate
    return slug or "paper"


# ── HTTP ──────────────────────────────────────────────────────

def http_get(url: str, *, timeout: int = 60, retries: int = 3, accept: str | None = None) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (400, 401, 403, 404):
                raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        time.sleep(2 * (2 ** attempt))
    assert last is not None
    raise last


def http_get_json(url: str, **kw) -> Any:
    return json.loads(http_get(url, accept="application/json", **kw))


# ── Front matter ──────────────────────────────────────────────

_FM_RE = re.compile(r"^---[ \t]*\n(.*?)\n---[ \t]*\n", re.S)


def read_front_matter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    return yaml.safe_load(m.group(1)) or {}, text[m.end():]


def set_front_matter_key(path: Path, key: str, value: str) -> None:
    """Insert or replace a single scalar key in a post's front matter, keeping the rest verbatim."""
    text = path.read_text(encoding="utf-8")
    m = _FM_RE.match(text)
    if not m:
        raise ValueError(f"{path} has no front matter")
    fm = m.group(1)
    line = f"{key}: {json.dumps(value, ensure_ascii=False)}"
    if re.search(rf"^{re.escape(key)}:.*$", fm, flags=re.M):
        fm = re.sub(rf"^{re.escape(key)}:.*$", line, fm, flags=re.M)
    else:
        fm = fm + "\n" + line
    path.write_text(f"---\n{fm}\n---\n" + text[m.end():], encoding="utf-8")


def published_arxiv_ids() -> set[str]:
    """arXiv IDs already covered by a blog post.

    Uses front matter `arxiv_id`; for older posts without it, the first arXiv
    reference in the body (the paper-info header), so papers merely cited in a
    post are not treated as reviewed.
    """
    ids: set[str] = set()
    for post in POSTS_DIR.glob("*.md"):
        fm, body = read_front_matter(post)
        if fm.get("arxiv_id"):
            ids.add(normalize_arxiv_id(str(fm["arxiv_id"])))
            continue
        m = re.search(r"(?:arxiv\.org/(?:abs|pdf)/|arXiv:)(\d{4}\.\d{4,5})", body)
        if m:
            ids.add(m.group(1))
    return ids
