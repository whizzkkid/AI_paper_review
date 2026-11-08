#!/usr/bin/env python3
"""Validate hand-edited posts and Shorts scripts before they are merged/rendered.

    python -m pipeline.check            # all posts + shorts
Exit code 1 on errors (YAML syntax, unknown visual types, missing fields); warnings never fail.
"""

from __future__ import annotations

import sys

import yaml

from .common import POSTS_DIR, ROOT, list_specs, read_front_matter
from .generate import ICONS, VISUAL_TYPES
from .pronounce import load_lexicon, transliterations

REQUIRED = {
    "chat": ["messages"], "bars": ["items"], "line": ["series"], "flow": ["nodes"], "split": ["left", "right"],
    "stat": ["value"], "steps": ["items"], "figure": ["figure_id"], "tokens": ["words"],
}


def check_spec(path) -> tuple[list[str], list[str]]:
    errors, warns = [], []
    try:
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (줄 {mark.line + 1})" if mark else ""
        return [f"YAML 문법 오류{where}: {getattr(e, 'problem', e)} — 따옴표로 시작한 문장은 끝까지 따옴표로 감싸세요"], []
    scenes = (spec.get("shorts") or {}).get("scenes") or []
    if not scenes:
        errors.append("shorts.scenes가 비어 있습니다")
    total = 0
    lex = load_lexicon(spec)
    for i, s in enumerate(scenes, 1):
        if not str(s.get("narration") or "").strip():
            errors.append(f"장면 {i}: narration이 비어 있습니다")
        for say, term in transliterations(str(s.get("narration") or ""), lex):
            warns.append(f"장면 {i}: 자막에 '{say}' → '{term}'로 쓰세요 (음성은 사전대로 '{say}'로 읽습니다)")
        total += len(str(s.get("narration") or ""))
        v = s.get("visual") or {}
        t = v.get("type")
        if t not in VISUAL_TYPES:
            errors.append(f"장면 {i}: visual.type '{t}'은(는) 없는 유형입니다 ({', '.join(VISUAL_TYPES)})")
            continue
        for field in REQUIRED.get(t, []):
            if not v.get(field):
                errors.append(f"장면 {i} ({t}): '{field}'가 필요합니다")
        icons = [v.get("icon")] + [n.get("icon") for n in v.get("nodes", []) + v.get("items", []) if isinstance(n, dict)]
        icons += [(v.get(side) or {}).get("icon") for side in ("left", "right")]
        for ic in filter(None, icons):
            if ic not in ICONS:
                warns.append(f"장면 {i}: 아이콘 '{ic}'이(가) 목록에 없어 기본 아이콘으로 표시됩니다")
        headline = str(s.get("headline") or "")
        if any(len(line.replace("**", "")) > 16 for line in headline.split("\n")):
            warns.append(f"장면 {i}: 헤드라인 한 줄이 길어 글자가 작아질 수 있습니다")
    if total > 340:
        warns.append(f"내레이션 총 {total}자 — 59초를 넘으면 음성이 자동으로 빨라집니다")
    if not (ROOT / str(spec.get("post", ""))).exists():
        warns.append(f"연결된 블로그 글이 없습니다: {spec.get('post')}")
    return errors, warns


def check_post(path) -> tuple[list[str], list[str]]:
    errors, warns = [], []
    try:
        fm, _ = read_front_matter(path)
    except yaml.YAMLError as e:
        return [f"front matter YAML 오류: {e}"], []
    for key in ("layout", "title", "date"):
        if not fm.get(key):
            errors.append(f"front matter에 '{key}'가 없습니다")
    if fm.get("visibility", "public") not in ("public", "unlisted"):
        errors.append("visibility는 public 또는 unlisted여야 합니다 (사이트에서 빼려면 published: false)")
    spec = fm.get("shorts_spec")
    if spec and not (ROOT / spec).exists():
        warns.append(f"shorts_spec 파일이 없습니다: {spec}")
    return errors, warns


def main() -> None:
    n_err = 0
    targets = [(p, check_spec) for p in list_specs()] + [(p, check_post) for p in sorted(POSTS_DIR.glob("*.md"))]
    for path, fn in targets:
        errors, warns = fn(path)
        rel = path.relative_to(ROOT)
        for e in errors:
            print(f"::error file={rel}::{e}")
        for w in warns:
            print(f"::warning file={rel}::{w}")
        print(f"{'❌' if errors else '✅'} {rel}" + (f"  (경고 {len(warns)})" if warns else ""))
        n_err += len(errors)
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
