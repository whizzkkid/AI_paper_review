#!/usr/bin/env python3
"""Publish approved Shorts: runs on `main` after a review PR is merged.

For every shorts spec without a YouTube ID (and not marked `"skip": true`):
  1. re-render the video from the *merged* script (so edits made in the PR are respected)
  2. upload it to YouTube
  3. write the video ID back into the spec and the blog post front matter (→ embed on the blog)

    python -m pipeline.publish            # all pending specs
    python -m pipeline.publish --dry-run  # render only, never upload
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import ROOT, list_specs, load_config, load_spec, now_kst, save_spec, set_front_matter_key
from .render_video import render, youtube_description
from .youtube import build_metadata, have_credentials, upload


def pending_specs() -> list[Path]:
    out = []
    for p in list_specs():
        spec = load_spec(p)
        yt = spec.get("youtube", {})
        if not yt.get("video_id") and not yt.get("skip"):
            out.append(p)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Render + upload approved Shorts to YouTube")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--spec", type=Path, help="publish only this spec")
    args = ap.parse_args()

    cfg = load_config()
    if not cfg["youtube"].get("enabled", True) and not args.dry_run:
        print("[publish] config.yml의 youtube.enabled가 false라 업로드를 하지 않습니다. (블로그만 게시)")
        return
    specs = [args.spec] if args.spec else pending_specs()
    if not specs:
        print("[publish] 업로드 대기 중인 쇼츠가 없습니다.")
        return
    can_upload = have_credentials() and not args.dry_run
    if not can_upload and not args.dry_run:
        print("::warning::YouTube 시크릿(YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN)이 없어 업로드를 건너뜁니다. "
              "README의 'YouTube 연결' 절차를 진행한 뒤 Actions에서 publish 워크플로를 다시 실행하세요.")

    failures = 0
    for spec_path in specs:
        spec = load_spec(spec_path)
        post = ROOT / spec["post"]
        if not post.exists():
            print(f"[publish] {spec_path.name}: 블로그 포스트가 없어 건너뜀 ({spec['post']})")
            continue
        print(f"[publish] ▶ {spec['paper']['title']}")
        try:
            result = render(spec_path)
            if not can_upload:
                print(f"[publish] (업로드 생략) 렌더 결과: {result['video']}")
                continue
            body = build_metadata(spec, cfg["youtube"], youtube_description(spec))
            video_id = upload(Path(result["video"]), body)
        except Exception as e:  # keep going with the other specs
            failures += 1
            print(f"::error::{spec_path.name} 업로드 실패: {e}")
            continue
        spec["youtube"].update({
            "video_id": video_id,
            "url": f"https://youtube.com/shorts/{video_id}",
            "uploaded_at": now_kst().isoformat(timespec="seconds"),
            "privacy": body["status"]["privacyStatus"],
        })
        save_spec(spec_path, spec)
        set_front_matter_key(post, "youtube_id", video_id)
        print(f"[publish] ✅ https://youtube.com/shorts/{video_id}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
