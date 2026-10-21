"""Name normalisation applied identically to watchlist entries and screened records.

Screening quality is decided here more than in the matcher: if "Mohammed Al-Rashid"
and "MUHAMMAD ALRASHID" do not normalise to comparable token lists, no similarity
function downstream will rescue the match.
"""

from __future__ import annotations

import re
import unicodedata

# Honorifics and titles carry no identity signal and inflate token-set mismatch.
HONORIFICS = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "sir", "dame", "sheikh", "shaikh",
    "haji", "hajji", "mullah", "gen", "general", "col", "colonel", "capt", "captain",
}

# Legal-form suffixes for entities ("Acme Trading LLC" == "ACME TRADING L.L.C.").
LEGAL_SUFFIXES = {
    "ltd", "limited", "llc", "inc", "incorporated", "corp", "corporation", "co",
    "plc", "gmbh", "ag", "sa", "srl", "bv", "nv", "pte", "pvt", "fze", "fzco", "jsc",
    "ooo", "oao", "llp", "lp", "company",
}

# Common transliteration variants collapsed to one canonical spelling. Deliberately
# small: each entry was added because two spellings of the same name are both common
# in sanctions lists and customer data.
VARIANTS = {
    "mohammed": "muhammad", "mohamed": "muhammad", "mohammad": "muhammad",
    "muhammed": "muhammad", "mohamad": "muhammad", "mahomed": "muhammad",
    "ahmad": "ahmed", "ahmet": "ahmed",
    "abdul": "abd", "abdel": "abd", "abdal": "abd",
    "yousef": "yusuf", "yousuf": "yusuf", "youssef": "yusuf", "josef": "yusuf",
    "hussain": "husain", "hussein": "husain", "husein": "husain",
    "osama": "usama", "omar": "umar",
    "aleksandr": "alexander", "aleksander": "alexander", "alexandr": "alexander",
    "sergei": "sergey", "sergej": "sergey",
    "yuri": "yury", "iouri": "yury",
}

# Arabic-style particles are joined to the following token so "Al Rashid",
# "Al-Rashid" and "Alrashid" become the same token.
PARTICLES = {"al", "el", "bin", "ibn", "bint", "abu", "van", "von", "de", "der", "del"}

_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")


def fold(text: str) -> str:
    """Lower-case and strip diacritics (é -> e, ø -> o) without dropping letters."""
    text = text.replace("ø", "o").replace("Ø", "O").replace("ß", "ss").replace("ł", "l")
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.lower()


def tokens(name: str, *, entity: bool = False) -> list[str]:
    """Normalise a raw name into canonical tokens.

    `entity=True` additionally removes legal-form suffixes; it is set for
    organisation/vessel records, never for individuals (a person called "Co" exists).
    """
    text = fold(name)
    # Dotted abbreviations first ("L.L.C." -> "llc"), then hyphens/apostrophes act as
    # joiners within a word ("Al-Rashid" -> "alrashid", "O'Brien" -> "obrien").
    text = re.sub(r"(?<=\b[a-z])\.(?=[a-z]\b)", "", text)
    text = re.sub(r"(?<=[a-z])['’`](?=[a-z])", "", text)
    text = text.replace("-", " - ")
    text = _NON_ALNUM.sub(" ", text.replace(" - ", " "))
    raw = [t for t in _SPACES.split(text) if t]

    out: list[str] = []
    i = 0
    while i < len(raw):
        tok = raw[i]
        if tok in HONORIFICS:
            i += 1
            continue
        if entity and tok in LEGAL_SUFFIXES:
            i += 1
            continue
        if tok in PARTICLES and i + 1 < len(raw):
            tok = tok + raw[i + 1]
            i += 1
        out.append(VARIANTS.get(tok, tok))
        i += 1
    return out


def normalise(name: str, *, entity: bool = False) -> str:
    return " ".join(tokens(name, entity=entity))
