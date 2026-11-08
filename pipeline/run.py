#!/usr/bin/env python3
"""One scheduled run: pick hot paper(s) → Claude review → Shorts preview → build/manifest.json.

Nothing here publishes anything. `pipeline.open_pr` turns the manifest into review PRs,
and only merging a PR (your approval) deploys the post and uploads the video.

    python -m pipeline.run                         # auto-pick the hottest new paper
    python -m pipeline.run --arxiv-id 2610.42149   # a specific paper
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import BUILD_DIR, ROOT, normalize_arxiv_id
from .discover import discover
from .figures import fetch_figures
from .generate import enrich_paper, generate_content, normalize_content, write_outputs
from .paper import download_pdf, fetch_paper
from .render_video import render


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate review drafts for approval")
    ap.add_argument("--arxiv-id", default="", help="review this paper instead of auto-discovery")
    ap.add_argument("--exclude", default="", help="comma-separated arXiv IDs to skip (open PRs)")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--no-video", action="store_true")
    args = ap.parse_args()

    if args.arxiv_id.strip():
        picks = [{"arxiv_id": normalize_arxiv_id(args.arxiv_id), "source": "manual"}]
    else:
        exclude = {x.strip() for x in args.exclude.split(",") if x.strip()}
        picks = discover(args.count, exclude)
    if not picks:
        print("[run] 새로 리뷰할 논문이 없습니다.")
        return

    manifest = []
    for pick in picks:
        paper = enrich_paper(fetch_paper(pick["arxiv_id"]), pick)
        print(f"[run] ▶ arXiv:{paper['arxiv_id']} {paper['title']}", file=sys.stderr)
        work = BUILD_DIR / paper["arxiv_id"]
        pdf = download_pdf(paper, work)
        figures = fetch_figures(paper["arxiv_id"], work / "figs")
        content = generate_content(paper, pdf, figures)
        (work / "content.json").write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
        content, warnings = normalize_content(content, figures)
        spec = write_outputs(paper, content, figures=figures)
        spec_path = Path(spec.pop("_spec_path"))
        video = None if args.no_video else render(spec_path)
        manifest.append({
            "arxiv_id": paper["arxiv_id"],
            "title": paper["title"],
            "stem": spec["stem"],
            "spec": str(spec_path.relative_to(ROOT)),
            "post": spec["post"],
            "assets": spec.get("_assets", []),
            "pick": {k: v for k, v in pick.items() if k in ("source", "upvotes", "score", "venue", "hf_date")},
            "warnings": warnings,
            "video": video,
        })

    BUILD_DIR.mkdir(exist_ok=True)
    (BUILD_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[run] manifest: {BUILD_DIR / 'manifest.json'} ({len(manifest)} paper(s))")


if __name__ == "__main__":
    main()
