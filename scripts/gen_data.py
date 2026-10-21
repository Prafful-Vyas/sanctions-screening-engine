"""Generate a synthetic watchlist and customer file with labelled planted matches.

Nothing here is a real sanctioned party: names are random combinations of common
given/family names across naming cultures. The customer file contains
  * planted true matches — a list entry perturbed the way real data drifts
    (transliteration, typos, reordering, honorifics, diacritics, dropped middle name,
    alias use, missing DOB/country), and
  * namesakes — same or near-same name as a list entry but a different person
    (different DOB and nationality), which is where false positives come from.
Labels go to a separate file so the screener never sees them.
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

POOLS = {
    "arabic": (
        ["Muhammad", "Mohammed", "Ahmed", "Ali", "Hassan", "Hussein", "Yusuf", "Omar", "Khalid",
         "Ibrahim", "Abdullah", "Usama", "Tariq", "Faisal", "Hamza", "Karim", "Said", "Nasser",
         "Bilal", "Mustafa", "Jamal", "Walid", "Samir", "Adel", "Bassam", "Ziad", "Imad", "Rami",
         "Fadi", "Majed", "Anwar", "Mazen", "Nabil", "Raed", "Sami", "Hisham", "Talal", "Ayman"],
        ["Al-Rashid", "Al-Masri", "Haddad", "Khoury", "Al-Hakim", "Mansour", "Darwish",
         "Al-Tamimi", "Saleh", "Qureshi", "Al-Amin", "Farouk", "Abdel Aziz", "Bin Salem",
         "Al-Sayed", "Shaaban", "Al-Jabouri", "Hamdan", "Al-Khatib", "Barakat", "Al-Zahrani",
         "Nassar", "Al-Obeidi", "Kassem", "Al-Shami", "Halabi", "Yassin", "Al-Hashimi", "Awad",
         "Al-Dulaimi", "Sabbagh", "Al-Qasimi", "Ghanem", "Al-Najjar", "Khalil", "Al-Bakri"],
        ["SY", "IQ", "YE", "LB", "AE", "EG", "LY", "SA"],
    ),
    "russian": (
        ["Alexander", "Sergey", "Dmitry", "Yury", "Ivan", "Mikhail", "Vladimir", "Nikolai",
         "Oleg", "Pavel", "Andrei", "Viktor", "Boris", "Gennady", "Igor", "Konstantin", "Leonid",
         "Maxim", "Roman", "Stanislav", "Timur", "Vadim", "Yevgeny", "Arkady", "Anatoly", "Ruslan"],
        ["Ivanov", "Petrov", "Sokolov", "Volkov", "Morozov", "Kuznetsov", "Popov", "Lebedev",
         "Novikov", "Fedorov", "Orlov", "Zaitsev", "Belov", "Grigoriev", "Komarov", "Medvedev",
         "Nikitin", "Pavlov", "Romanov", "Semenov", "Smirnov", "Tarasov", "Vasiliev", "Yegorov",
         "Belyaev", "Gusev", "Kiselev", "Makarov", "Osipov", "Sorokin", "Titov", "Utkin"],
        ["RU", "BY", "KZ", "UA"],
    ),
    "chinese": (
        ["Wei", "Jun", "Ming", "Hua", "Lei", "Yan", "Feng", "Jian", "Xin", "Bo", "Hao", "Jie",
         "Kai", "Lin", "Peng", "Qiang", "Rui", "Tao", "Xiang", "Yong", "Zhi", "Gang", "Hong", "Bin"],
        ["Li", "Zhang", "Wang", "Liu", "Chen", "Yang", "Huang", "Zhao", "Zhou", "Wu", "Xu", "Sun",
         "Ma", "Zhu", "Hu", "Guo", "He", "Gao", "Lin", "Luo", "Zheng", "Liang", "Xie", "Song"],
        ["CN", "HK", "SG"],
    ),
    "latin": (
        ["José", "Juan", "Carlos", "Luis", "Jorge", "Miguel", "Andrés", "Ramón", "Diego",
         "Alejandro", "Fernando", "Ricardo", "Eduardo", "Rafael", "Héctor", "Javier", "Raúl",
         "Sergio", "Óscar", "Pablo", "Mauricio", "Gustavo", "Ernesto", "Rubén"],
        ["García", "Rodríguez", "Martínez", "Hernández", "López", "González", "Pérez",
         "Sánchez", "Ramírez", "Torres", "Flores", "Rivera", "Gómez", "Díaz", "Cruz", "Morales",
         "Reyes", "Gutiérrez", "Ortiz", "Castillo", "Jiménez", "Vargas", "Romero", "Herrera",
         "Medina", "Aguilar", "Mendoza", "Castro", "Ruiz", "Álvarez"],
        ["VE", "CO", "MX", "CU", "NI"],
    ),
    "persian": (
        ["Reza", "Mehdi", "Hossein", "Ali", "Mohsen", "Javad", "Saeed", "Majid", "Amir", "Behrouz",
         "Dariush", "Farhad", "Hamid", "Kamran", "Masoud", "Nader", "Parviz", "Siamak"],
        ["Hosseini", "Rahimi", "Karimi", "Moradi", "Jafari", "Ahmadi", "Rezaei", "Tehrani",
         "Sadeghi", "Ghorbani", "Mohammadi", "Hashemi", "Mousavi", "Najafi", "Shirazi", "Esfahani",
         "Kazemi", "Bagheri", "Salehi", "Zamani"],
        ["IR"],
    ),
}
# Customer-only pool: names that should almost never match the list.
CUSTOMER_ONLY = (
    ["Rahul", "Priya", "Amit", "Sneha", "Arjun", "Kavya", "James", "Emma", "Oliver",
     "Sophie", "Liam", "Grace", "Rohan", "Ananya", "Vikram", "Neha"],
    ["Sharma", "Patel", "Iyer", "Reddy", "Nair", "Gupta", "Smith", "Brown", "Taylor",
     "Wilson", "Clarke", "Mehta", "Joshi", "Kapoor", "Desai", "Bose"],
    ["IN", "GB", "US", "AU"],
)
ENTITY_WORDS = ["Gulf", "Northern", "Eastern", "Star", "Ocean", "Golden", "Crescent", "Silk",
                "Delta", "Atlas", "Orion", "Falcon", "Cedar", "Baltic", "Pacific", "Phoenix"]
ENTITY_KINDS = ["Trading", "Shipping", "Petroleum", "Logistics", "Holdings", "Exchange",
                "Industries", "Metals", "Shipbuilding", "Investments"]
ENTITY_SUFFIX = ["LLC", "Co", "Ltd", "FZE", "JSC", "Limited", "Company"]
PROGRAMS = ["SDGT", "UKR-EO13660", "IRAN", "SYRIA", "CUBA", "VENEZUELA-EO13850", "DPRK3"]

VARIANT_SWAPS = {
    "Muhammad": ["Mohammed", "Mohamed", "Muhammed", "Mohammad"], "Mohammed": ["Muhammad", "Mohamed"],
    "Hussein": ["Hussain", "Husein"], "Yusuf": ["Yousef", "Youssef"], "Omar": ["Umar"],
    "Usama": ["Osama"], "Ahmed": ["Ahmad"], "Alexander": ["Aleksandr", "Alexandr"],
    "Sergey": ["Sergei"], "Yury": ["Yuri", "Iouri"], "Al-Rashid": ["Al Rashid", "Alrashid", "Al-Rasheed"],
    "Al-Masri": ["Al Masri", "El-Masri"], "Abdel Aziz": ["Abdul Aziz", "Abdelaziz"],
}
HONORIFICS = ["Mr", "Dr", "Sheikh", "Haji", "Gen."]


def person(rng: random.Random, pool) -> tuple[str, str]:
    given, family, countries = pool
    parts = [rng.choice(given)]
    if rng.random() < 0.45:
        parts.append(rng.choice(given))  # middle / patronymic
    parts.append(rng.choice(family))
    return " ".join(parts), rng.choice(countries)


def dob(rng: random.Random) -> str:
    return f"{rng.randint(1950, 1995)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


def typo(rng: random.Random, word: str) -> str:
    if len(word) < 5:
        return word
    i = rng.randint(1, len(word) - 2)
    op = rng.choice(["swap", "drop", "double"])
    if op == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if op == "drop":
        return word[:i] + word[i + 1:]
    return word[:i] + word[i] + word[i:]


def strip_accents_or_add(rng: random.Random, name: str) -> str:
    import unicodedata
    plain = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    return plain if plain != name else name.replace("e", "é", 1) if rng.random() < 0.5 else name


def perturb(rng: random.Random, name: str, aliases: list[str]) -> str:
    if aliases and rng.random() < 0.15:
        name = rng.choice(aliases)
    parts = name.split(" ")
    for _ in range(rng.choice([1, 1, 2])):
        op = rng.choice(["variant", "typo", "reorder", "honorific", "accent", "drop_middle",
                         "upper", "variant"])
        if op == "variant":
            parts = [rng.choice(VARIANT_SWAPS[p]) if p in VARIANT_SWAPS and rng.random() < 0.8
                     else p for p in parts]
        elif op == "typo":
            j = rng.randrange(len(parts))
            parts[j] = typo(rng, parts[j])
        elif op == "reorder" and len(parts) >= 2:
            parts = parts[-1:] + parts[:-1]
        elif op == "honorific":
            parts = [rng.choice(HONORIFICS)] + parts
        elif op == "accent":
            parts = strip_accents_or_add(rng, " ".join(parts)).split(" ")
        elif op == "drop_middle" and len(parts) >= 3:
            parts = [parts[0], parts[-1]]
        elif op == "upper":
            parts = [p.upper() for p in parts]
    return " ".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data")
    ap.add_argument("--entries", type=int, default=1500)
    ap.add_argument("--customers", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    entries = []
    seen_names = set()
    while len(entries) < args.entries:
        eid = f"WL-{len(entries) + 1:05d}"
        if rng.random() < 0.8:
            pool = POOLS[rng.choice(list(POOLS))]
            name, country = person(rng, pool)
            if name in seen_names:
                continue
            aliases = [person(rng, pool)[0] for _ in range(rng.choice([0, 0, 1, 2]))]
            entries.append(dict(entry_id=eid, entry_type="individual", primary_name=name,
                                aliases="|".join(aliases), dob=dob(rng) if rng.random() < 0.8 else "",
                                nationality=country if rng.random() < 0.85 else "",
                                program=rng.choice(PROGRAMS)))
        else:
            name = f"{rng.choice(ENTITY_WORDS)} {rng.choice(ENTITY_WORDS)} {rng.choice(ENTITY_KINDS)} {rng.choice(ENTITY_SUFFIX)}"
            if name in seen_names:
                continue
            entries.append(dict(entry_id=eid, entry_type="entity", primary_name=name, aliases="",
                                dob="", nationality=rng.choice(["IR", "SY", "RU", "AE", "KP", "VE"]),
                                program=rng.choice(PROGRAMS)))
        seen_names.add(name)

    customers, labels = [], []
    individuals = [e for e in entries if e["entry_type"] == "individual"]
    for i in range(args.customers):
        cid = f"C{i + 1:07d}"
        r = rng.random()
        if r < 0.02:  # planted true match
            e = rng.choice(entries)
            name = perturb(rng, e["primary_name"], [a for a in e["aliases"].split("|") if a])
            if e["entry_type"] == "entity":
                name = name.replace(" LLC", " L.L.C.").replace(" Ltd", " Limited")
            d = e["dob"] if rng.random() < 0.7 else (e["dob"][:4] if e["dob"] and rng.random() < 0.5 else "")
            c = e["nationality"] if rng.random() < 0.7 else ""
            customers.append(dict(record_id=cid, name=name, record_type=e["entry_type"], dob=d, country=c))
            labels.append(dict(record_id=cid, truth_entry_id=e["entry_id"], kind="true_match"))
        elif r < 0.05:  # namesake: same name, different person
            e = rng.choice(individuals)
            year = int(e["dob"][:4]) if e["dob"] else 1970
            d = f"{year + rng.choice([-1, 1]) * rng.randint(6, 30)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
            customers.append(dict(record_id=cid, name=e["primary_name"], record_type="individual",
                                  dob=d, country=rng.choice(CUSTOMER_ONLY[2])))
            labels.append(dict(record_id=cid, truth_entry_id="", kind="namesake"))
        else:
            pool = POOLS[rng.choice(list(POOLS))] if rng.random() < 0.15 else CUSTOMER_ONLY
            name, country = person(rng, pool)
            customers.append(dict(record_id=cid, name=name, record_type="individual",
                                  dob=dob(rng), country=country))
            labels.append(dict(record_id=cid, truth_entry_id="", kind="background"))

    for fname, rows in [("watchlist.csv", entries), ("customers.csv", customers), ("labels.csv", labels)]:
        with open(out / fname, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(f"wrote {len(entries)} entries, {len(customers)} customers to {out}/")


if __name__ == "__main__":
    main()
