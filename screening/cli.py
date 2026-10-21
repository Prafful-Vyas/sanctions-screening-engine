"""Command line entry point: `python -m screening <command>`."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path

from . import store
from .engine import Record, Screener
from .model import AlertModel, train
from .watchlist import load_csv


def _records(path: str) -> list[Record]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [Record(r["record_id"], r["name"], r.get("record_type", "individual"),
                       r.get("dob", ""), r.get("country", "")) for r in csv.DictReader(fh)]


def _list_version(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def _labelled_alerts(screener: Screener, records: list[Record], labels_path: str):
    with open(labels_path, newline="", encoding="utf-8") as fh:
        truth = {r["record_id"]: r["truth_entry_id"] for r in csv.DictReader(fh)}
    X, y, planted, found = [], [], 0, 0
    for rec in records:
        t = truth.get(rec.record_id, "")
        planted += bool(t)
        matches = screener.screen(rec)
        found += any(m.entry_id == t for m in matches) if t else 0
        for m in matches:
            X.append(m.features())
            y.append(int(m.entry_id == t))
    return X, y, planted, found


def cmd_screen(args) -> int:
    entries = load_csv(args.watchlist)
    screener = Screener(entries, threshold=args.threshold)
    records = _records(args.input)
    model = AlertModel.load(args.model) if args.model else None
    run_id = args.run_id or uuid.uuid4().hex[:16]

    conn = store.connect_sqlite(args.db)
    store.start_run(conn, run_id, _list_version(args.watchlist), args.threshold, len(records))
    t0 = time.perf_counter()
    batch, raised, closed = [], 0, 0
    for rec in records:
        for m in screener.screen(rec):
            prob = model.probability(m.features()) if model else None
            status = "AUTO_CLOSED" if model and prob < model.close_below else "OPEN"
            closed += status == "AUTO_CLOSED"
            raised += 1
            batch.append((m, prob, status))
        if len(batch) >= 500:
            store.save_alerts(conn, run_id, batch)
            batch = []
    store.save_alerts(conn, run_id, batch)
    store.finish_run(conn, run_id, raised)
    elapsed = time.perf_counter() - t0
    print(json.dumps({"run_id": run_id, "records": len(records), "alerts": raised,
                      "auto_closed": closed, "open": raised - closed,
                      "seconds": round(elapsed, 2),
                      "records_per_sec": round(len(records) / elapsed, 1)}))
    return 0


def cmd_evaluate(args) -> int:
    screener = Screener(load_csv(args.watchlist), threshold=args.threshold)
    _, y, planted, found = _labelled_alerts(screener, _records(args.input), args.labels)
    print(json.dumps({"threshold": args.threshold, "planted_true_matches": planted,
                      "detected": found, "recall": round(found / max(1, planted), 4),
                      "alerts": len(y), "true_alerts": sum(y),
                      "alert_precision": round(sum(y) / max(1, len(y)), 4)}))
    return 0


def cmd_train(args) -> int:
    screener = Screener(load_csv(args.watchlist), threshold=args.threshold)
    X, y, _, _ = _labelled_alerts(screener, _records(args.input), args.labels)
    model, metrics = train(X, y, target_recall=args.target_recall)
    model.save(args.out)
    print(json.dumps(metrics))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="screening")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--watchlist", required=True)
        p.add_argument("--input", required=True, help="customer CSV")
        p.add_argument("--threshold", type=float, default=0.88)

    p = sub.add_parser("screen", help="screen a customer file and persist alerts")
    common(p)
    p.add_argument("--db", default="screening.db")
    p.add_argument("--model", help="alert model JSON; enables auto-closing")
    p.add_argument("--run-id")
    p.set_defaults(fn=cmd_screen)

    p = sub.add_parser("evaluate", help="recall/precision of the rule engine on labelled data")
    common(p)
    p.add_argument("--labels", required=True)
    p.set_defaults(fn=cmd_evaluate)

    p = sub.add_parser("train", help="fit the alert-prioritisation model")
    common(p)
    p.add_argument("--labels", required=True)
    p.add_argument("--target-recall", type=float, default=0.99)
    p.add_argument("--out", default="alert_model.json")
    p.set_defaults(fn=cmd_train)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
