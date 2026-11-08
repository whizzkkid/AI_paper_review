#!/usr/bin/env python3
"""Learn the editor's style from their edits.

Compares each untouched AI draft in editorial/drafts/ with the current (edited) post / Shorts script,
asks Claude which *general* rules explain the edits, and appends them to editorial/style-guide.md
under "## 학습된 규칙". Every later generation reads that file, so the automation follows "my way".

    python -m pipeline.learn --dry-run     # just show what changed (no API key needed)
    python -m pipeline.learn               # propose + append rules, then reset the drafts baseline
"""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import sys
from pathlib import Path

from .common import DRAFTS_DIR, EDITORIAL_DIR, POSTS_DIR, load_config, now_kst, spec_path_for

GUIDE = EDITORIAL_DIR / "style-guide.md"
LOG = EDITORIAL_DIR / "edit-log.md"
MAX_DIFF_CHARS = 60_000

RULES_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "rules": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "rule": {"type": "string"},
                "applies_to": {"type": "string", "enum": ["블로그", "쇼츠", "공통"]},
                "evidence": {"type": "string"},
            },
            "required": ["rule", "applies_to", "evidence"],
            "additionalProperties": False,
        }},
    },
    "required": ["summary", "rules"],
    "additionalProperties": False,
}

PROMPT = """당신은 편집장의 취향을 문서화하는 수석 에디터입니다.
아래는 AI가 쓴 초안(-)을 편집장이 직접 고친 결과(+)의 diff입니다. 블로그 글(md)과 쇼츠 대본(yml)이 섞여 있습니다.

할 일: 앞으로의 AI 초안이 처음부터 편집장처럼 쓰도록, 이 수정들을 설명하는 **일반 규칙**을 뽑으세요.
- 특정 논문에만 해당하는 내용(이 숫자를 저 숫자로 정정 등)은 규칙이 아닙니다. 다만 그런 정정이 반복되면
  "사실 확인" 류의 일반 규칙으로 바꿔 쓰세요.
- 기존 스타일 가이드에 이미 있는 내용은 빼세요. 서로 충돌하면 편집장의 최신 수정이 우선임을 규칙에 명시하세요.
- 규칙은 실행 가능한 한 문장(예: "쇼츠 헤드라인은 의문문보다 단정형으로 쓴다")으로, 최대 8개.
- evidence에는 어떤 수정에서 나온 규칙인지 짧게 적습니다.
- summary는 이번 수정의 전체 경향을 2~3문장으로.
"""


def collect_diffs() -> list[tuple[str, str, Path, Path, str]]:
    """[(stem, kind, draft, final, unified_diff)] for every draft whose final version differs."""
    out = []
    if not DRAFTS_DIR.exists():
        return out
    for draft in sorted(DRAFTS_DIR.iterdir()):
        if draft.name.endswith(".post.md"):
            stem, kind = draft.name[: -len(".post.md")], "블로그"
            final = POSTS_DIR / f"{stem}.md"
        elif draft.name.endswith(".shorts.yml"):
            stem, kind = draft.name[: -len(".shorts.yml")], "쇼츠"
            final = spec_path_for(stem)
        else:
            continue
        if not final.exists():
            continue
        a = draft.read_text(encoding="utf-8").splitlines(keepends=True)
        b = final.read_text(encoding="utf-8").splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(a, b, f"AI초안/{draft.name}", f"편집본/{final.name}", n=2))
        if diff.strip():
            out.append((stem, kind, draft, final, diff))
    return out


def ask_claude(diff_text: str, guide: str) -> dict:
    import anthropic

    cfg = load_config()["claude"]
    client = anthropic.Anthropic()
    with client.beta.messages.stream(
        model=cfg["model"], max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        system=PROMPT,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": RULES_SCHEMA}},
        messages=[{"role": "user", "content": f"# 현재 스타일 가이드\n{guide}\n\n# 편집 diff\n{diff_text}"}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("Claude가 요청을 거절했습니다.")
    return json.loads(next(b.text for b in msg.content if b.type == "text"))


def main() -> None:
    ap = argparse.ArgumentParser(description="Turn the editor's edits into style-guide rules")
    ap.add_argument("--dry-run", action="store_true", help="print the diffs only")
    ap.add_argument("--keep-drafts", action="store_true", help="do not reset the drafts baseline afterwards")
    args = ap.parse_args()

    diffs = collect_diffs()
    if not diffs:
        print("[learn] AI 초안과 달라진 글·쇼츠가 없습니다. 먼저 _posts/…md 나 shorts/…yml 을 고쳐 보세요.")
        return
    print(f"[learn] 수정된 파일 {len(diffs)}개: " + ", ".join(f"{k}:{s}" for s, k, *_ in diffs))
    diff_text = "\n\n".join(d for *_, d in diffs)
    if len(diff_text) > MAX_DIFF_CHARS:
        print(f"[learn] diff가 길어 앞 {MAX_DIFF_CHARS:,}자만 분석합니다.", file=sys.stderr)
        diff_text = diff_text[:MAX_DIFF_CHARS]
    if args.dry_run:
        print(diff_text)
        return

    guide = GUIDE.read_text(encoding="utf-8")
    result = ask_claude(diff_text, guide)
    today = now_kst().strftime("%Y-%m-%d")
    block = [f"\n### {today} — {', '.join(sorted({s for s, *_ in diffs}))}", ""]
    block += [f"- [{r['applies_to']}] {r['rule']}  <sub>근거: {r['evidence']}</sub>" for r in result["rules"]]
    GUIDE.write_text(guide.rstrip() + "\n" + "\n".join(block) + "\n", encoding="utf-8")

    log = LOG.read_text(encoding="utf-8") if LOG.exists() else "# 편집 기록\n\nAI 초안 대비 편집장 수정의 요약입니다.\n"
    LOG.write_text(log.rstrip() + f"\n\n## {today}\n{result['summary']}\n", encoding="utf-8")
    print(f"[learn] 규칙 {len(result['rules'])}개를 {GUIDE.relative_to(GUIDE.parents[1])}에 추가했습니다.")
    for r in result["rules"]:
        print(f"  - [{r['applies_to']}] {r['rule']}")

    if not args.keep_drafts:  # next run only learns from newer edits
        for _, _, draft, final, _ in diffs:
            shutil.copyfile(final, draft)


if __name__ == "__main__":
    main()
