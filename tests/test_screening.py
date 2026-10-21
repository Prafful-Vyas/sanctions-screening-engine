import random

import pytest

from screening import store
from screening.engine import Record, Screener, dob_signal
from screening.model import AlertModel, train
from screening.normalize import normalise, tokens
from screening.similarity import jaro_winkler, soundex, token_alignment
from screening.watchlist import Entry

ENTRIES = [
    Entry("WL-1", "individual", "Muhammad Khalid Al-Rashid", ("Abu Khalid",), "1971-03-14", "SY", "SDGT"),
    Entry("WL-2", "individual", "Aleksandr Petrov", (), "1965", "RU", "UKR-EO13660"),
    Entry("WL-3", "entity", "Golden Crescent Trading LLC", (), "", "AE", "IRAN"),
    Entry("WL-4", "individual", "José García Ramírez", (), "1980-01-02", "VE", "VENEZUELA"),
]


@pytest.mark.parametrize("raw,expected", [
    ("Mr. MOHAMMED Al-Rashid", "muhammad alrashid"),
    ("Muhammad al Rashid", "muhammad alrashid"),
    ("José  García-Ramírez", "jose garcia ramirez"),
    ("Sheikh Usama Bin Salem", "usama binsalem"),
])
def test_normalise_individuals(raw, expected):
    assert normalise(raw) == expected


def test_legal_suffixes_only_removed_for_entities():
    assert tokens("Golden Crescent Trading L.L.C.", entity=True) == ["golden", "crescent", "trading"]
    assert tokens("Golden Crescent Trading L.L.C.") == ["golden", "crescent", "trading", "llc"]


@pytest.mark.parametrize("a,b,expected", [
    ("martha", "marhta", 0.9611), ("dixon", "dicksonx", 0.8133), ("dwayne", "duane", 0.84),
])
def test_jaro_winkler_reference_values(a, b, expected):
    assert jaro_winkler(a, b) == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize("word,code", [
    ("Robert", "R163"), ("Rupert", "R163"), ("Ashcraft", "A261"), ("Tymczak", "T522"),
    ("Pfister", "P236"), ("Rashid", "R230"), ("Rasheed", "R230"),
])
def test_soundex(word, code):
    assert soundex(word) == code


def test_token_alignment_is_order_free():
    mean, cov = token_alignment(["rashid", "muhammad"], ["muhammad", "rashid"])
    assert mean == pytest.approx(1.0) and cov == 1.0


@pytest.fixture(scope="module")
def screener():
    return Screener(ENTRIES)


@pytest.mark.parametrize("name", [
    "MOHAMED KHALID ALRASHID",  # transliteration + joined particle + case
    "Al Rashid Muhammad Khalid",  # reordered
    "Dr Muhammad Kalid Al-Rashid",  # honorific + typo
    "Abu Khalid",  # alias
])
def test_detects_perturbed_names(screener, name):
    hits = screener.screen(Record("C1", name))
    assert hits and hits[0].entry_id == "WL-1"


def test_entity_with_different_legal_form(screener):
    hits = screener.screen(Record("C2", "GOLDEN CRESCENT TRADING LIMITED", "entity"))
    assert [h.entry_id for h in hits] == ["WL-3"]


def test_no_alert_for_unrelated_name(screener):
    assert screener.screen(Record("C3", "Priya Sharma", dob="1990-05-05", country="IN")) == []


def test_single_shared_token_is_not_a_match(screener):
    assert screener.screen(Record("C4", "Muhammad Iqbal")) == []


def test_secondary_identifiers_adjust_but_do_not_suppress(screener):
    same = screener.screen(Record("C5", "Jose Garcia Ramirez", dob="1980-01-02", country="VE"))[0]
    namesake = screener.screen(Record("C6", "Jose Garcia Ramirez", dob="1999-07-07", country="ES"))[0]
    assert same.entry_id == namesake.entry_id == "WL-4"
    assert same.score > namesake.score


@pytest.mark.parametrize("a,b,sig", [
    ("1971-03-14", "1971-03-14", 1.0), ("1971", "1971-03-14", 0.5), ("", "1971", 0.0),
    ("1990-01-01", "1971-03-14", -1.0),
])
def test_dob_signal(a, b, sig):
    assert dob_signal(a, b) == sig


def test_store_round_trip(tmp_path, screener):
    conn = store.connect_sqlite(tmp_path / "s.db")
    store.start_run(conn, "r1", "v1", 0.88, 1)
    hits = screener.screen(Record("C1", "Muhammad Khalid Al Rashid"))
    store.save_alerts(conn, "r1", [(h, 0.9, "OPEN") for h in hits])
    store.finish_run(conn, "r1", len(hits))
    rows = conn.execute("SELECT r.alerts_raised, a.entry_id, a.status FROM screening_run r "
                        "JOIN screening_alert a USING (run_id)").fetchall()
    assert rows == [(1, "WL-1", "OPEN")]


def test_model_keeps_recall_and_round_trips(tmp_path):
    rng = random.Random(0)
    X, y = [], []
    for _ in range(600):
        true = rng.random() < 0.2
        dob = rng.choice([1.0, 0.5, 0.0]) if true else rng.choice([-1.0, 0.0, 0.0])
        X.append([rng.uniform(0.92, 1) if true else rng.uniform(0.88, 0.97), 0.95, 1.0, 1.0,
                  dob, 0.0, 1.0, 1.0])
        y.append(int(true))
    model, metrics = train(X, y, target_recall=0.99)
    assert metrics["recall"] >= 0.99
    assert metrics["precision_after"] >= metrics["precision_before"]
    model.save(tmp_path / "m.json")
    loaded = AlertModel.load(tmp_path / "m.json")
    assert loaded.probability(X[0]) == pytest.approx(model.probability(X[0]))
