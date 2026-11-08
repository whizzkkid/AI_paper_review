#!/usr/bin/env python3
"""Generate a grounded Korean blog review + YouTube Shorts spec for one paper with Claude.

Claude reads the *full paper PDF* (not just the abstract) and must back every key
number with a verbatim quote, which is listed in the review PR for a quick fact check.

    python -m pipeline.generate --arxiv-id 2610.42149
    python -m pipeline.generate --arxiv-id 2610.42149 --content-json my_content.json   # skip Claude
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

from .common import (
    BUILD_DIR, POSTS_DIR, ROOT, SHORTS_DIR, load_config, normalize_arxiv_id, now_kst, slugify,
)
from .paper import download_pdf, fetch_paper, pdf_text

LAYOUTS = ["hook", "paper", "bullets", "stat", "compare", "cta"]

_STR = {"type": "string"}
_STRS = {"type": "array", "items": {"type": "string"}}

SCENE_SCHEMA = {
    "type": "object",
    "properties": {
        "layout": {"type": "string", "enum": LAYOUTS},
        "headline": _STR,
        "subtext": _STR,
        "bullets": _STRS,
        "stat_value": _STR,
        "stat_label": _STR,
        "left_label": _STR,
        "left_value": _STR,
        "right_label": _STR,
        "right_value": _STR,
        "narration": _STR,
        "broll_note": _STR,
    },
    "required": [
        "layout", "headline", "subtext", "bullets", "stat_value", "stat_label",
        "left_label", "left_value", "right_label", "right_value", "narration", "broll_note",
    ],
    "additionalProperties": False,
}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "blog_title": _STR,
        "blog_description": _STR,
        "blog_tags": _STRS,
        "blog_body_markdown": _STR,
        "shorts_title": _STR,
        "shorts_title_candidates": _STRS,
        "youtube_description": _STR,
        "youtube_tags": _STRS,
        "scenes": {"type": "array", "items": SCENE_SCHEMA},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"claim": _STR, "evidence_quote": _STR, "location": _STR},
                "required": ["claim", "evidence_quote", "location"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "blog_title", "blog_description", "blog_tags", "blog_body_markdown", "shorts_title",
        "shorts_title_candidates", "youtube_description", "youtube_tags", "scenes", "facts",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """당신은 AI 분야 박사급 연구자이자, 어려운 논문을 한국어로 정확하고 재미있게 풀어내는 테크 크리에이터입니다.
독자는 AI 엔지니어·대학원생과 AI에 관심 많은 일반인입니다. 첨부된 논문 PDF 전문을 읽고, 블로그 리뷰와 60초 유튜브 쇼츠 대본을 만듭니다.

# 사실성 원칙 (가장 중요)
- 모든 수치·실험 결과·비교는 첨부 PDF에 실제로 있는 것만 씁니다. 반올림 외의 가공, 추정, 기억에 의존한 보충은 하지 않습니다.
- 학회 채택·수상 정보는 사용자 메시지의 `venue` 항목에 있을 때만 언급합니다. 없으면 "학회 논문", "최고 논문" 같은 표현을 쓰지 않습니다.
- 모델·데이터셋·벤치마크 이름은 논문 표기를 따릅니다.
- 논문이 주장하는 것과 당신의 해석을 구분합니다("논문에 따르면", "제 생각에는").
- `facts`에는 블로그와 쇼츠에 쓴 핵심 수치·주장(5~10개)마다 근거가 되는 원문 문장(영문 그대로, 40단어 이내)과 위치(예: "Table 2", "Section 4.1", "Abstract")를 적습니다. 리뷰어가 이것으로 사실 확인을 합니다.

