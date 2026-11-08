#!/usr/bin/env python3
"""Generate a grounded Korean blog review + a visual-first Shorts script for one paper with Claude.

Claude reads
  • the full paper PDF (not just the abstract) and its figures (from the arXiv HTML version),
  • editorial/style-guide.md — the editor's rules, edited by hand and grown by `pipeline.learn`,
  • exemplar posts/Shorts the editor approved (`exemplar: true`) — few-shot examples of "my way",
and must back every key number with a verbatim quote (listed in the review PR for fact-checking).
The untouched AI output is saved to editorial/drafts/ so the editor's later edits can be learned.

    python -m pipeline.generate --arxiv-id 2610.42149
    python -m pipeline.generate --arxiv-id 2610.42149 --content-json my_content.json   # skip Claude
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from .common import (
    BUILD_DIR, DRAFTS_DIR, EDITORIAL_DIR, POSTS_DIR, ROOT, load_config, load_spec, normalize_arxiv_id,
    now_kst, read_front_matter, save_spec, slugify, spec_path_for,
)
from .paper import download_pdf, fetch_paper, pdf_text

# ── schema ────────────────────────────────────────────────────

ICONS = sorted(json.loads((ROOT / "pipeline" / "video" / "icons.js").read_text(encoding="utf-8")
                          .split("window.ICONS = ", 1)[1].rstrip().rstrip(";")).keys())
VISUAL_TYPES = ["chat", "bars", "line", "flow", "split", "stat", "steps", "figure", "paper", "tokens", "cta", "title"]

_S = {"type": "string"}
_N = {"type": "number"}
_B = {"type": "boolean"}
_ICON = {"type": "string", "enum": ICONS}


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _arr(item: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item}


def _t(name: str) -> dict[str, Any]:
    return {"type": "string", "const": name}


_BOX = _obj({"x": _N, "y": _N, "w": _N, "h": _N})
_SIDE = _obj({"title": _S, "icon": _ICON, "value": _S, "caption": _S})
VISUAL_SCHEMA = {"anyOf": [
    _obj({"type": _t("chat"), "dim_middle": _B,
          "messages": _arr(_obj({"role": {"type": "string", "enum": ["user", "ai"]}, "text": _S,
                                 "mark": {"type": "string", "enum": ["", "ok", "wrong", "lost"]}}))}),
    _obj({"type": _t("bars"), "unit": _S, "baseline": _N, "baseline_label": _S, "note": _S,
          "items": _arr(_obj({"label": _S, "value": _N, "highlight": _B}))}),
    _obj({"type": _t("line"), "x_label": _S, "y_label": _S, "unit": _S, "y_from_zero": _B, "note": _S,
          "series": _arr(_obj({"name": _S, "highlight": _B, "points": _arr(_obj({"x": _N, "y": _N}))}))}),
    _obj({"type": _t("flow"), "direction": {"type": "string", "enum": ["column", "row"]},
          "nodes": _arr(_obj({"id": _S, "label": _S, "sub": _S, "icon": _ICON, "highlight": _B})),
          "edges": _arr(_obj({"from": _S, "to": _S, "label": _S}))}),
    _obj({"type": _t("split"), "left": _SIDE, "right": _SIDE,
          "verdict": {"type": "string", "enum": ["left", "right", "none"]}}),
    _obj({"type": _t("stat"), "value": _S, "label": _S, "ratio": _N, "icon": _ICON,
          "tone": {"type": "string", "enum": ["good", "bad", "neutral"]}}),
    _obj({"type": _t("steps"), "items": _arr(_obj({"icon": _ICON, "text": _S}))}),
    _obj({"type": _t("figure"), "figure_id": _S, "caption": _S, "crop": _BOX, "focus": _BOX,
          "highlights": _arr(_obj({"x": _N, "y": _N, "w": _N, "h": _N, "label": _S}))}),
    _obj({"type": _t("paper"), "stamp": _S, "orgs": _arr(_S)}),
    _obj({"type": _t("tokens"), "mode": {"type": "string", "enum": ["discrete", "continuous", "both"]},
          "words": _arr(_S), "top_label": _S, "bottom_label": _S}),
    _obj({"type": _t("cta"), "blog_title": _S, "button": _S}),
    _obj({"type": _t("title"), "icon": _ICON, "subtext": _S}),
]}
SCENE_SCHEMA = _obj({"headline": _S, "narration": _S, "visual": VISUAL_SCHEMA, "memo": _S})
OUTPUT_SCHEMA = _obj({
    "blog_title": _S, "blog_description": _S, "blog_tags": _arr(_S), "blog_body_markdown": _S,
    "shorts_title": _S, "shorts_title_candidates": _arr(_S), "youtube_description": _S, "youtube_tags": _arr(_S),
    "scenes": _arr(SCENE_SCHEMA),
    "facts": _arr(_obj({"claim": _S, "evidence_quote": _S, "location": _S})),
})

BASE_PROMPT = """당신은 AI 분야 박사급 연구자이자, 어려운 논문을 한국어로 정확하고 재미있게 풀어내는 테크 크리에이터입니다.
첨부된 논문 PDF 전문과 그림을 읽고, 블로그 리뷰와 '시각화 중심' 60초 유튜브 쇼츠 대본을 만듭니다.

