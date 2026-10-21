"""String similarity primitives, implemented here rather than imported so the scoring
is fully explainable to model-risk reviewers (every number in an alert can be
reproduced by hand from these functions)."""

from __future__ import annotations

from itertools import permutations


def jaro(a: str, b: str) -> float:
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return 0.0
    window = max(la, lb) // 2 - 1
    a_flags = [False] * la
    b_flags = [False] * lb
    matches = 0
    for i, ch in enumerate(a):
        lo, hi = max(0, i - window), min(i + window + 1, lb)
        for j in range(lo, hi):
            if not b_flags[j] and b[j] == ch:
                a_flags[i] = b_flags[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    transpositions = 0
    k = 0
    for i in range(la):
        if a_flags[i]:
            while not b_flags[k]:
                k += 1
            if a[i] != b[k]:
                transpositions += 1
            k += 1
    m = matches
    return (m / la + m / lb + (m - transpositions / 2) / m) / 3


def jaro_winkler(a: str, b: str, prefix_scale: float = 0.1) -> float:
    j = jaro(a, b)
    prefix = 0
    for x, y in zip(a[:4], b[:4]):
        if x != y:
            break
        prefix += 1
    return j + prefix * prefix_scale * (1 - j)


def soundex(token: str) -> str:
    """American Soundex. Used only for blocking (candidate generation), not scoring."""
    codes = {
        **dict.fromkeys("bfpv", "1"), **dict.fromkeys("cgjkqsxz", "2"),
        **dict.fromkeys("dt", "3"), "l": "4", **dict.fromkeys("mn", "5"), "r": "6",
    }
    token = "".join(c for c in token.lower() if c.isalpha())
    if not token:
        return ""
    out = token[0].upper()
    prev = codes.get(token[0], "")
    for c in token[1:]:
        code = codes.get(c, "")
        if code and code != prev:
            out += code
        if c not in "hw":
            prev = code
    return (out + "000")[:4]


def token_alignment(query: list[str], target: list[str]) -> tuple[float, float]:
    """Best one-to-one token alignment between two names.

    Returns (mean similarity over aligned pairs, coverage) where coverage is the share
    of the *shorter* name's tokens that found a partner scoring >= 0.85. Order-free, so
    "Rashid Muhammad" vs "Muhammad Rashid" scores 1.0 — names are frequently reordered
    between Arabic, Chinese and Western conventions.
    """
    if not query or not target:
        return 0.0, 0.0
    short, long_ = (query, target) if len(query) <= len(target) else (target, query)
    best_mean, best_cov = 0.0, 0.0
    if len(long_) <= 6:
        candidates = permutations(long_, len(short))
    else:  # bound the factorial blow-up on long entity names: greedy alignment
        candidates = [_greedy(short, long_)]
    for perm in candidates:
        sims = [jaro_winkler(s, t) for s, t in zip(short, perm)]
        mean = sum(sims) / len(sims)
        if mean > best_mean:
            best_mean = mean
            best_cov = sum(s >= 0.85 for s in sims) / len(short)
    return best_mean, best_cov


def _greedy(short: list[str], long_: list[str]) -> tuple[str, ...]:
    remaining = list(long_)
    picked = []
    for s in short:
        best = max(remaining, key=lambda t: jaro_winkler(s, t))
        picked.append(best)
        remaining.remove(best)
    return tuple(picked)
