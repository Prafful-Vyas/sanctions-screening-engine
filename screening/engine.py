"""Screening engine: candidate generation, explainable scoring, alert decision."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .normalize import tokens
from .similarity import jaro_winkler, token_alignment
from .watchlist import BlockingIndex, Entry, NameVariant


@dataclass(frozen=True)
class Record:
    record_id: str
    name: str
    record_type: str = "individual"
    dob: str = ""
    country: str = ""


@dataclass
class Match:
    record_id: str
    entry_id: str
    matched_name: str
    name_type: str
    name_score: float
    token_mean: float
    coverage: float
    length_ratio: float
    dob_signal: float
    country_signal: float
    type_match: int
    score: float

    def features(self) -> list[float]:
        """Feature vector for the false-positive model (see model.py)."""
        return [
            self.name_score, self.token_mean, self.coverage, self.length_ratio, self.dob_signal,
            self.country_signal, float(self.type_match), 1.0 if self.name_type == "primary" else 0.0,
        ]

    def as_row(self) -> dict:
        return asdict(self)


FEATURE_NAMES = [
    "name_score", "token_mean", "coverage", "length_ratio", "dob_signal", "country_signal", "type_match",
    "is_primary_name",
]


def dob_signal(record_dob: str, entry_dob: str) -> float:
    """+1 exact date, +0.5 same year only, 0 unknown on either side, -1 conflict."""
    if not record_dob or not entry_dob:
        return 0.0
    if record_dob == entry_dob:
        return 1.0
    if record_dob[:4] == entry_dob[:4]:
        return 0.5 if (len(record_dob) == 4 or len(entry_dob) == 4) else 0.25
    try:
        return -1.0 if abs(int(record_dob[:4]) - int(entry_dob[:4])) > 2 else -0.25
    except ValueError:
        return 0.0


def country_signal(record_country: str, entry_country: str) -> float:
    if not record_country or not entry_country:
        return 0.0
    return 1.0 if record_country.upper() == entry_country.upper() else -0.5


class Screener:
    """Rule-based screener. `threshold` applies to the name score only; secondary
    identifiers (DOB, nationality) adjust the final score but never suppress an alert
    on their own — regulators expect a strong name match to be reviewed even when the
    customer's DOB is missing or mistyped."""

    def __init__(self, entries: list[Entry], threshold: float = 0.88):
        self.index = BlockingIndex.build(entries)
        self.threshold = threshold

    def screen(self, record: Record) -> list[Match]:
        is_entity = record.record_type != "individual"
        q = tokens(record.name, entity=is_entity)
        if not q:
            return []
        best: dict[str, Match] = {}
        for variant in self.index.candidates(q):
            m = self._score(record, q, variant)
            if m.name_score < self.threshold:
                continue
            prev = best.get(m.entry_id)
            if prev is None or m.score > prev.score:
                best[m.entry_id] = m
        return sorted(best.values(), key=lambda m: m.score, reverse=True)

    def _score(self, record: Record, q: list[str], v: NameVariant) -> Match:
        mean, cov = token_alignment(q, v.toks)
        whole = jaro_winkler(" ".join(sorted(q)), " ".join(sorted(v.toks)))
        # Coverage penalises "Ali" matching "Ali Hassan Abdullah": one strong token
        # is not a name match.
        name_score = round(0.6 * mean + 0.25 * cov + 0.15 * whole, 4)
        dob = dob_signal(record.dob, v.entry.dob)
        ctry = country_signal(record.country, v.entry.nationality)
        type_match = int((record.record_type == "individual") == (v.entry.entry_type == "individual"))
        score = name_score + 0.05 * dob + 0.03 * ctry - (0.0 if type_match else 0.1)
        return Match(
            record_id=record.record_id, entry_id=v.entry.entry_id, matched_name=v.raw,
            name_type=v.name_type, name_score=name_score, token_mean=round(mean, 4),
            coverage=round(cov, 4),
            length_ratio=round(min(len(q), len(v.toks)) / max(len(q), len(v.toks)), 4),
            dob_signal=dob, country_signal=ctry,
            type_match=type_match, score=round(score, 4),
        )
