"""Watchlist model, loader and blocking index."""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .normalize import tokens
from .similarity import soundex


@dataclass(frozen=True)
class Entry:
    entry_id: str
    entry_type: str  # individual | entity | vessel
    primary_name: str
    aliases: tuple[str, ...] = ()
    dob: str = ""  # "YYYY" or "YYYY-MM-DD"; empty when the list does not publish one
    nationality: str = ""  # ISO-3166 alpha-2
    program: str = ""

    @property
    def is_entity(self) -> bool:
        return self.entry_type != "individual"

    def names(self) -> list[tuple[str, str]]:
        """(name_type, raw_name) for the primary name and every alias."""
        return [("primary", self.primary_name)] + [("alias", a) for a in self.aliases]


def load_csv(path: str | Path) -> list[Entry]:
    entries = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            entries.append(
                Entry(
                    entry_id=row["entry_id"],
                    entry_type=row["entry_type"],
                    primary_name=row["primary_name"],
                    aliases=tuple(a for a in row.get("aliases", "").split("|") if a),
                    dob=row.get("dob", ""),
                    nationality=row.get("nationality", ""),
                    program=row.get("program", ""),
                )
            )
    return entries


@dataclass
class NameVariant:
    entry: Entry
    name_type: str
    raw: str
    toks: list[str]


@dataclass
class BlockingIndex:
    """Phonetic blocking: a record is only compared against list names that share at
    least one Soundex key with it. This tolerates vowel-level transliteration
    differences (Rashid/Rasheed both key to R230). Soundex keeps the first letter, so
    first-letter variants (Osama/Usama) are handled by the VARIANTS table in
    normalize.py instead."""

    variants: list[NameVariant] = field(default_factory=list)
    _by_key: dict[str, set[int]] = field(default_factory=lambda: defaultdict(set))

    @classmethod
    def build(cls, entries: list[Entry]) -> BlockingIndex:
        idx = cls()
        for entry in entries:
            for name_type, raw in entry.names():
                toks = tokens(raw, entity=entry.is_entity)
                if not toks:
                    continue
                vid = len(idx.variants)
                idx.variants.append(NameVariant(entry, name_type, raw, toks))
                for key in _keys(toks):
                    idx._by_key[key].add(vid)
        return idx

    def candidates(self, toks: list[str]) -> list[NameVariant]:
        ids: set[int] = set()
        for key in _keys(toks):
            ids |= self._by_key.get(key, set())
        return [self.variants[i] for i in sorted(ids)]


def _keys(toks: list[str]) -> set[str]:
    # Single-letter tokens (initials) would block against half the list.
    return {soundex(t) for t in toks if len(t) > 1}
