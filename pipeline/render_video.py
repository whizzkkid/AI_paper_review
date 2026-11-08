#!/usr/bin/env python3
"""Render a visual-first YouTube Short (1080x1920) from a shorts spec (shorts/<stem>.yml).

Every scene is a motion-graphic built in HTML/SVG (pipeline/video/stage.html): animated charts,
chat re-enactments, diagrams, the paper's own figures with zoom + highlights, karaoke captions.
Playwright captures the stage frame by frame; ffmpeg muxes it with the TTS narration.

    python -m pipeline.render_video shorts/2026-11-08-some-paper.yml [--fast]

Outputs
  build/<stem>/<stem>.mp4               the video (not committed; uploaded on publish)
  assets/shorts/<stem>-thumb.jpg        cover frame (blog og:image, PR preview)
  assets/shorts/<stem>-sheet.jpg        contact sheet of every scene (PR preview)
  build/<stem>/script.md                timeline with real timings (PR / review)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import wave
from pathlib import Path
from typing import Any

from PIL import Image

from .common import ASSETS_SHORTS_DIR, BUILD_DIR, FONTS_DIR, ROOT, http_get, load_config, load_spec
from .tts import Word, synthesize

STAGE = ROOT / "pipeline" / "video" / "stage.html"
LEAD, GAP, TAIL = 0.30, 0.35, 1.40   # seconds of silence: start, between scenes, end
SAMPLE_RATE = 48000

PRETENDARD = ["Pretendard-Medium.otf", "Pretendard-SemiBold.otf", "Pretendard-Bold.otf",
              "Pretendard-ExtraBold.otf", "Pretendard-Black.otf"]
PRETENDARD_URL = "https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/public/static/{}"


def ensure_fonts() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    for name in PRETENDARD:
        path = FONTS_DIR / name
        if path.exists() and path.stat().st_size > 100_000:
            continue
        try:
            path.write_bytes(http_get(PRETENDARD_URL.format(name), timeout=60))
        except Exception as e:
            print(f"[warn] Pretendard 다운로드 실패({name}): {e} — 시스템 폰트로 대체", file=sys.stderr)


# ── captions (karaoke: word-level timing) ─────────────────────

def chunk_caption(text: str, max_chars: int = 16) -> list[str]:
    clauses = [c.strip() for c in re.split(r"(?<=[.?!,])\s+", text.strip()) if c.strip()]
    chunks: list[str] = []
    for clause in clauses:
        cur = ""
        for wd in clause.split():
            cand = f"{cur} {wd}".strip()
            if cur and len(cand) > max_chars:
                chunks.append(cur)
                cur = wd
            else:
                cur = cand
        if cur:
            chunks.append(cur)
    out: list[str] = []
    for c in chunks:  # merge a dangling short tail into the previous chunk
        if out and len(c) <= 3 and len(out[-1]) + len(c) + 1 <= max_chars + 4:
            out[-1] = f"{out[-1]} {c}"
        else:
            out.append(c)
    return [re.sub(r"[.,]$", "", c) for c in out]


def _norm(s: str) -> str:
    return re.sub(r"[^\w]", "", s)


def char_timer(narration: str, words: list[Word] | None, dur: float):
    """Map a character position in the narration (spaces/punctuation ignored) to seconds."""
    total = len(_norm(narration)) or 1
    if words:
        pts, pos = [(0, words[0][0])], 0
        for s, e, t in words:
            pts.append((pos, s))
            pos += len(_norm(t))
            pts.append((pos, e))
        if abs(pos - total) / total < 0.25:
            def at(c: float) -> float:
                for (c0, t0), (c1, t1) in zip(pts, pts[1:]):
                    if c0 <= c <= c1:
                        return t0 if c1 == c0 else t0 + (t1 - t0) * (c - c0) / (c1 - c0)
                return pts[-1][1]
            return at
    return lambda c: dur * c / total


def build_captions(scenes, raw, timeline, ends, tempo) -> list[dict[str, Any]]:
    caps = []
    for i, s in enumerate(scenes):
        n0, n1 = timeline[i]
        words = [(a / tempo, b / tempo, x) for a, b, x in (raw[i][1] or [])] or None
        at = char_timer(s["narration"], words, n1 - n0)
        chunks = chunk_caption(s["narration"])
        pos, starts, cw = 0, [], []
        for c in chunks:
            ws = []
            for w in c.split():
                ws.append({"t": round(n0 + max(0.0, at(pos) - 0.04), 3), "text": w})
                pos += len(_norm(w))
            starts.append(ws[0]["t"])
            cw.append(ws)
        for j, ws in enumerate(cw):
            end = starts[j + 1] if j + 1 < len(cw) else min(ends[i], n1 + 0.45)
            caps.append({"start": starts[j], "end": end, "words": ws})
    return caps


# ── audio ────────────────────────────────────────────────────

def tts_cached(text: str, out: Path, vcfg: dict[str, Any]):
    """Re-use narration audio when the text/voice did not change (fast re-renders after small edits)."""
    key = json.dumps([vcfg.get("tts"), vcfg.get("voice"), vcfg.get("gcloud_voice"), vcfg.get("rate"), text], ensure_ascii=False)
    meta = out.with_suffix(".json")
    if out.exists() and meta.exists():
        m = json.loads(meta.read_text(encoding="utf-8"))
        if m.get("key") == key:
            return out, [tuple(w) for w in m["words"]] if m.get("words") is not None else None
    path, words = synthesize(text, out, vcfg)
    meta.write_text(json.dumps({"key": key, "words": words}, ensure_ascii=False), encoding="utf-8")
    return path, words


def decode_pcm(path: Path, tempo: float = 1.0) -> bytes:
    cmd = ["ffmpeg", "-loglevel", "error", "-i", str(path)]
    if abs(tempo - 1.0) > 1e-3:
        cmd += ["-af", f"atempo={tempo:.4f}"]
    cmd += ["-ar", str(SAMPLE_RATE), "-ac", "1", "-f", "s16le", "-"]
    return subprocess.run(cmd, check=True, capture_output=True).stdout


def silence(sec: float) -> bytes:
    return b"\x00\x00" * int(round(sec * SAMPLE_RATE))


# ── stage data ───────────────────────────────────────────────

def _uri(p: str | Path) -> str:
    return Path(p).resolve().as_uri()


def stage_data(spec: dict[str, Any], scenes, starts, ends, captions, total, cfg) -> dict[str, Any]:
    from .figures import fetch_figures
    from .paper import download_pdf, render_first_page

    paper = spec["paper"]
    v = paper.get("venue") or None
    types = {(s.get("visual") or {}).get("type") for s in scenes}
    figures: dict[str, Any] = {}
    if "figure" in types:
        for f in fetch_figures(paper["arxiv_id"], BUILD_DIR / paper["arxiv_id"] / "figs"):
            figures[f["id"]] = {"src": _uri(f["file"]), "w": f["width"], "h": f["height"]}
    page = {"venue": (v["venue"] + (f" {v['honor']}" if v.get("honor") else "")) if v else "",
            "orgs": [o.strip() for o in re.split(r"[·,]", paper.get("organization") or "") if o.strip()]}
    if "paper" in types:
        try:
            pdf = download_pdf(paper, BUILD_DIR / paper["arxiv_id"])
            png = render_first_page(pdf, BUILD_DIR / paper["arxiv_id"] / "page1.png", dpi=150)
            if png:
                im = Image.open(png)
                top = im.crop((0, 0, im.width, int(im.height * 0.55)))
                top_path = png.with_name("page1_top.png")
                top.save(top_path)
                page.update(page1=_uri(top_path), page1_w=top.width, page1_h=top.height)
        except Exception as e:
            print(f"[warn] 논문 첫 페이지 렌더 실패: {e}", file=sys.stderr)
    badge = page["venue"] or "HOT PAPER"
    ref = f"arXiv {paper['arxiv_id']}" + (f"  ·  {paper['organization']}" if paper.get("organization") else "")
    blog = spec["blog_url"].replace("https://", "").rstrip("/")
    return {
        "total": total,
        "channel": cfg["site"]["channel_name"],
        "badge": badge, "badge_soft": not v,
        "ref": ref,
        "blog_url_short": re.sub(r"/posts/.*$", "", blog),
        "blog_title": spec.get("blog_title") or spec["shorts"]["title"],
        "paper": page,
        "figures": figures,
        "scenes": [{"start": starts[i], "end": ends[i], "headline": s.get("headline", ""), "visual": s.get("visual") or {}}
                   for i, s in enumerate(scenes)],
        "captions": captions,
    }


# ── main render ──────────────────────────────────────────────

def render(spec_path: Path, fast: bool = False, sheet_only: bool = False) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    cfg = load_config()
    vcfg = cfg["video"]
    W, H, FPS = vcfg["width"], vcfg["height"], vcfg["fps"]
    spec = load_spec(spec_path)
    stem = spec["stem"]
    scenes = spec["shorts"]["scenes"]
    work = BUILD_DIR / stem
    (work / "audio").mkdir(parents=True, exist_ok=True)
    ensure_fonts()

    # 1) narration audio per scene (auto speed-up to fit max_seconds)
    print(f"[render] TTS ({vcfg['tts']}) for {len(scenes)} scenes...", file=sys.stderr)
    raw = [tts_cached(s["narration"], work / "audio" / f"{i:02d}.mp3", vcfg) for i, s in enumerate(scenes)]
    pcm = [decode_pcm(p) for p, _ in raw]
    speech = sum(len(b) / 2 / SAMPLE_RATE for b in pcm)
    fixed = LEAD + GAP * (len(scenes) - 1) + TAIL
    tempo = 1.0
    if speech + fixed > vcfg["max_seconds"]:
        tempo = min(1.25, speech / max(1.0, vcfg["max_seconds"] - fixed))
        print(f"[render] {speech + fixed:.1f}s > {vcfg['max_seconds']}s → 음성 {tempo:.2f}배속", file=sys.stderr)
        pcm = [decode_pcm(p, tempo) for p, _ in raw]

    # 2) timeline
    audio = bytearray(silence(LEAD))
    timeline, t = [], LEAD
    for i, b in enumerate(pcm):
        d = len(b) / 2 / SAMPLE_RATE
        timeline.append((t, t + d))
        audio += b
        pad = GAP if i < len(pcm) - 1 else TAIL
        audio += silence(pad)
        t += d + pad
    total = t
    voice_wav = work / "voice.wav"
    with wave.open(str(voice_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(bytes(audio))
    starts = [0.0] + [max(0.0, a - 0.2) for a, _ in timeline[1:]]
    ends = starts[1:] + [total]
    captions = build_captions(scenes, raw, timeline, ends, tempo)
    data = stage_data(spec, scenes, starts, ends, captions, total, cfg)
    (work / "stage-data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # 3) frames (Playwright) → ffmpeg
    out_mp4 = work / f"{stem}.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
           "-i", str(voice_wav)]
    bgm = (vcfg.get("bgm") or "").strip()
    voice_chain = "[1:a]loudnorm=I=-15:TP=-1.5:LRA=11,aresample=48000[v]"
    if bgm and (ROOT / bgm).exists():
        cmd += ["-stream_loop", "-1", "-i", str(ROOT / bgm)]
        fc = (f"{voice_chain};[2:a]volume={vcfg.get('bgm_volume', 0.07)},"
              f"afade=t=out:st={max(0.0, total - 1.5):.2f}:d=1.5,aresample=48000[b];"
              "[v][b]amix=inputs=2:duration=first:normalize=0[a]")
    else:
        fc = voice_chain.replace("[v]", "[a]")
    cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[a]",
            "-c:v", "libx264", "-preset", "veryfast" if fast else "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.3f}", str(out_mp4)]
    n_frames = int(math.ceil(total * FPS))
    print(f"[render] capturing {n_frames} frames ({total:.1f}s)...", file=sys.stderr)

    ASSETS_SHORTS_DIR.mkdir(parents=True, exist_ok=True)
    thumb = ASSETS_SHORTS_DIR / f"{stem}-thumb.jpg"
    sheet_path = ASSETS_SHORTS_DIR / f"{stem}-sheet.jpg"
    with sync_playwright() as pw:
        exe = os.environ.get("SHORTS_CHROMIUM") or None
        browser = pw.chromium.launch(executable_path=exe)
        page = browser.new_page(viewport={"width": W, "height": H})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(STAGE.as_uri())
        page.evaluate("d => window.setup(d)", data)
        if not sheet_only:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            try:
                for fi in range(n_frames):
                    page.evaluate("t => window.renderAt(t)", fi / FPS)
                    proc.stdin.write(page.screenshot(type="jpeg", quality=92))
            finally:
                proc.stdin.close()
            if proc.wait() != 0:
                raise RuntimeError("ffmpeg 인코딩 실패")
        if errors:
            raise RuntimeError("스테이지 JS 오류: " + " | ".join(errors[:3]))

        # 4) previews: cover + contact sheet
        cover_t = min(ends[0] - 0.05, starts[0] + 2.2)
        page.evaluate("t => window.renderAt(t, {captions: false})", cover_t)
        page.screenshot(path=str(thumb), type="jpeg", quality=88)
        tiles = []
        for i in range(len(scenes)):
            tt = min(ends[i] - 0.05, starts[i] + max(2.4, (ends[i] - starts[i]) * 0.72))
            page.evaluate("t => window.renderAt(t)", tt)
            tile = work / f"tile{i:02d}.jpg"
            page.screenshot(path=str(tile), type="jpeg", quality=88)
            tiles.append(Image.open(tile).resize((270, 480), Image.LANCZOS))
        browser.close()

    cols = min(4, len(tiles))
    rows = math.ceil(len(tiles) / cols)
    sheet = Image.new("RGB", (cols * 270 + (cols + 1) * 12, rows * 480 + (rows + 1) * 12), (30, 34, 40))
    for i, tile in enumerate(tiles):
        sheet.paste(tile, (12 + (i % cols) * 282, 12 + (i // cols) * 492))
    sheet.save(sheet_path, quality=82)

    md_path = work / "script.md"
    md_path.write_text(script_markdown(spec, list(zip(starts, ends)), total, tempo), encoding="utf-8")
    result = {"video": str(out_mp4), "thumb": str(thumb), "sheet": str(sheet_path), "script": str(md_path),
              "duration": round(total, 2), "tempo": round(tempo, 3)}
    print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
    return result


def _ts(sec: float) -> str:
    return f"{int(sec // 60):02d}:{sec % 60:04.1f}"


def script_markdown(spec: dict[str, Any], timings, total: float, tempo: float) -> str:
    sh = spec["shorts"]
    p = spec["paper"]
    venue = p["venue"]["venue"] if p.get("venue") else "—"
    out = [
        f"# 🎬 쇼츠 타임라인 — {p['title']}",
        "",
        f"- **유튜브 제목**: {sh['title']} #Shorts",
        f"- **러닝타임**: {total:.1f}초" + (f" (음성 {tempo:.2f}배속 적용)" if tempo > 1.001 else ""),
        f"- **논문**: [{p['title']}]({p['abs_url']}) · 학회: {venue}",
        "",
        "| 시간 | 시각화 | 화면 문구 | 내레이션 |",
        "|---|---|---|---|",
    ]
    for (a, b), s in zip(timings, sh["scenes"]):
        screen = (s.get("headline") or "").replace("\n", " ").replace("|", "\\|")
        out.append(f"| {_ts(a)}~{_ts(b)} | `{(s.get('visual') or {}).get('type', '-')}` | {screen} | {s['narration']} |")
    return "\n".join(out) + "\n"


def youtube_description(spec: dict[str, Any]) -> str:
    p = spec["paper"]
    venue = p["venue"]["venue"] if p.get("venue") else ""
    tags = ["#Shorts", "#AI", "#논문리뷰", "#인공지능"]
    if venue:
        tags.append("#" + venue.replace(" ", ""))
    return "\n".join([
        spec["shorts"]["description"].strip(),
        "",
        f"📝 블로그 상세 리뷰: {spec['blog_url']}",
        f"📄 논문: {p['title']}" + (f" ({venue})" if venue else ""),
        f"🔗 arXiv: {p['abs_url']}",
        "",
        "※ 이 영상은 AI(Claude)로 논문 원문을 분석해 대본을 만들고, AI 음성으로 낭독했습니다.",
        "",
        " ".join(tags),
    ])


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a YouTube Short from a shorts spec")
    ap.add_argument("spec", type=Path)
    ap.add_argument("--fast", action="store_true", help="faster, slightly larger encode (preview)")
    ap.add_argument("--sheet-only", action="store_true", help="only the scene contact sheet + cover (no video)")
    args = ap.parse_args()
    render(args.spec, fast=args.fast, sheet_only=args.sheet_only)


if __name__ == "__main__":
    main()