# 사실성 원칙 (어떤 스타일 지침보다 우선)
- 모든 수치·실험 결과·비교는 첨부 PDF에 실제로 있는 것만 씁니다. 반올림 외의 가공, 추정, 기억에 의존한 보충은 하지 않습니다.
- 학회 채택·수상 정보는 메타데이터의 `venue` 항목에 있을 때만 언급합니다.
- 논문이 주장하는 것과 당신의 해석을 구분합니다("논문에 따르면", "제 생각에는").
- `facts`에는 블로그와 쇼츠에 쓴 핵심 수치·주장(5~10개)마다 근거 원문(영문 그대로, 40단어 이내)과 위치(예: "Table 2", "Section 4.1")를 적습니다.

# 블로그 (blog_*)
- blog_title: "[핵심을 찌르는 한글 제목] 영문 원제" 형식. blog_description: 검색 결과용 1~2문장. blog_tags: 5~8개.
- blog_body_markdown: 프론트매터·논문 정보 박스는 자동으로 붙으니 본문만. ```mermaid 다이어그램은 flowchart TD, 노드 7개 이하,
  노드 라벨은 반드시 큰따옴표(예: A["입력"] --> B["인코더"]). 수식은 $...$ / $$...$$. 표는 마크다운 표.
- 본문에 논문 그림을 1~3개 넣습니다. 넣을 자리에 한 줄로 `{{figure:Figure N|한 줄 설명}}`만 쓰면 이미지와 출처가 자동으로 들어갑니다(제공된 그림만).

# 쇼츠: 글자 슬라이드가 아니라 '보여주는' 영상
- 시청자는 글을 읽지 않습니다. 모든 장면은 visual이 주인공이고, 화면 글자는 headline(짧게)과 자막(narration)뿐입니다.
- 장면 6~8개, 전체 narration 260~320자(공백 포함, 약 50~55초). 장면당 narration 25~55자.
- 1번 장면은 가장 강렬한 시각(논문 결과 그림, 현상을 재현한 대화, 충격적인 수치)으로 시작하는 훅. 2번은 visual.type=paper. 마지막은 cta.
- 같은 visual.type을 연속으로 쓰지 말고, 제공된 논문 그림 중 결과가 한눈에 보이는 것(정성 비교 이미지, 핵심 그래프)을 최소 한 장면에 씁니다.
- headline: 한 줄 12자 이내, 최대 2줄(줄바꿈 \\n). 핵심 단어 1개를 **강조**. 이모지 금지. 그래프·그림이 말해주는 장면은 headline을 더 짧게.
- narration: TTS가 읽는 구어체 존댓말이자 자막. 기호(→, :, /, 괄호)와 이모지 금지. TTS가 잘못 읽기 쉬운 영문 고유명사는
  한글 발음으로(NeurIPS→뉴립스, ICLR→아이클리어, BAGEL→베이글). GPT, AI 같은 흔한 약어는 그대로.
- memo: 편집자를 위한 연출 메모 한 줄.

## visual.type 목록 (필드는 스키마를 따르고, 해당 없는 필드는 ""·0·[]·false로 채웁니다)
- chat: LLM·에이전트 현상을 대화로 재현. messages 4~7개(text 22자 이내), mark: ''|ok|wrong|lost, dim_middle: 중간 턴이 흐려지는 연출.
- bars: 수치 비교. 2~5개는 세로, 6~8개는 가로 막대. value는 숫자, unit(예 "%"), highlight 1개, baseline(기준선 값, 없으면 0), note에 출처("논문 Table 1").
- line: 추세·스케일링. series 2~3개(points 3~12개, x는 숫자), highlight 1개, note에 출처.
- flow: 방법·파이프라인 3~5단계(nodes: label 8자 이내, sub 16자 이내). edges 중 바로 다음 노드가 아닌 것은 되돌아가는 루프로 그려집니다.
- split: 기존 vs 제안 대결(left/right: title, icon, value, caption), verdict.
- stat: 핵심 숫자 하나. ratio가 0~1이면 링 게이지, 아니면 -1.
- steps: 실천 팁·절차 2~4개(text 16자 이내).
- figure: 제공된 논문 그림만(figure_id는 "Figure N"). crop은 보여줄 영역(그림 기준 0~1 정규화, 전체면 0,0,1,1) — 세로 화면이므로 넓은 그림은 한 패널만.
  focus는 후반에 줌인할 영역(crop 기준, 없으면 w=0). highlights는 강조 박스 0~2개(crop 기준 좌표, label 10자 이내).
- paper: 논문 소개(첫 페이지 + 학회 도장). stamp는 학회명(+수상), orgs는 소속 기관 4개 이하.
- tokens: 이산 토큰 vs 연속 표현 같은 개념 비유(words 3~6개).
- cta: 마지막 장면. blog_title은 블로그 제목의 한글 부분, button은 "구독하고 다음 논문 받기".
- title: 위 어느 것도 맞지 않을 때만(큰 아이콘 + subtext).
icon 값은 스키마의 enum 중에서 고릅니다.

# 출력 메타
- shorts_title: 60자 이내, 해시태그 없이. shorts_title_candidates: 대안 3개. youtube_description: 3~5줄(링크·해시태그 제외). youtube_tags: 8~15개.
"""


# ── editorial context ─────────────────────────────────────────

def style_guide() -> str:
    path = EDITORIAL_DIR / "style-guide.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def exemplars(limit: int = 2) -> list[dict[str, str]]:
    """Posts the editor marked `exemplar: true` (newest first) + their Shorts script."""
    out = []
    for post in sorted(POSTS_DIR.glob("*.md"), reverse=True):
        fm, body = read_front_matter(post)
        if not fm.get("exemplar"):
            continue
        shorts = ""
        if fm.get("shorts_spec") and (ROOT / fm["shorts_spec"]).exists():
            spec = load_spec(ROOT / fm["shorts_spec"])
            shorts = yaml.safe_dump({"title": spec["shorts"]["title"], "scenes": spec["shorts"]["scenes"]},
                                    allow_unicode=True, sort_keys=False, width=1000)
        out.append({"title": fm.get("title", post.stem), "body": body.strip(), "shorts": shorts})
        if len(out) >= limit:
            break
    return out


def system_prompt() -> str:
    guide = style_guide()
    return BASE_PROMPT + (f"\n# 편집장 스타일 가이드 (editorial/style-guide.md — 사실성 원칙 다음으로 우선)\n{guide}\n" if guide else "")


def _paper_brief(paper: dict[str, Any], figures: list[dict[str, Any]]) -> str:
    v = paper.get("venue")
    venue = f"{v['venue']}{' ' + v['honor'] if v.get('honor') else ''} ({'워크숍' if v['track'] == 'workshop' else '본 학회'})" if v else "(없음 — 학회 언급 금지)"
    authors = paper["authors"]
    lines = [
        f"- arXiv ID: {paper['arxiv_id']}",
        f"- 제목: {paper['title']}",
        f"- 저자: {', '.join(authors[:8])}{f' 외 {len(authors) - 8}명' if len(authors) > 8 else ''}",
        f"- 소속(HF 표기): {paper.get('organization') or '(정보 없음 — PDF 첫 페이지 참고)'}",
        f"- 최초 공개일: {paper['published']}",
        f"- venue: {venue}",
        f"- arXiv comment: {paper.get('comment') or '(없음)'}",
    ]
    if paper.get("upvotes"):
        lines.append(f"- Hugging Face Daily Papers 업보트: {paper['upvotes']}")
    lines.append("- 쇼츠에 쓸 수 있는 논문 그림: " + (", ".join(f"{f['id']} ({f['width']}x{f['height']})" for f in figures) or "(없음 — figure 장면 금지)"))
    return "\n".join(lines)


def _image_block(path: str) -> dict[str, Any]:
    from PIL import Image

    im = Image.open(path).convert("RGB")
    if max(im.size) > 1400:
        s = 1400 / max(im.size)
        im = im.resize((round(im.width * s), round(im.height * s)))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                        "data": base64.standard_b64encode(buf.getvalue()).decode()}}


# ── Claude call ───────────────────────────────────────────────

def generate_content(paper: dict[str, Any], pdf_path: Path, figures: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Call Claude with the full PDF (+ figures, style guide, exemplars) and return the structured content."""
    import anthropic

    cfg = load_config()["claude"]
    client = anthropic.Anthropic()
    figures = figures or []

    pdf_bytes = pdf_path.read_bytes()
    if len(pdf_bytes) <= 20 * 1024 * 1024:  # base64 grows 4/3 → stays under the 32 MB request limit
        doc_block = {"type": "document", "title": paper["title"],
                     "source": {"type": "base64", "media_type": "application/pdf",
                                "data": base64.standard_b64encode(pdf_bytes).decode()}}
    else:  # very large PDFs (huge figures) → send the extracted text instead
        text = pdf_text(pdf_path)
        if not text.strip():
            raise RuntimeError("PDF가 너무 크고 텍스트 추출도 실패했습니다.")
        doc_block = {"type": "document", "title": paper["title"],
                     "source": {"type": "text", "media_type": "text/plain", "data": text}}

    content: list[dict[str, Any]] = []
    ex = exemplars()
    if ex:
        parts = ["# 편집장이 승인한 예시 (톤·구성·시각화 방식의 기준. 내용은 베끼지 말 것)"]
        for i, e in enumerate(ex, 1):
            parts.append(f"\n## 예시 {i}: {e['title']}\n### 블로그 본문\n{e['body']}\n### 쇼츠 대본(YAML)\n{e['shorts']}")
        content.append({"type": "text", "text": "\n".join(parts)})
    for f in figures[:8]:
        content.append({"type": "text", "text": f"[{f['id']}] {f['caption'][:300]}"})
        content.append(_image_block(f["file"]))
    content.append(doc_block)
    content.append({"type": "text", "text": "첨부한 논문으로 블로그 리뷰와 시각화 중심 쇼츠 대본을 작성해 주세요.\n\n"
                                            f"# 논문 메타데이터\n{_paper_brief(paper, figures)}\n"})

    def call(structured: bool):
        kw: dict[str, Any] = {"effort": cfg["effort"]}
        sys_p = system_prompt()
        if structured:
            kw["format"] = {"type": "json_schema", "schema": OUTPUT_SCHEMA}
        else:
            sys_p += "\n\n# 출력 형식\n아래 JSON 스키마를 따르는 JSON 객체 하나만 출력하세요(코드펜스 없이).\n" + json.dumps(OUTPUT_SCHEMA, ensure_ascii=False)
        with client.beta.messages.stream(
            model=cfg["model"], max_tokens=cfg["max_tokens"],
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            system=sys_p, output_config=kw,
            messages=[{"role": "user", "content": content}],
        ) as stream:
            return stream.get_final_message()

    print(f"[generate] Claude({cfg['model']}, effort={cfg['effort']}) — PDF + 그림 {len(figures)}개 + 예시 {len(ex)}개",
          file=sys.stderr)
    try:
        message = call(structured=True)
    except anthropic.BadRequestError as e:  # e.g. schema too complex for structured outputs → plain JSON
        if "schema" not in str(e).lower():
            raise
        print(f"[generate] 구조화 출력 스키마 거부 → 일반 JSON 모드로 재시도: {e}", file=sys.stderr)
        message = call(structured=False)

    if message.stop_reason == "refusal":
        raise RuntimeError(f"Claude가 요청을 거절했습니다: {getattr(message, 'stop_details', None)}")
    if message.stop_reason == "max_tokens":
        raise RuntimeError("max_tokens에 도달해 출력이 잘렸습니다. config.yml의 claude.max_tokens를 늘려주세요.")
    text = next(b.text for b in message.content if b.type == "text").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    u = message.usage
    print(f"[generate] done: in={u.input_tokens} out={u.output_tokens} tokens (message {message.id})", file=sys.stderr)
    return json.loads(text)


# ── validation / normalization ─────────────────────────────────

_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")


def _clamp_box(b: dict[str, Any] | None, full: bool) -> dict[str, float]:
    b = b or {}
    vals = {k: min(1.0, max(0.0, float(b.get(k) or 0))) for k in ("x", "y", "w", "h")}
    if full and (vals["w"] <= 0 or vals["h"] <= 0):
        return {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}
    return vals


def normalize_content(c: dict[str, Any], figures: list[dict[str, Any]] | None = None) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    fig_ids = {f["id"] for f in (figures or [])}
    scenes = c["scenes"]
    for i, s in enumerate(scenes):
        s["headline"] = _EMOJI_RE.sub("", s.get("headline", "")).replace("\\n", "\n").strip()
        s["narration"] = _EMOJI_RE.sub("", s["narration"]).strip()
        v = s.get("visual") or {}
        if v.get("type") not in VISUAL_TYPES:
            warnings.append(f"장면 {i + 1}: 알 수 없는 visual.type '{v.get('type')}' → title로 대체")
            v = {"type": "title", "icon": "sparkles", "subtext": ""}
        if v["type"] == "figure":
            if v.get("figure_id") not in fig_ids:
                warnings.append(f"장면 {i + 1}: 없는 그림 '{v.get('figure_id')}' → title로 대체")
                v = {"type": "title", "icon": "image", "subtext": v.get("caption", "")}
            else:
                v["crop"] = _clamp_box(v.get("crop"), full=True)
                v["focus"] = _clamp_box(v.get("focus"), full=False)
                v["highlights"] = [dict(_clamp_box(h, full=False), label=h.get("label", "")) for h in v.get("highlights", [])][:2]
        s["visual"] = v
    types = [s["visual"]["type"] for s in scenes]
    if not (5 <= len(scenes) <= 9):
        warnings.append(f"장면 수가 {len(scenes)}개입니다 (권장 6~8).")
    if types and types[-1] != "cta":
        warnings.append("마지막 장면이 cta가 아닙니다.")
    if any(a == b for a, b in zip(types, types[1:])):
        warnings.append("같은 visual.type이 연속으로 쓰였습니다.")
    if fig_ids and "figure" not in types:
        warnings.append("논문 그림(figure) 장면이 없습니다.")
    total = sum(len(s["narration"]) for s in scenes)
    if not (220 <= total <= 350):
        warnings.append(f"내레이션 총 {total}자 (권장 260~320자).")
    c["shorts_title"] = re.sub(r"#shorts", "", c["shorts_title"], flags=re.I).strip()
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


def write_outputs(paper: dict[str, Any], content: dict[str, Any], *, date=None,
                  figures: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Write the Jekyll post and the Shorts spec (YAML), plus untouched copies in editorial/drafts/."""
    cfg = load_config()
    date = date or now_kst()
    slug = slugify(paper["title"])
    stem = f"{date:%Y-%m-%d}-{slug}"
    post_path = POSTS_DIR / f"{stem}.md"
    spec_path = spec_path_for(stem)
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
        "visibility": cfg["site"].get("default_visibility", "unlisted"),
        "exemplar": False,
        "image": f"/assets/shorts/{stem}-thumb.jpg",
        "shorts_spec": f"shorts/{stem}.yml",
        "youtube_id": "",
    }
    from .figures import embed_figures

    body, fig_files = embed_figures(content["blog_body_markdown"].strip(), paper["arxiv_id"], figures or [], ROOT / "assets")
    footer = ("\n\n---\n\n<small>이 리뷰는 AI(Claude)가 논문 원문을 분석해 초안을 작성하고, "
              f"작성자({cfg['site']['author']})가 검토·승인한 뒤 게시되었습니다. 수치와 표현은 반드시 원문으로 확인하세요.</small>\n")
    POSTS_DIR.mkdir(exist_ok=True)
    post_path.write_text(
        "---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000) + "---\n\n"
        + _post_header(paper) + "\n\n---\n\n" + body + footer,
        encoding="utf-8",
    )

    spec = {
        "version": 2,
        "stem": stem,
        "slug": slug,
        "post": str(post_path.relative_to(ROOT)),
        "blog_url": blog_url,
        "blog_title": content["blog_title"].split("]")[-1].strip() if "]" in content["blog_title"] else content["blog_title"],
        "exemplar": False,
        "paper": {k: paper.get(k) for k in (
            "arxiv_id", "title", "authors", "published", "organization", "venue", "upvotes",
            "abs_url", "pdf_url", "hf_url", "project_page")},
        "shorts": {
            "title": content["shorts_title"],
            "title_candidates": content["shorts_title_candidates"],
            "description": content["youtube_description"],
            "tags": content["youtube_tags"],
            "scenes": [{"headline": s["headline"], "narration": s["narration"], "visual": s["visual"], "memo": s.get("memo", "")}
                       for s in content["scenes"]],
        },
        "facts": content["facts"],
        "youtube": {"skip": False, "video_id": "", "url": "", "uploaded_at": ""},
        "generated_at": date.isoformat(timespec="seconds"),
    }
    save_spec(spec_path, spec)
    save_drafts(stem, post_path, spec_path)
    spec["_spec_path"] = str(spec_path)
    spec["_assets"] = [str(f.relative_to(ROOT)) for f in fig_files]
    return spec


def save_drafts(stem: str, post_path: Path, spec_path: Path) -> None:
    """Keep the untouched AI output; `python -m pipeline.learn` diffs it against the editor's final version."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(post_path, DRAFTS_DIR / f"{stem}.post.md")
    shutil.copyfile(spec_path, DRAFTS_DIR / f"{stem}.shorts.yml")


def enrich_paper(paper: dict[str, Any], extra: dict[str, Any] | None) -> dict[str, Any]:
    """Merge discovery info (HF upvotes, organization, project page) into arXiv metadata."""
    if extra:
        for k in ("upvotes", "organization", "project_page", "hf_url"):
            if extra.get(k) and not paper.get(k):
                paper[k] = extra[k]
    paper.setdefault("hf_url", f"https://huggingface.co/papers/{paper['arxiv_id']}")
    return paper


def main() -> None:
    from .figures import fetch_figures

    ap = argparse.ArgumentParser(description="Generate a blog review + visual Shorts script with Claude")
    ap.add_argument("--arxiv-id", required=True)
    ap.add_argument("--content-json", help="use this content JSON instead of calling Claude")
    ap.add_argument("--extra-json", help="discovery info JSON (upvotes, organization, ...)")
    args = ap.parse_args()

    paper = fetch_paper(normalize_arxiv_id(args.arxiv_id))
    extra = json.loads(Path(args.extra_json).read_text()) if args.extra_json else None
    paper = enrich_paper(paper, extra)
    work = BUILD_DIR / paper["arxiv_id"]
    pdf = download_pdf(paper, work)
    figures = fetch_figures(paper["arxiv_id"], work / "figs", pdf_path=pdf)

    if args.content_json:
        content = json.loads(Path(args.content_json).read_text(encoding="utf-8"))
    else:
        content = generate_content(paper, pdf, figures)
        (work / "content.json").write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    content, warnings = normalize_content(content, figures)
    for w in warnings:
        print(f"[warn] {w}", file=sys.stderr)
    spec = write_outputs(paper, content, figures=figures)
    print(json.dumps({"spec": spec["_spec_path"], "post": spec["post"], "warnings": warnings}, ensure_ascii=False))


if __name__ == "__main__":
    main()
