"""Alert-prioritisation model.

The rule engine is tuned for recall, so most alerts are false positives (common
names, namesakes with a different DOB). A logistic regression over the explainable
match features ranks alerts and auto-closes only those below a cut-off chosen on
held-out data to keep recall at the target. Coefficients are stored as plain JSON —
no pickles — so the model is reviewable and safe to load.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .engine import FEATURE_NAMES


@dataclass
class AlertModel:
    coef: list[float]
    intercept: float
    close_below: float  # probability under which an alert is auto-closed

    def probability(self, features: list[float]) -> float:
        z = self.intercept + sum(c * x for c, x in zip(self.coef, features))
        return 1.0 / (1.0 + math.exp(-z))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({
            "features": FEATURE_NAMES, "coef": self.coef,
            "intercept": self.intercept, "close_below": self.close_below,
        }, indent=2))

    @classmethod
    def load(cls, path: str | Path) -> AlertModel:
        d = json.loads(Path(path).read_text())
        if d["features"] != FEATURE_NAMES:
            raise ValueError(f"model features {d['features']} != engine features {FEATURE_NAMES}")
        return cls(d["coef"], d["intercept"], d["close_below"])


def train(X: list[list[float]], y: list[int], target_recall: float = 0.99,
          seed: int = 7) -> tuple[AlertModel, dict]:
    """Fit on 70%, pick the auto-close cut-off on the other 30% so that recall of
    true matches stays >= target_recall, and report what that cut-off buys."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split

    X_tr, X_va, y_tr, y_va = train_test_split(X, y, test_size=0.3, random_state=seed, stratify=y)
    clf = LogisticRegression(max_iter=1000, class_weight="balanced").fit(X_tr, y_tr)
    model = AlertModel([float(c) for c in clf.coef_[0]], float(clf.intercept_[0]), 0.0)

    probs = [model.probability(x) for x in X_va]
    positives = sorted(p for p, t in zip(probs, y_va) if t == 1)
    # Highest cut-off that still keeps `target_recall` of true matches above it.
    allowed_misses = int(len(positives) * (1 - target_recall))
    model.close_below = positives[allowed_misses] - 1e-9 if positives else 0.0

    kept = [(p, t) for p, t in zip(probs, y_va) if p >= model.close_below]
    metrics = {
        "validation_alerts": len(y_va),
        "validation_true_matches": sum(y_va),
        "close_below": round(model.close_below, 6),
        "recall": round(sum(t for _, t in kept) / max(1, sum(y_va)), 4),
        "alerts_auto_closed_pct": round(100 * (1 - len(kept) / len(y_va)), 2),
        "precision_before": round(sum(y_va) / len(y_va), 4),
        "precision_after": round(sum(t for _, t in kept) / max(1, len(kept)), 4),
    }
    return model, metrics
