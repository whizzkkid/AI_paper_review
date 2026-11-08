"""Text-to-speech providers. Each returns the audio path plus optional word timings.

  edge    free Microsoft Edge neural voices via the `edge-tts` package (no key)
  gcloud  Google Cloud Text-to-Speech REST API (env GOOGLE_TTS_API_KEY)
  silent  silence with an estimated duration (for layout tests without network)
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import ssl
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

Word = tuple[float, float, str]  # (start_sec, end_sec, text)


def synthesize(text: str, out_path: Path, vcfg: dict[str, Any]) -> tuple[Path, list[Word] | None]:
    provider = vcfg.get("tts", "edge")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if provider == "edge":
        return _edge(text, out_path, vcfg["voice"], vcfg.get("rate", "+0%"))
    if provider == "gcloud":
        return _gcloud(text, out_path, vcfg.get("gcloud_voice", "ko-KR-Chirp3-HD-Charon"), vcfg.get("rate", "+0%"))
    if provider == "silent":
        return _silent(text, out_path)
    raise ValueError(f"unknown tts provider: {provider}")


def _edge(text: str, out_path: Path, voice: str, rate: str) -> tuple[Path, list[Word]]:
    import edge_tts
    import edge_tts.communicate as comm_mod

    # edge-tts pins certifi; honour SSL_CERT_FILE so it also works behind TLS-inspecting proxies.
    ca = os.environ.get("SSL_CERT_FILE")
    if ca and os.path.exists(ca) and hasattr(comm_mod, "_SSL_CTX"):
        comm_mod._SSL_CTX = ssl.create_default_context(cafile=ca)

    async def run() -> list[Word]:
        communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
        words: list[Word] = []
        with open(out_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7
                    words.append((start, start + chunk["duration"] / 1e7, chunk["text"]))
        return words

    last: Exception | None = None
    for attempt in range(4):
        try:
            words = asyncio.run(run())
            if out_path.stat().st_size > 0:
                return out_path, words
        except Exception as e:  # network hiccups are common; retry
            last = e
        time.sleep(2 * (2 ** attempt))
    raise RuntimeError(f"edge-tts failed: {last}")


def _gcloud(text: str, out_path: Path, voice: str, rate: str) -> tuple[Path, None]:
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_TTS_API_KEY 환경 변수가 필요합니다.")
    speaking_rate = 1.0 + float(rate.rstrip("%")) / 100  # "+12%" -> 1.12
    body = json.dumps({
        "input": {"text": text},
        "voice": {"languageCode": "ko-KR", "name": voice},
        "audioConfig": {"audioEncoding": "MP3", "speakingRate": round(speaking_rate, 2)},
    }).encode()
    req = urllib.request.Request(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        data=body, headers={"Content-Type": "application/json", "X-Goog-Api-Key": key},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        audio = base64.b64decode(json.loads(resp.read())["audioContent"])
    out_path.write_bytes(audio)
    return out_path, None


def _silent(text: str, out_path: Path) -> tuple[Path, None]:
    seconds = max(1.5, len(text.replace(" ", "")) / 6.0)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
         "-t", f"{seconds:.2f}", "-q:a", "9", str(out_path)],
        check=True,
    )
    return out_path, None
