"""Script-aware tokenizing, so the filters work in any language and not only English.

The relevance checks used to find words with [a-z0-9]+, which turns Hindi or Chinese into nothing and cuts accented
Latin words in half ("preço" became "pre"), so every post in those languages was filtered out. A word is now a run of
letters, digits and combining marks in any script, with an apostrophe allowed inside a word. Scripts written without
spaces (Chinese, Japanese kana, Thai, Lao, Khmer, Burmese) are cut into overlapping two-character pieces, the usual way
to match words there without a dictionary. Hyphens split words, as before.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

_UNSPACED = (
    (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF), (0x20000, 0x2FA1F),  # Han
    (0x3040, 0x30FF), (0x31F0, 0x31FF),                                         # Hiragana, Katakana
    (0x0E00, 0x0EFF), (0x1000, 0x109F), (0x1780, 0x17FF),                       # Thai, Lao, Burmese, Khmer
)
APOSTROPHES = ("'", "’")


def is_unspaced(ch: str) -> bool:
    cp = ord(ch)
    return any(a <= cp <= b for a, b in _UNSPACED)


def has_unspaced(word: str) -> bool:
    return any(is_unspaced(c) for c in word)


@lru_cache(maxsize=4096)
def _kind(ch: str) -> int:
    """0 separator, 1 letter/digit/mark of a spaced script, 2 letter of an unspaced script, 3 apostrophe."""
    if ch in APOSTROPHES:
        return 3
    if unicodedata.category(ch)[0] in "LNM":
        return 2 if is_unspaced(ch) else 1
    return 0


@lru_cache(maxsize=8192)
def tokens(text: str) -> tuple[str, ...]:
    """Lower-cased words in order. Unspaced scripts come out as overlapping character pairs (a lone character stays alone)."""
    s = (text or "").lower()
    if s.isascii():  # fast path: plain English text needs no per-character work
        return tuple(re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)*", s))
    out: list[str] = []
    run: list[str] = []
    mode = 0

    def flush() -> None:
        nonlocal run, mode
        if run:
            w = "".join(run).strip("'’")
            if w:
                if mode == 2:
                    out.extend([w[i:i + 2] for i in range(len(w) - 1)] or [w])
                else:
                    out.append(w)
        run, mode = [], 0

    n = len(s)
    for i, ch in enumerate(s):
        k = _kind(ch)
        if k == 3:  # an apostrophe belongs to the word only between two letters ("don't"), otherwise it is a separator
            if run and mode == 1 and i + 1 < n and _kind(s[i + 1]) == 1:
                run.append(ch)
            else:
                flush()
        elif k == 0:
            flush()
        else:
            if run and k != mode:
                flush()
            mode = k
            run.append(ch)
    flush()
    return tuple(out)


def joined_words(text: str) -> list[str]:
    """Words with hyphenated compounds kept whole ("low-end"), for building queries."""
    out: list[str] = []
    for chunk in (text or "").lower().split():
        parts = tokens(chunk)
        if not parts:
            continue
        out.append("-".join(parts) if "-" in chunk and not any(has_unspaced(p) for p in parts) else None)
        if out[-1] is None:
            out.pop()
            out.extend(parts)
    return out
