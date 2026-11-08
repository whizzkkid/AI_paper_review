#!/usr/bin/env python3
"""AI-generated B-roll clips for `broll` scenes (Higgsfield).

A `broll` scene carries an English `prompt` for a short, metaphorical, vertical clip that plays
full-bleed behind the headline (never a depiction of the paper's actual results). Clips are stored
in the repo under media/broll/<stem>/ and referenced by `visual.file`, so the review PR shows the
exact clip and the post-merge publish re-render reuses it instead of paying to regenerate.

Two ways to get a clip:
  • automation — Higgsfield API (pip higgsfield-client, env HF_KEY="key:secret"), config broll.enabled
  • interactive — in a Claude session with the Higgsfield MCP connector, generate the clip there,
    save it under media/broll/<stem>/ and set `file:` in the YAML; this module then just uses it.

    python -m pipeline.broll shorts/<stem>.yml          # generate missing clips (needs HF_KEY)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from .common import ROOT, http_get, load_config, load_spec, save_spec

MEDIA_DIR = ROOT / "media" / "broll"
NEGATIVE = "text, letters, captions, subtitles, logo, watermark, brand, real person, celebrity, chart, graph, UI screenshot"


def have_credentials() -> bool:
    return bool(os.environ.get("HF_KEY") or (os.environ.get("HF_API_KEY") and os.environ.get("HF_API_SECRET")))


def generate_clip(prompt: str, out_mp4: Path, bcfg: dict[str, Any]) -> Path:
    """Text-to-video via the Higgsfield API, then a small 720x1280 H.264 copy for the repo."""
    import higgsfield_client

    result = higgsfield_client.subscribe(
        bcfg.get("model", "wan/v2.7/text-to-video"),
        arguments={
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "duration": int(bcfg.get("duration", 6)),
            "resolution": bcfg.get("resolution", "720p"),
            "negative_prompt": NEGATIVE,
        },
    )
    url = (result.get("video") or {}).get("url")
    if not url:
        raise RuntimeError(f"Higgsfield 결과에 영상 URL이 없습니다: {result}")
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.mp4"
        raw.write_bytes(http_get(url, timeout=300))
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-an",
             "-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=30",
             "-c:v", "libx264", "-preset", "slow", "-crf", "28", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
             str(out_mp4)],
            check=True,
        )
    return out_mp4


def ensure_broll(spec_path: Path) -> list[Path]:
    """Generate clips for broll scenes that have no `file` yet; returns the new files (to commit)."""
    cfg = load_config().get("broll", {})
    spec = load_spec(spec_path)
    stem = spec["stem"]
    pending = [(i, s) for i, s in enumerate(spec["shorts"]["scenes"])
               if (s.get("visual") or {}).get("type") == "broll"
               and not (s["visual"].get("file") and (ROOT / s["visual"]["file"]).exists())]
    if not pending:
        return []
    if not cfg.get("enabled") or not have_credentials():
        why = "broll.enabled가 false" if not cfg.get("enabled") else "HF_KEY가 없음"
        print(f"[broll] {why} → {len(pending)}개 장면은 대체 화면으로 렌더링됩니다.", file=sys.stderr)
        return []
    created: list[Path] = []
    for i, s in pending[: int(cfg.get("max_per_short", 2))]:
        out = MEDIA_DIR / stem / f"scene{i + 1:02d}.mp4"
        print(f"[broll] 장면 {i + 1} 생성 중: {s['visual'].get('prompt', '')[:80]}", file=sys.stderr)
        try:
            generate_clip(s["visual"]["prompt"], out, cfg)
        except Exception as e:  # a failed clip must not block the review PR
            print(f"[broll] 장면 {i + 1} 생성 실패 → 대체 화면 사용: {e}", file=sys.stderr)
            continue
        s["visual"]["file"] = str(out.relative_to(ROOT))
        created.append(out)
    save_spec(spec_path, spec)
    return created


def extract_frames(mp4: Path, out_dir: Path, fps: int) -> int:
    """Decode a clip into JPEG frames the HTML stage can step through deterministically."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        old.unlink()
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp4), "-vf", f"fps={fps}", "-q:v", "3",
                    str(out_dir / "%04d.jpg")], check=True)
    return len(list(out_dir.glob("*.jpg")))


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate AI B-roll clips for a Shorts script")
    ap.add_argument("spec", type=Path)
    args = ap.parse_args()
    for f in ensure_broll(args.spec):
        print(f.relative_to(ROOT))


if __name__ == "__main__":
    main()