# 블로그 (blog_*)
- blog_title: "[핵심을 찌르는 한글 제목] 영문 원제" 형식. 과장·낚시 금지, 호기심은 유발.
- blog_description: 검색 결과에 보일 1~2문장 요약.
- blog_tags: 5~8개 (학회명이 있으면 포함, 핵심 기법·분야).
- blog_body_markdown: 프론트매터와 논문 정보 박스는 자동으로 붙으니 쓰지 말고 본문만. 2,500~4,500자. 구성:
  ## 1. 인트로 — 누구나 공감할 문제의식
  ## 2. 기존 방식의 한계 — 왜 지금까지 안 됐나
  ## 3. 핵심 아이디어 — 방법을 직관 → 구체 순으로. ```mermaid 다이어그램 1개 이상(모바일 가독성을 위해 flowchart TD, 노드 7개 이하, 노드 라벨은 반드시 큰따옴표로 감싸기, 예: A["입력 이미지"] --> B["인코더"]). 필요하면 수식($...$, $$...$$).
  ## 4. 실험 결과 — 마크다운 표 1개 이상, 원문 수치 그대로
  ## 5. 한계와 열린 질문 — 논문이 밝힌 한계 + 비판적 시각
  ## 6. 실무자·연구자를 위한 시사점
  ### 📌 요약 (TL;DR) — 3줄 불릿

