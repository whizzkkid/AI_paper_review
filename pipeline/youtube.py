#!/usr/bin/env python3
"""YouTube Data API v3 upload + one-time OAuth helper.

One-time setup on your own computer (opens a browser):
    pip install google-auth-oauthlib
    python -m pipeline.youtube auth --client-secrets client_secret.json
→ prints YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN to store as GitHub secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"


def have_credentials() -> bool:
    return all(os.environ.get(k) for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"))


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _clean(text: str) -> str:
    return re.sub(r"[<>]", "", text)  # YouTube rejects angle brackets in title/description


def build_metadata(spec: dict[str, Any], ycfg: dict[str, Any], description: str) -> dict[str, Any]:
    title = _clean(spec["shorts"]["title"]).strip()
    suffix = " #Shorts"
    title = title[: 100 - len(suffix)].rstrip() + suffix
    tags: list[str] = []
    total = 0
    for t in spec["shorts"].get("tags", []):
        t = _clean(t).strip()
        cost = len(t) + (2 if " " in t else 0) + 1
        if t and total + cost <= 480:
            tags.append(t)
            total += cost
    return {
        "snippet": {
            "title": title,
            "description": _clean(description)[:4900],
            "tags": tags,
            "categoryId": str(ycfg.get("category_id", "28")),
            "defaultLanguage": ycfg.get("default_language", "ko"),
            "defaultAudioLanguage": ycfg.get("default_language", "ko"),
        },
        "status": {
            "privacyStatus": ycfg.get("privacy", "public"),
            "selfDeclaredMadeForKids": bool(ycfg.get("made_for_kids", False)),
            "containsSyntheticMedia": bool(ycfg.get("contains_synthetic_media", True)),
            "embeddable": True,
        },
    }


def upload(video_path: Path, body: dict[str, Any]) -> str:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    yt = _service()
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    retries = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                print(f"[youtube] uploading {int(status.progress() * 100)}%", file=sys.stderr)
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and retries < 5:
                retries += 1
                time.sleep(2 ** retries)
                continue
            raise
    return response["id"]


def auth(client_secrets: str) -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    info = json.loads(Path(client_secrets).read_text())
    client = info.get("installed") or info.get("web") or {}
    print("\n아래 3개 값을 GitHub 저장소 Settings → Secrets and variables → Actions 에 등록하세요:\n")
    print(f"YOUTUBE_CLIENT_ID={client.get('client_id')}")
    print(f"YOUTUBE_CLIENT_SECRET={client.get('client_secret')}")
    print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")


def main() -> None:
    ap = argparse.ArgumentParser(description="YouTube helper")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("auth", help="get a refresh token (run locally once)")
    a.add_argument("--client-secrets", default="client_secret.json")
    args = ap.parse_args()
    if args.cmd == "auth":
        auth(args.client_secrets)


if __name__ == "__main__":
    main()
