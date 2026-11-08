"""Subtitles show English names as written (ICLR, NeurIPS, LARC); only the TTS voice gets the Korean reading.

Lexicon = editorial/pronunciation.yml (shared, editor-owned) + the spec's own `pronunciation:` map
(terms specific to one paper, e.g. a method name). The spec wins on conflicts.

    speak("ICLR 2026 최우수 논문", lex)  →  "아이클리어 2026 최우수 논문"
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from .common import EDITORIAL_DIR

LEXICON_PATH = EDITORIAL_DIR / "pronunciation.yml"


def load_lexicon(spec: dict[str, Any] | None = None) -> dict[str, str]:
    lex: dict[str, str] = {}
    if LEXICON_PATH.exists():
        lex.update(yaml.safe_load(LEXICON_PATH.read_text(encoding="utf-8")) or {})
    if spec:
        lex.update(spec.get("pronunciation") or {})
    return {str(k).strip(): str(v).strip() for k, v in lex.items() if str(k).strip() and str(v).strip()}


def _pattern(lex: dict[str, str]) -> re.Pattern | None:
    if not lex:
        return None
    terms = sorted(lex, key=len, reverse=True)  # "GPT-4o" before "GPT"
    return re.compile(r"(?<![A-Za-z0-9])(" + "|".join(map(re.escape, terms)) + r")(?![A-Za-z0-9])")


def speak_word(word: str, lex: dict[str, str], pat: re.Pattern | None = None) -> str:
    pat = pat or _pattern(lex)
    return pat.sub(lambda m: lex[m.group(1)], word) if pat else word


def speak(text: str, lex: dict[str, str]) -> str:
    """Spoken form, word by word, so caption words stay aligned with the TTS word timings."""
    pat = _pattern(lex)
    return " ".join(speak_word(w, lex, pat) for w in text.split())


def _reading_re(say: str) -> re.Pattern:
    # must start a word ("드라마" is not 라마); a particle may follow ("아이클리어의")
    return re.compile(r"(?<![가-힣A-Za-z0-9])" + re.escape(say))


def transliterations(text: str, lex: dict[str, str]) -> list[tuple[str, str]]:
    """(reading, term) pairs where a subtitle spells a known English name in Hangul (e.g. 아이클리어 → ICLR)."""
    return [(say, term) for term, say in lex.items() if re.search(r"[가-힣]", say) and _reading_re(say).search(text)]


def restore_terms(text: str, lex: dict[str, str]) -> tuple[str, list[tuple[str, str]]]:
    """Put the written form back into a subtitle that used a Hangul reading (아이클리어 → ICLR)."""
    found = transliterations(text, lex)
    for say, term in sorted(found, key=lambda x: len(x[0]), reverse=True):
        text = _reading_re(say).sub(term, text)
    return text, found


def lexicon_prompt(lex: dict[str, str]) -> str:
    return ", ".join(f"{k}={v}" for k, v in lex.items())