# 쇼츠 (shorts_*, youtube_*, scenes)
- 전체 내레이션 240~300자(공백 포함) ≈ 50~55초. 장면 6~7개, 장면당 내레이션 25~60자.
- 장면 순서: 1번 layout="hook"(첫 3초 안에 시선을 잡는 질문/반전, 내레이션 35자 이내) → 2번 layout="paper"(논문 소개: 무엇을 한 논문인지, 학회/기관) → 중간은 "bullets"/"stat"/"compare" 중 내용에 맞게 → 마지막 layout="cta".
- headline: 화면에 크게 뜨는 문구. 한 줄 12자 이내, 최대 2줄(줄바꿈은 \\n). 가장 중요한 단어 1개를 **강조**로 감쌉니다. 이모지 금지.
- subtext: 화면 보조 문구(30자 이내, 없으면 ""). bullets: "bullets" 레이아웃에서만 2~3개(각 18자 이내), 그 외 [].
- stat_value/stat_label: "stat" 레이아웃에서만(예: "2.3배", "추론 속도 향상"), 그 외 "".
- left_/right_ 필드: "compare" 레이아웃에서만(예: 기존 방법 vs 제안 방법의 값), 그 외 "".
- narration: TTS가 읽는 구어체 존댓말. 화면 자막으로도 쓰입니다. 화살표·괄호·콜론·슬래시 같은 기호와 이모지를 쓰지 마세요. TTS가 잘못 읽기 쉬운 영어 고유명사는 한글 발음으로 씁니다(예: NeurIPS→뉴립스, ICLR→아이클리어, BAGEL→베이글). GPT, AI처럼 흔한 약어는 그대로 둡니다. 화면 문구(headline 등)에는 영문 표기를 그대로 써도 됩니다.
- cta 내레이션: 설명란의 블로그 링크로 상세 리뷰를 안내하고 구독을 권합니다("고정 댓글"이라고 하지 마세요).
- broll_note: 편집자를 위한 화면 연출 메모(한 줄).
- shorts_title: 60자 이내, 호기심을 자극하되 사실에 근거. 해시태그는 쓰지 않습니다(자동 추가). shorts_title_candidates: 대안 3개.
- youtube_description: 3~5줄 요약(링크·해시태그는 자동 추가되니 쓰지 않음). youtube_tags: 8~15개.
"""


def _paper_brief(paper: dict[str, Any]) -> str:
    v = paper.get("venue")
    venue = f"{v['venue']}{' ' + v['honor'] if v.get('honor') else ''} ({'워크숍' if v['track'] == 'workshop' else '본 학회'})" if v else "(없음 — 학회 언급 금지)"
    authors = paper["authors"]
    author_str = ", ".join(authors[:8]) + (f" 외 {len(authors) - 8}명" if len(authors) > 8 else "")
    lines = [
        f"- arXiv ID: {paper['arxiv_id']}",
        f"- 제목: {paper['title']}",
        f"- 저자: {author_str}",
        f"- 소속(HF 표기): {paper.get('organization') or '(정보 없음)'}",
        f"- 최초 공개일: {paper['published']}",
        f"- venue: {venue}",
        f"- arXiv comment: {paper.get('comment') or '(없음)'}",
    ]
    if paper.get("upvotes"):
        lines.append(f"- Hugging Face Daily Papers 업보트: {paper['upvotes']}")
    return "\n".join(lines)


def generate_content(paper: dict[str, Any], pdf_path: Path) -> dict[str, Any]:
    """Call Claude with the full PDF and return the structured review content."""
    import anthropic

    cfg = load_config()["claude"]
    client = anthropic.Anthropic()

    pdf_bytes = pdf_path.read_bytes()
    if len(pdf_bytes) <= 20 * 1024 * 1024:  # base64 grows 4/3 → stays under the 32 MB request limit
        doc_block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf",
                       "data": base64.standard_b64encode(pdf_bytes).decode()},
            "title": paper["title"],
        }
    else:  # very large PDFs (huge figures) → send the extracted text instead
        text = pdf_text(pdf_path)
        if not text.strip():
            raise RuntimeError("PDF가 너무 크고 텍스트 추출도 실패했습니다.")
        doc_block = {"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": text},
                     "title": paper["title"]}

    user_text = (
        "첨부한 논문으로 블로그 리뷰와 60초 쇼츠 대본을 작성해 주세요.\n\n"
        f"# 논문 메타데이터\n{_paper_brief(paper)}\n"
    )

    print(f"[generate] Claude({cfg['model']}, effort={cfg['effort']}) 가 논문 전문을 읽는 중...", file=sys.stderr)
    with client.beta.messages.stream(
        model=cfg["model"],
        max_tokens=cfg["max_tokens"],
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM_PROMPT,
        output_config={
            "effort": cfg["effort"],
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
        messages=[{"role": "user", "content": [doc_block, {"type": "text", "text": user_text}]}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        raise RuntimeError(f"Claude가 요청을 거절했습니다: {details}")
    if message.stop_reason == "max_tokens":
        raise RuntimeError("max_tokens에 도달해 출력이 잘렸습니다. config.yml의 claude.max_tokens를 늘려주세요.")

    text = next(b.text for b in message.content if b.type == "text")
    u = message.usage
    print(f"[generate] done: in={u.input_tokens} out={u.output_tokens} tokens (message {message.id})",
          file=sys.stderr)
    return json.loads(text)


# ── validation / normalization ─────────────────────────────────

_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")


def normalize_content(c: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    scenes = c["scenes"]
    for s in scenes:
        s["headline"] = _EMOJI_RE.sub("", s["headline"]).replace("\\n", "\n").strip()
        s["narration"] = _EMOJI_RE.sub("", s["narration"]).strip()
        if s["layout"] != "bullets":
            s["bullets"] = []
    if not (5 <= len(scenes) <= 8):
        warnings.append(f"장면 수가 {len(scenes)}개입니다 (권장 6~7).")
    if scenes and scenes[0]["layout"] != "hook":
        warnings.append("첫 장면이 hook이 아닙니다.")
    if scenes and scenes[-1]["layout"] != "cta":
        warnings.append("마지막 장면이 cta가 아닙니다.")
    total = sum(len(s["narration"]) for s in scenes)
    if not (200 <= total <= 340):
        warnings.append(f"내레이션 총 {total}자 (권장 240~300자).")
    c["shorts_title"] = c["shorts_title"].replace("#Shorts", "").replace("#shorts", "").strip()
    return c, warnings


# ── writing outputs ───────────────────────────────────────────

def _post_header(paper: dict[str, Any]) -> str:
    authors = paper["authors"]
    author_str = ", ".join(authors[:6]) + (f" 외 {len(authors) - 6}명" if len(authors) > 6 else "")
    if paper.get("organization"):
        author_str += f" ({paper['organization']})"
    links = [f"[arXiv:{paper['arxiv_id']}]({paper['abs_url']})", f"[PDF]({paper['pdf_url']})"]
    if paper.get("hf_url"):
        links.append(f"[Hugging Face]({paper['hf_url']})")
    if paper.get("project_page"):
        links.append(f"[프로젝트 페이지]({paper['project_page']})")
    lines = [f"> **논문 원제**: *{paper['title']}*  "]
    v = paper.get("venue")
    if v:
        honor = f" · **{v['honor']}**" if v.get("honor") else ""
        track = " (Workshop)" if v["track"] == "workshop" else ""
        lines.append(f"> **학회**: **{v['venue']}**{track}{honor}  ")
    lines.append(f"> **저자**: {author_str}  ")
    lines.append(f"> **원문 링크**: {' / '.join(links)}")
    return "\n".join(lines)


def write_outputs(paper: dict[str, Any], content: dict[str, Any], *, date=None) -> dict[str, Any]:
    """Write the Jekyll post and the Shorts spec; return the spec (with file paths)."""
    cfg = load_config()
    date = date or now_kst()
    slug = slugify(paper["title"])
    stem = f"{date:%Y-%m-%d}-{slug}"
    post_path = POSTS_DIR / f"{stem}.md"
    spec_path = SHORTS_DIR / f"{stem}.json"
    blog_url = f"{cfg['site']['base_url'].rstrip('/')}/posts/{slug}/"

    v = paper.get("venue")
    categories = ["AI Research"] + ([v["venue"]] if v and v["track"] == "main" else [])
    front = {
        "layout": "post",
        "title": content["blog_title"],
        "date": f"{date:%Y-%m-%d %H:%M:%S} +0900",
        "categories": categories,
        "tags": content["blog_tags"],
        "description": content["blog_description"],
        "arxiv_id": paper["arxiv_id"],
        "venue": v["venue"] if v else "",
        "image": f"/assets/shorts/{stem}-thumb.jpg",
        "shorts_spec": f"shorts/{stem}.json",
        "youtube_id": "",
    }
    body = content["blog_body_markdown"].strip()
    footer = ("\n\n---\n\n<small>이 리뷰는 AI(Claude)가 논문 원문을 분석해 초안을 작성하고, "
              f"작성자({cfg['site']['author']})가 검토·승인한 뒤 게시되었습니다. 수치와 표현은 반드시 원문으로 확인하세요.</small>\n")
    POSTS_DIR.mkdir(exist_ok=True)
    post_path.write_text(
        "---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000) + "---\n\n"
        + _post_header(paper) + "\n\n---\n\n" + body + footer,
        encoding="utf-8",
    )

    spec = {
        "version": 1,
        "stem": stem,
        "slug": slug,
        "post": str(post_path.relative_to(ROOT)),
        "blog_url": blog_url,
        "paper": {k: paper.get(k) for k in (
            "arxiv_id", "title", "authors", "published", "organization", "venue", "upvotes",
            "abs_url", "pdf_url", "hf_url", "project_page")},
        "shorts": {
            "title": content["shorts_title"],
            "title_candidates": content["shorts_title_candidates"],
            "description": content["youtube_description"],
            "tags": content["youtube_tags"],
            "scenes": content["scenes"],
        },
        "facts": content["facts"],
        "youtube": {"skip": False, "video_id": "", "url": "", "uploaded_at": ""},
        "generated_at": date.isoformat(timespec="seconds"),
    }
    SHORTS_DIR.mkdir(exist_ok=True)
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    spec["_spec_path"] = str(spec_path)
    return spec


def enrich_paper(paper: dict[str, Any], extra: dict[str, Any] | None) -> dict[str, Any]:
    """Merge discovery info (HF upvotes, organization, project page) into arXiv metadata."""
    if extra:
        for k in ("upvotes", "organization", "project_page", "hf_url"):
            if extra.get(k) and not paper.get(k):
                paper[k] = extra[k]
    paper.setdefault("hf_url", f"https://huggingface.co/papers/{paper['arxiv_id']}")
    return paper


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a blog review + Shorts spec with Claude")
    ap.add_argument("--arxiv-id", required=True)
    ap.add_argument("--content-json", help="use this content JSON instead of calling Claude")
    ap.add_argument("--extra-json", help="discovery info JSON (upvotes, organization, ...)")
    args = ap.parse_args()

    paper = fetch_paper(normalize_arxiv_id(args.arxiv_id))
    extra = json.loads(Path(args.extra_json).read_text()) if args.extra_json else None
    paper = enrich_paper(paper, extra)
    work = BUILD_DIR / paper["arxiv_id"]
    pdf = download_pdf(paper, work)

    if args.content_json:
        content = json.loads(Path(args.content_json).read_text(encoding="utf-8"))
    else:
        content = generate_content(paper, pdf)
        (work / "content.json").write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    content, warnings = normalize_content(content)
    for w in warnings:
        print(f"[warn] {w}", file=sys.stderr)
    spec = write_outputs(paper, content)
    print(json.dumps({"spec": spec["_spec_path"], "post": spec["post"], "warnings": warnings}, ensure_ascii=False))


if __name__ == "__main__":
    main()
