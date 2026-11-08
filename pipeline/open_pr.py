#!/usr/bin/env python3
"""Turn build/manifest.json into one review PR per paper — the "notify me before deploying" gate.

Each PR is assigned to the repo owner (GitHub notifies by email / mobile app) and contains the
post, the Shorts script, a contact sheet preview and a fact-check list. Merging = approval.

    python -m pipeline.open_pr build/manifest.json --assignee <내 GitHub ID>
Requires the `gh` CLI with GH_TOKEN, and the repo setting
"Allow GitHub Actions to create and approve pull requests".
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from .common import DRAFTS_DIR, ROOT, load_config, load_spec

LABEL = "needs-approval"


def sh(*cmd: str, check: bool = True) -> str:
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed:\n{res.stdout}\n{res.stderr}")
    return res.stdout.strip()


def pr_body(entry: dict, spec: dict, branch: str, repo: str, run_url: str) -> str:
    p = spec["paper"]
    cfg = load_config()
    v = p.get("venue")
    pick = entry.get("pick", {})
    if pick.get("source") == "queue":
        reason = "`pipeline/queue.yml` 수동 큐"
    elif pick.get("source") == "manual":
        reason = "수동 실행 (arXiv ID 지정)"
    else:
        reason = (f"Hugging Face Daily Papers 업보트 **{pick.get('upvotes', 0)}**"
                  + (f" × 학회 채택({v['venue']}) 가중치" if v else "") + f" → 점수 {pick.get('score', 0):.0f}")
    raw = f"https://github.com/{repo}/blob/{branch}"
    stem = entry["stem"]
    duration = (entry.get("video") or {}).get("duration")
    lines = [
        "## 🆕 새 논문 리뷰 초안 — 배포 승인 요청",
        "",
        f"**{p['title']}**",
        "",
        f"- 📄 [arXiv:{p['arxiv_id']}]({p['abs_url']}) · [PDF]({p['pdf_url']})"
        + (f" · [Hugging Face]({p['hf_url']})" if p.get("hf_url") else ""),
        f"- 🏛️ 학회: **{v['venue']}**" + (f" ({v['honor']})" if v and v.get("honor") else "") if v else "- 🏛️ 학회: 표기 없음 (arXiv 프리프린트)",
        f"- 🏢 소속: {p.get('organization') or '—'}",
        f"- 🔥 선정 이유: {reason}",
        "",
        "### 🎬 쇼츠 미리보기",
        "",
        f"**{spec['shorts']['title']} #Shorts**" + (f" · {duration:.0f}초" if duration else ""),
        "",
        f'<img src="{raw}/assets/shorts/{stem}-sheet.jpg?raw=true" width="720" alt="scene contact sheet">',
        "",
        f"▶️ **영상(mp4) 확인**: [이 실행의 Artifacts → `shorts-preview`]({run_url}#artifacts)",
        f"📜 쇼츠 대본(수정 가능): [`{entry['spec']}`]({raw}/{entry['spec']})",
        "",
        "### 📝 블로그 포스트",
        "",
        f"- 파일: [`{spec['post']}`]({raw}/{spec['post']}) (Files changed 탭에서 바로 읽고 수정 가능)",
        f"- 게시 후 주소: {spec['blog_url']}",
        "",
        "### ✅ 사실 확인 체크리스트 (Claude가 논문 원문에서 인용)",
        "",
    ]
    for f in spec.get("facts", []):
        lines.append(f"- [ ] **{f['claim']}** — “{f['evidence_quote']}” *({f['location']})*")
    if entry.get("warnings"):
        lines += ["", "### ⚠️ 자동 점검 경고", ""] + [f"- {w}" for w in entry["warnings"]]
    privacy = cfg["youtube"]["privacy"]
    lines += [
        "",
        "---",
        "",
        "### 🚀 이 PR을 Merge하면 (= 배포 승인)",
        "",
        f"1. 블로그 포스트가 GitHub Pages에 게시됩니다 → {spec['blog_url']}",
        f"2. `publish` 워크플로가 **머지된 대본으로** 영상을 다시 렌더링해 YouTube에 업로드합니다 (공개 범위: `{privacy}`).",
        "",
        "- ✏️ 수정이 필요하면 이 브랜치에서 `_posts/…md`(글)나 `shorts/…yml`(내레이션·화면 문구·시각화)을 고친 뒤 머지하세요.",
        "  고친 내용은 `editorial/drafts/`의 AI 초안과 비교되어 `python -m pipeline.learn`으로 스타일 가이드에 반영됩니다.",
        "- 🙅 거절하려면 PR을 닫고, 다시 추천되지 않도록 `pipeline/queue.yml`의 `skip:`에 "
        f"`\"{p['arxiv_id']}\"`를 추가하세요.",
        "",
        "<sub>🤖 AI Paper Review 자동화 파이프라인이 생성했습니다. 머지 전까지는 아무것도 공개되지 않습니다.</sub>",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Open approval PRs for generated reviews")
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--assignee", default="")
    ap.add_argument("--base", default="main")
    args = ap.parse_args()

    repo = os.environ.get("GITHUB_REPOSITORY") or sh("gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    run_url = os.environ.get("RUN_URL", f"https://github.com/{repo}/actions")
    entries = json.loads(args.manifest.read_text(encoding="utf-8"))
    start = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    sh("gh", "label", "create", LABEL, "--color", "FBCA04", "--description", "배포 전 승인 필요", "--force", check=False)

    for entry in entries:
        spec = load_spec(ROOT / entry["spec"])
        stem = entry["stem"]
        branch = f"auto/review-{entry['arxiv_id']}"
        if sh("git", "ls-remote", "--heads", "origin", branch):
            branch = f"{branch}-{stem[:10]}"
        files = [entry["post"], entry["spec"], f"assets/shorts/{stem}-thumb.jpg", f"assets/shorts/{stem}-sheet.jpg",
                 str((DRAFTS_DIR / f"{stem}.post.md").relative_to(ROOT)), str((DRAFTS_DIR / f"{stem}.shorts.yml").relative_to(ROOT))]
        files += entry.get("assets", [])
        files = [f for f in files if (ROOT / f).exists()]

        sh("git", "switch", "-c", branch)
        sh("git", "add", "--", *files)
        sh("git", "commit", "-m", f"review: {entry['title'][:60]} (arXiv:{entry['arxiv_id']})")
        sh("git", "push", "-u", "origin", branch)

        body_path = ROOT / "build" / f"pr-{stem}.md"
        body_path.write_text(pr_body(entry, spec, branch, repo, run_url), encoding="utf-8")
        cmd = ["gh", "pr", "create", "--base", args.base, "--head", branch,
               "--title", f"[리뷰 승인 요청] {spec['shorts']['title']}", "--body-file", str(body_path),
               "--label", LABEL]
        if args.assignee:
            cmd += ["--assignee", args.assignee]
        try:
            url = sh(*cmd)
        except Exception:
            if not args.assignee:
                raise
            # an organization (or a bot) cannot be an assignee — open the PR without one
            url = sh(*[c for c in cmd if c not in ("--assignee", args.assignee)])
        print(f"[open_pr] {url}")
        sh("git", "switch", start)


if __name__ == "__main__":
    main()
