"""Find recent, hot AI papers worth reviewing.

Sources (in priority order):
  1. pipeline/queue.yml          — papers you explicitly want covered
  2. Hugging Face Daily Papers   — community upvotes over the last N days ("hotness")
     + arXiv comment/journal_ref — conference acceptance (NeurIPS/ICLR/ICML/CVPR/ACL ...)

Already-posted papers, `skip:` entries and IDs passed via --exclude are never picked.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from typing import Any

from .common import load_config, load_queue, normalize_arxiv_id, now_kst, published_arxiv_ids, http_get_json
from .paper import fetch_arxiv_metadata


def hf_daily_papers(lookback_days: int) -> dict[str, dict[str, Any]]:
    today = now_kst().date()
    found: dict[str, dict[str, Any]] = {}
    for i in range(lookback_days + 1):
        day = today - timedelta(days=i)
        try:
            items = http_get_json(f"https://huggingface.co/api/daily_papers?date={day}&limit=100", timeout=45)
        except Exception as e:  # one bad day should not kill the run
            print(f"[warn] HF daily papers {day}: {e}", file=sys.stderr)
            continue
        for item in items:
            p = item.get("paper") or {}
            aid = p.get("id")
            if not aid:
                continue
            org = (p.get("organization") or item.get("organization") or {}) or {}
            prev = found.get(aid)
            if prev is None or p.get("upvotes", 0) > prev["upvotes"]:
                found[aid] = {
                    "arxiv_id": normalize_arxiv_id(aid),
                    "title": p.get("title", ""),
                    "upvotes": int(p.get("upvotes") or 0),
                    "organization": org.get("fullname") or org.get("name") or "",
                    "project_page": p.get("projectPage") or "",
                    "hf_url": f"https://huggingface.co/papers/{aid}",
                    "hf_date": str(day),
                }
    return found


def score(c: dict[str, Any], cfg: dict[str, Any]) -> float:
    s = float(c.get("upvotes", 0))
    v = c.get("venue")
    if v:
        s *= cfg["workshop_multiplier"] if v["track"] == "workshop" else cfg["venue_multiplier"]
    return s


def discover(limit: int = 1, exclude: set[str] | None = None, verbose: bool = True) -> list[dict[str, Any]]:
    cfg = load_config()["discovery"]
    q = load_queue()
    blocked = published_arxiv_ids() | set(q["skip"]) | {normalize_arxiv_id(x) for x in (exclude or set())}

    picks: list[dict[str, Any]] = []
    for aid in q["queue"]:
        if aid not in blocked and aid not in {p["arxiv_id"] for p in picks}:
            picks.append({"arxiv_id": aid, "source": "queue", "upvotes": 0, "score": float("inf")})
    if len(picks) >= limit:
        return picks[:limit]

    hf = hf_daily_papers(cfg["lookback_days"])
    bad_kw = [k.lower() for k in cfg.get("exclude_title_keywords", [])]
    pool = [
        c for c in hf.values()
        if c["arxiv_id"] not in blocked
        and c["upvotes"] >= cfg["min_upvotes"]
        and not any(k in c["title"].lower() for k in bad_kw)
    ]
    pool.sort(key=lambda c: -c["upvotes"])
    pool = pool[: cfg["candidates"]]
    if not pool:
        return picks

    meta = fetch_arxiv_metadata([c["arxiv_id"] for c in pool])
    for c in pool:
        m = meta.get(c["arxiv_id"], {})
        c["venue"] = m.get("venue")
        c["arxiv_comment"] = m.get("comment", "")
        c["source"] = "hf_daily"
        c["score"] = score(c, cfg)

    policy = cfg.get("venue_policy", "prefer")
    with_venue = sorted([c for c in pool if c.get("venue")], key=lambda c: -c["score"])
    ranked = sorted(pool, key=lambda c: -c["score"])
    if policy == "require":
        ranked = with_venue
    elif policy == "prefer":
        ranked = with_venue + [c for c in ranked if not c.get("venue")]

    if verbose:
        print(f"[discover] {len(hf)} HF papers, {len(pool)} candidates, {len(with_venue)} with an accepted venue",
              file=sys.stderr)
        for c in ranked[:10]:
            v = c["venue"]["venue"] + (f" {c['venue']['track']}" if c["venue"] else "") if c.get("venue") else "-"
            print(f"  {c['score']:7.1f}  ↑{c['upvotes']:<4} {c['arxiv_id']}  [{v}]  {c['title'][:70]}",
                  file=sys.stderr)

    for c in ranked:
        if len(picks) >= limit:
            break
        picks.append(c)
    return picks


def main() -> None:
    ap = argparse.ArgumentParser(description="Pick hot recent AI papers to review")
    ap.add_argument("--limit", type=int, default=1)
    ap.add_argument("--exclude", default="", help="comma-separated arXiv IDs to skip (e.g. open PRs)")
    args = ap.parse_args()
    exclude = {x for x in args.exclude.split(",") if x.strip()}
    print(json.dumps(discover(args.limit, exclude), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
