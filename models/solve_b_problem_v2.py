"""Second-pass, evidence-first solver for school-contest B.

This module deliberately sits beside ``solve_b_problem.py``.  The first solver
is retained as the historical T-21 baseline; this entry point is the T-23
replay used to test the rebuilt Skill registry.  It reuses only the audited
CSV mapping/cleaning primitives and adds:

* a transparent majority and core-feature baseline;
* repeated out-of-fold evaluation for the core and full logistic routes;
* bootstrap intervals and calibration diagnostics;
* an imputation ablation, policy uncertainty and capacity curve;
* a Latin-hypercube stress envelope and boundary/counterexample search.

The raw attachment is never copied or modified.  Customer-level risk output is
local-only; committed artifacts are aggregate and synthetic/parameterized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import mannwhitneyu
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.model_selection import RepeatedStratifiedKFold, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

# These are the audited field mapping and deterministic cleaning primitives
# from the original, already-tested solver.  No material-package code is
# executed or imported.
from solve_b_problem import (  # type: ignore
    CATEGORICAL,
    CHINESE_TO_ENGLISH,
    ID,
    NUMERIC,
    TARGET,
    clean_data,
    make_encoder,
    read_csv_detect,
    set_chinese_font,
)
from solve_b_problem import make_intersection_summary  # type: ignore


SCHEMA = "b-problem-replay/v2"
DEFAULT_SEED = 42
CORE_CATEGORICAL = [
    "contract",
    "online_security",
    "online_backup",
    "device_protection",
    "tech_support",
    "streaming_tv",
    "streaming_movies",
]
CORE_NUMERIC = ["tenure_months", "monthly_charges"]
VALUE_ADDED = CORE_CATEGORICAL[1:]
DISPLAY_NAMES = {
    "gender": "性别",
    "senior": "老年人",
    "partner": "伴侣",
    "dependents": "家属",
    "phone_service": "电话服务",
    "multiple_lines": "多条线路",
    "internet_service": "互联网服务",
    "online_security": "在线安全",
    "online_backup": "在线备份",
    "device_protection": "设备保护",
    "tech_support": "技术支持",
    "streaming_tv": "电视流媒体",
    "streaming_movies": "电影流媒体",
    "contract": "合同类型",
    "paperless_billing": "电子账单",
    "payment_method": "支付方式",
}


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.ndarray,)):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if pd.isna(value):
        return None
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in ("numpy", "pandas", "scipy", "sklearn"):
        try:
            module = __import__(name)
            versions[name] = str(getattr(module, "__version__", "unknown"))
        except Exception as exc:  # pragma: no cover - environment diagnostic
            versions[name] = f"unavailable:{type(exc).__name__}"
    return versions


def _make_logistic(categorical: Sequence[str], numeric: Sequence[str], seed: int) -> Pipeline:
    try:
        encoder = OneHotEncoder(handle_unknown="ignore", drop="first", sparse_output=False)
    except TypeError:  # pragma: no cover - old sklearn fallback
        encoder = OneHotEncoder(handle_unknown="ignore", drop="first", sparse=False)
    transformer = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), list(numeric)),
            ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("onehot", encoder)]), list(categorical)),
        ],
        remainder="drop",
    )
    return Pipeline(
        [
            ("preprocess", transformer),
            ("model", LogisticRegression(max_iter=4000, C=1.0, solver="lbfgs", random_state=seed)),
        ]
    )


def metric_dict(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "average_precision": float(average_precision_score(y, p)),
        "brier": float(brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
    }


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict[str, Any]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows: list[dict[str, Any]] = []
    weighted = 0.0
    max_gap = 0.0
    n = len(y)
    for index in range(bins):
        left, right = edges[index], edges[index + 1]
        mask = (p >= left) & (p < right if index < bins - 1 else p <= right)
        count = int(mask.sum())
        if count == 0:
            rows.append({"bin": index + 1, "n": 0, "mean_predicted": None, "observed_rate": None, "absolute_gap": None})
            continue
        pred = float(p[mask].mean())
        obs = float(y[mask].mean())
        gap = abs(pred - obs)
        weighted += count / max(n, 1) * gap
        max_gap = max(max_gap, gap)
        rows.append({"bin": index + 1, "n": count, "mean_predicted": pred, "observed_rate": obs, "absolute_gap": gap})
    return {"bins": rows, "ece": float(weighted), "max_calibration_error": float(max_gap)}


def quantile_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> dict[str, Any]:
    """Calibration with equal-frequency bins, useful when the tail is sparse."""
    order = np.argsort(p, kind="mergesort")
    groups = np.array_split(order, bins)
    rows: list[dict[str, Any]] = []
    weighted = 0.0
    max_gap = 0.0
    n = len(y)
    for index, positions in enumerate(groups, start=1):
        if len(positions) == 0:
            continue
        pred = float(p[positions].mean())
        obs = float(y[positions].mean())
        gap = abs(pred - obs)
        weighted += len(positions) / max(n, 1) * gap
        max_gap = max(max_gap, gap)
        rows.append({"bin": index, "n": int(len(positions)), "mean_predicted": pred, "observed_rate": obs, "absolute_gap": gap})
    return {"bins": rows, "ece": float(weighted), "max_calibration_error": float(max_gap)}


def repeated_oof(
    frame: pd.DataFrame,
    categorical: Sequence[str],
    numeric: Sequence[str],
    seed: int,
    splits: int = 5,
    repeats: int = 3,
) -> tuple[np.ndarray, dict[str, Any], list[dict[str, Any]]]:
    """Average repeated OOF probabilities; each fold fits preprocessing anew."""
    X = frame[list(categorical) + list(numeric)]
    y = frame[TARGET].to_numpy(dtype=int)
    predictions = np.zeros((repeats, len(frame)), dtype=float)
    fold_rows: list[dict[str, Any]] = []
    for repeat in range(repeats):
        cv = StratifiedKFold(n_splits=splits, shuffle=True, random_state=seed + repeat)
        for fold, (train_idx, test_idx) in enumerate(cv.split(X, y), start=1):
            model = _make_logistic(categorical, numeric, seed + repeat)
            model.fit(X.iloc[train_idx], y[train_idx])
            predictions[repeat, test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
            fold_metric = metric_dict(y[test_idx], predictions[repeat, test_idx])
            fold_rows.append({"repeat": repeat + 1, "fold": fold, "n_train": int(len(train_idx)), "n_test": int(len(test_idx)), **fold_metric})
    averaged = predictions.mean(axis=0)
    summary = metric_dict(y, averaged)
    summary.update(
        {
            "repeats": repeats,
            "folds": splits,
            "fold_auc_mean": float(np.mean([row["roc_auc"] for row in fold_rows])),
            "fold_auc_std": float(np.std([row["roc_auc"] for row in fold_rows], ddof=1)),
            "oof_missing": int(np.isnan(averaged).sum()),
        }
    )
    return averaged, summary, fold_rows


def holdout_route(frame: pd.DataFrame, categorical: Sequence[str], numeric: Sequence[str], seed: int) -> dict[str, Any]:
    X = frame[list(categorical) + list(numeric)]
    y = frame[TARGET].to_numpy(dtype=int)
    train_idx, test_idx = train_test_split(np.arange(len(frame)), test_size=0.2, stratify=y, random_state=seed)
    model = _make_logistic(categorical, numeric, seed)
    model.fit(X.iloc[train_idx], y[train_idx])
    p = model.predict_proba(X.iloc[test_idx])[:, 1]
    return {
        "metrics": metric_dict(y[test_idx], p),
        "n_train": int(len(train_idx)),
        "n_test": int(len(test_idx)),
        "split": {"strategy": "stratified-holdout", "test_size": 0.2, "seed": seed},
    }


def bootstrap_metrics(y: np.ndarray, p: np.ndarray, seed: int, reps: int = 500) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    values = {name: [] for name in ("roc_auc", "average_precision", "brier", "log_loss")}
    n = len(y)
    for _ in range(reps):
        idx = rng.integers(0, n, size=n)
        # A degenerate resample cannot define AUC/AP.  Re-draw only that
        # replicate; with n=7043 this branch is practically never reached.
        if len(np.unique(y[idx])) < 2:
            continue
        metrics = metric_dict(y[idx], p[idx])
        for key in values:
            values[key].append(metrics[key])
    result: dict[str, Any] = {"replicates_requested": reps, "replicates_used": len(values["roc_auc"]), "confidence": 0.95}
    for key, series in values.items():
        arr = np.asarray(series, dtype=float)
        result[key] = {
            "point": float(metric_dict(y, p)[key]),
            "lower": float(np.quantile(arr, 0.025)),
            "upper": float(np.quantile(arr, 0.975)),
        }
    return result


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return (float("nan"), float("nan"))
    phat = successes / total
    denom = 1.0 + z * z / total
    centre = (phat + z * z / (2 * total)) / denom
    half = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    values = np.asarray(p_values, dtype=float)
    order = np.argsort(values)
    adjusted = np.empty(len(values), dtype=float)
    running = 1.0
    for rank in range(len(values), 0, -1):
        index = order[rank - 1]
        running = min(running, values[index] * len(values) / rank)
        adjusted[index] = min(1.0, running)
    return adjusted.tolist()


def q1_effects(frame: pd.DataFrame) -> dict[str, Any]:
    y = frame[TARGET].to_numpy(dtype=int)
    overall = float(y.mean())
    categorical_rows: list[dict[str, Any]] = []
    raw_p: list[float] = []
    for column in CATEGORICAL:
        table = pd.crosstab(frame[column], frame[TARGET])
        from scipy.stats import chi2_contingency

        if table.shape[0] > 1 and table.shape[1] > 1:
            chi2, p_value, dof, _ = chi2_contingency(table)
            n = table.to_numpy().sum()
            phi2 = chi2 / n if n else 0.0
            r, k = table.shape
            correction = max(0.0, phi2 - ((k - 1) * (r - 1)) / max(1, n - 1))
            denom = min(k - 1, r - 1)
            v = math.sqrt(correction / denom) if denom else 0.0
        else:
            chi2, p_value, dof, v = 0.0, 1.0, 0, 0.0
        raw_p.append(float(p_value))
        categorical_rows.append(
            {"feature": column, "levels": int(table.shape[0]), "chi2": float(chi2), "p_value": float(p_value), "dof": int(dof), "cramers_v": float(v)}
        )
    q_values = benjamini_hochberg(raw_p)
    for row, q_value in zip(categorical_rows, q_values):
        row["q_value_bh"] = float(q_value)
        row["fdr_05"] = bool(q_value <= 0.05)

    group_rows: list[dict[str, Any]] = []
    for column in CATEGORICAL:
        grouped = frame.groupby(column, dropna=False)[TARGET].agg(n="size", churn_count="sum", churn_rate="mean").reset_index()
        for item in grouped.to_dict("records"):
            n = int(item["n"])
            if n < 30:
                continue
            low, high = wilson_interval(int(item["churn_count"]), n)
            rate = float(item["churn_rate"])
            group_rows.append(
                {
                    "feature": column,
                    "level": str(item[column]),
                    "n": n,
                    "churn_count": int(item["churn_count"]),
                    "churn_rate": rate,
                    "wilson95_low": low,
                    "wilson95_high": high,
                    "risk_ratio_vs_overall": float(rate / overall) if overall else None,
                    "rate_diff": float(rate - overall),
                }
            )
    numeric_rows: list[dict[str, Any]] = []
    for column in NUMERIC:
        stay = frame.loc[frame[TARGET] == 0, column].to_numpy(dtype=float)
        churn = frame.loc[frame[TARGET] == 1, column].to_numpy(dtype=float)
        statistic, p_value = mannwhitneyu(churn, stay, alternative="two-sided")
        numeric_rows.append(
            {
                "feature": column,
                "churn_median": float(np.median(churn)),
                "stay_median": float(np.median(stay)),
                "churn_mean": float(np.mean(churn)),
                "stay_mean": float(np.mean(stay)),
                "mann_whitney_u": float(statistic),
                "p_value": float(p_value),
            }
        )
    numeric_q = benjamini_hochberg([row["p_value"] for row in numeric_rows])
    for row, q_value in zip(numeric_rows, numeric_q):
        row["q_value_bh"] = float(q_value)
        row["fdr_05"] = bool(q_value <= 0.05)
    return {
        "overall_churn_rate": overall,
        "categorical": sorted(categorical_rows, key=lambda row: row["cramers_v"], reverse=True),
        "numeric": numeric_rows,
        "groups": sorted(group_rows, key=lambda row: row["churn_rate"], reverse=True),
    }


def policy_table(y: np.ndarray, p: np.ndarray, cost: float, success: float, loss: float) -> list[dict[str, Any]]:
    threshold = cost / (success * loss)
    order = np.argsort(-p)
    masks: list[tuple[str, np.ndarray]] = [
        ("不干预", np.zeros(len(p), dtype=bool)),
        ("全员干预", np.ones(len(p), dtype=bool)),
        (f"经济阈值 p≥{threshold:.4f}", p >= threshold),
    ]
    for ratio in (0.01, 0.05, 0.10, 0.20, 0.30):
        k = max(1, int(len(p) * ratio))
        mask = np.zeros(len(p), dtype=bool)
        mask[order[:k]] = True
        masks.append((f"风险排序前 {ratio:.0%}", mask))
    rows: list[dict[str, Any]] = []
    for name, mask in masks:
        net_each = p * success * loss - cost
        expected_avoided = float(np.sum(p[mask] * success * loss))
        intervention_cost = float(mask.sum() * cost)
        rows.append(
            {
                "strategy": name,
                "selected_count": int(mask.sum()),
                "selected_rate": float(mask.mean()),
                "observed_churn_rate_in_selected": float(y[mask].mean()) if mask.any() else None,
                "mean_predicted_risk_in_selected": float(p[mask].mean()) if mask.any() else None,
                "expected_avoided_loss": expected_avoided,
                "intervention_cost": intervention_cost,
                "expected_net_benefit": float(expected_avoided - intervention_cost),
                "min_selected_net": float(net_each[mask].min()) if mask.any() else None,
                "assumption": "p为关联风险；q为将要流失客户的平均条件成功率，不是个体uplift",
            }
        )
    return rows


def bootstrap_policy(y: np.ndarray, p: np.ndarray, cost: float, success: float, loss: float, seed: int, reps: int = 500) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    threshold = cost / (success * loss)
    masks = {
        "economic_threshold": p >= threshold,
        "top_10_percent": np.zeros(len(p), dtype=bool),
        "top_20_percent": np.zeros(len(p), dtype=bool),
    }
    order = np.argsort(-p)
    masks["top_10_percent"][order[: max(1, int(0.10 * len(p)))]] = True
    masks["top_20_percent"][order[: max(1, int(0.20 * len(p)))]] = True
    out: dict[str, Any] = {}
    for name, mask in masks.items():
        values: list[float] = []
        for _ in range(reps):
            idx = rng.integers(0, len(p), size=len(p))
            selected = mask[idx]
            values.append(float(np.sum((p[idx][selected] * success * loss) - cost)))
        point = float(np.sum((p[mask] * success * loss) - cost))
        out[name] = {
            "selected_count": int(mask.sum()),
            "point": point,
            "lower": float(np.quantile(values, 0.025)),
            "upper": float(np.quantile(values, 0.975)),
        }
    return {"replicates": reps, "confidence": 0.95, "policies": out}


def imputation_ablation(frame: pd.DataFrame, seed: int) -> dict[str, Any]:
    """Compare the structural-zero rule with a deliberately conservative alternative."""
    original = frame.copy()
    alternative = frame.copy()
    blank_mask = alternative["tenure_months"].eq(0) & alternative["total_charges"].eq(0)
    # The cleaned frame has already encoded the 11 structural blanks as zero.
    # Replacing only those rows by the non-zero median creates a transparent,
    # intentionally pessimistic comparator rather than a hidden preprocessing.
    nonzero = alternative.loc[alternative["total_charges"] > 0, "total_charges"]
    alternative.loc[blank_mask, "total_charges"] = float(nonzero.median()) if len(nonzero) else 0.0
    results: dict[str, Any] = {}
    for label, candidate in (("structural_zero", original), ("median_for_structural_blank", alternative)):
        p, summary, _ = repeated_oof(candidate, CATEGORICAL, NUMERIC, seed=seed, splits=5, repeats=2)
        results[label] = {"metrics": summary, "rows_changed": int(blank_mask.sum()) if label != "structural_zero" else 0}
    return results


def latin_hypercube(n: int, dimensions: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    result = np.empty((n, dimensions), dtype=float)
    for j in range(dimensions):
        result[:, j] = (rng.permutation(n) + rng.random(n)) / n
    return result


def stress_analysis(frame: pd.DataFrame, p: np.ndarray, seed: int, samples: int = 256) -> dict[str, Any]:
    """Stress envelope; all ranges are hypotheses because Q4 has no external series."""
    contracts = frame["contract"].astype(str).to_numpy()
    tenure = frame["tenure_months"].to_numpy(dtype=float)
    base_logit = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
    # u = competitor intensity, m = macro intensity, q = success rate,
    # c = intervention cost, l = loss.  Bounds are deliberately broad and
    # recorded as hypothetical scenario parameters, never fitted effects.
    unit = latin_hypercube(samples, 5, seed)
    u = 0.0 + 0.50 * unit[:, 0]
    m = 0.0 + 0.30 * unit[:, 1]
    q = 0.25 + 0.10 * unit[:, 2]
    c = 150.0 + 30.0 * unit[:, 3]
    l = 1800.0 + 400.0 * unit[:, 4]
    contract_multiplier = np.select(
        [contracts == "Month-to-month", contracts == "One year", contracts == "Two year"],
        [1.0, 0.50, 0.20],
        default=0.70,
    )
    short_multiplier = (tenure < 12).astype(float)
    robust_score = np.full(len(frame), np.inf, dtype=float)
    scenario_rows: list[dict[str, Any]] = []
    for idx in range(samples):
        delta = u[idx] * contract_multiplier + m[idx] * (0.75 + 0.25 * short_multiplier)
        shifted = 1.0 / (1.0 + np.exp(-(base_logit + delta)))
        net = shifted * q[idx] * l[idx] - c[idx]
        robust_score = np.minimum(robust_score, net)
        if idx in {0, samples // 2, samples - 1}:
            scenario_rows.append(
                {
                    "scenario_id": f"lhs-{idx + 1:03d}",
                    "competitor_logit_intensity": float(u[idx]),
                    "macro_logit_intensity": float(m[idx]),
                    "success_rate": float(q[idx]),
                    "cost": float(c[idx]),
                    "loss": float(l[idx]),
                    "predicted_churn_rate": float(shifted.mean()),
                    "positive_net_count": int((net > 0).sum()),
                    "total_positive_net": float(np.maximum(net, 0).sum()),
                }
            )
    robust_positive = robust_score > 0
    # Exact boundary search for the policy assumptions: when q falls below
    # C/(pL), an individually positive intervention becomes non-positive.
    threshold_extreme = 180.0 / (0.25 * 1800.0)
    return {
        "schema": "stress-envelope/v1",
        "assumptions": {
            "competitor_logit_range": [0.0, 0.50],
            "macro_logit_range": [0.0, 0.30],
            "success_rate_range": [0.25, 0.35],
            "cost_range": [150.0, 180.0],
            "loss_range": [1800.0, 2200.0],
            "contract_multiplier": {"Month-to-month": 1.0, "One year": 0.50, "Two year": 0.20},
            "short_tenure_extra_multiplier": "0.75 + 0.25*I(tenure<12)",
            "status": "HYPOTHESIS",
        },
        "sampling": {"method": "latin-hypercube", "samples": samples, "seed": seed, "dimensions": ["u", "m", "q", "C", "L"]},
        "representative_scenarios": scenario_rows,
        "robust_policy": {
            "selected_count": int(robust_positive.sum()),
            "selected_rate": float(robust_positive.mean()),
            "lower_bound_sum_min_person_net": float(np.maximum(robust_score[robust_positive], 0).sum()),
            "minimum_person_net_all_customers": float(robust_score.min()),
            "median_person_net_lower_bound": float(np.median(robust_score)),
        },
        "counterexample_boundary": {
            "worst_case_threshold": threshold_extreme,
            "interpretation": "在给定的最不利参数角点，p低于该值时不应自动干预；此为边界计算，不是市场事实。",
        },
    }


def save_figures(q1: Mapping[str, Any], calibration: Mapping[str, Any], policies: Sequence[Mapping[str, Any]], stress: Mapping[str, Any], output: Path) -> list[str]:
    """Create compact evidence figures from the same frozen result objects."""
    set_chinese_font()
    paths: list[str] = []
    # Q1 effect-size ranking.
    categorical = list(q1["categorical"])[::-1]
    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    ax.barh([DISPLAY_NAMES.get(item["feature"], item["feature"]) for item in categorical], [item["cramers_v"] for item in categorical], color="#167c80")
    ax.set_xlabel("修正 Cramér's V")
    ax.set_title("Q1 类别字段关联强度（BH-FDR 已登记）")
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    path = output / "q1_effect_sizes.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path.name)

    # Q2 quantile calibration curve.
    bins = list(calibration["quantile"]["bins"])
    fig, ax = plt.subplots(figsize=(5.8, 5.0))
    ax.plot([0, 1], [0, 1], "--", color="#94a3b8", linewidth=1)
    ax.plot([item["mean_predicted"] for item in bins], [item["observed_rate"] for item in bins], "o-", color="#a44435")
    ax.set_xlabel("平均预测概率")
    ax.set_ylabel("观测流失率")
    ax.set_title("Q2 OOF 概率校准（等频十组）")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    path = output / "q2_calibration.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path.name)

    # Q3 capacity/value curve.
    selected = [item for item in policies if item["selected_count"] > 0]
    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    ax.plot([item["selected_rate"] * 100 for item in selected], [item["expected_net_benefit"] for item in selected], "o-", color="#167c80")
    for item in selected:
        ax.annotate(item["strategy"].replace("风险排序前 ", ""), (item["selected_rate"] * 100, item["expected_net_benefit"]), fontsize=8, xytext=(3, 3), textcoords="offset points")
    ax.axhline(0, color="#334155", linewidth=0.8)
    ax.set_xlabel("干预覆盖率（%）")
    ax.set_ylabel("期望净收益（元）")
    ax.set_title("Q3 经济阈值与容量策略")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    path = output / "q3_policy_curve.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path.name)

    # Q4 scenario envelope summary.
    rows = list(stress["representative_scenarios"])
    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    ax.scatter([item["predicted_churn_rate"] * 100 for item in rows], [item["total_positive_net"] for item in rows], s=70, color="#a44435")
    for item in rows:
        ax.annotate(item["scenario_id"], (item["predicted_churn_rate"] * 100, item["total_positive_net"]), fontsize=8, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("情景预测流失率（%）")
    ax.set_ylabel("正收益集合期望净收益（元）")
    ax.set_title("Q4 拉丁超立方压力情景代表点")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    path = output / "q4_stress_envelope.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    paths.append(path.name)
    return paths


def independent_arithmetic_check(p: np.ndarray, cost: float, success: float, loss: float) -> dict[str, Any]:
    """A tiny second implementation of Q3 arithmetic, independent of policy_table."""
    threshold = cost / (success * loss)
    selected = np.flatnonzero(p >= threshold)
    expected = float(np.sum(p[selected]) * success * loss - len(selected) * cost)
    return {
        "threshold": float(threshold),
        "selected_count": int(len(selected)),
        "expected_net": expected,
        "formula": "sum(p_i)*q*L-|S|*C",
    }


def build_model_route() -> dict[str, Any]:
    return {
        "schema_version": "model-route/v2",
        "status": "VERIFIED",
        "routes": [
            {
                "question_id": "Q1",
                "structural_cues": ["二元标签", "类别分组", "需要因素关系和画像"],
                "baseline": {"method_id": "descriptive-statistical-baseline", "rationale": "先给总体率、分母和分组率", "assumptions": ["同一截面标签口径一致"], "metrics": ["rate", "Wilson95"]},
                "primary": {"method_id": "schema-provenance-audit + chi-square + Cramer's V + Mann-Whitney", "rationale": "同时报告显著性与效应量，避免大样本只看p值", "assumptions": ["类别/数值字段的观测粒度一致"], "equations": ["q1-group-rate", "q1-cramers"], "constraints": ["不写因果"], "expected_outputs": ["BH校正表", "Wilson区间", "交叉画像"]},
                "fallbacks": [{"method_id": "group-summary-reconcile", "trigger": "字段域或样本量不足"}],
                "prohibited_shortcuts": ["只按p值排序", "把群体差异写成干预效果"],
                "validation_plan": ["row-count-reconcile", "multiple-comparison", "denominator-check"],
                "evidence_refs": ["src-review-2023", "src-prize-paper-school-2026"],
            },
            {
                "question_id": "Q2",
                "structural_cues": ["有标签", "客户级风险判定", "题面指定合同/在网/费用/增值服务"],
                "baseline": {"method_id": "majority-class + core-rule", "rationale": "提供可解释下界并作为消融对照", "assumptions": ["部署只使用画像字段"], "metrics": ["ROC-AUC", "AP", "Brier", "log-loss"]},
                "primary": {"method_id": "generalized-linear-model (reference-coded logistic)", "rationale": "与题面变量对应、输出概率且可解释；重复OOF隔离预处理", "assumptions": ["横截面关联模型", "训练折内插补/缩放"], "equations": ["q2-logistic", "q2-fit"], "constraints": ["无时间字段，不能宣称时间外推"], "solver_config": {"C": 1.0, "solver": "lbfgs", "max_iter": 4000, "repeated_stratified_folds": "3x5"}, "expected_outputs": ["core/full对照", "bootstrap95", "calibration", "effect directions"]},
                "fallbacks": [{"method_id": "gradient-boosting", "trigger": "非线性残差显著且通过隔离验证"}, {"method_id": "conservative-baseline", "trigger": "未来批次漂移或校准失败"}],
                "prohibited_shortcuts": ["用全样本拟合概率评估自己", "用0.5替代经济阈值", "将系数写成因果"],
                "validation_plan": ["repeated-cross-validation", "holdout", "calibration-coverage-check", "imputation-ablation"],
                "evidence_refs": ["src-review-2021", "src-review-2023", "src-algorithm-index"],
            },
            {
                "question_id": "Q3",
                "structural_cues": ["成本/成功率/损失已给定", "二元干预决策", "可分离收益"],
                "baseline": {"method_id": "all-or-none-policy", "rationale": "全员/不干预是透明运营基线", "assumptions": ["q和L按题面给定"], "metrics": ["expected-net"]},
                "primary": {"method_id": "robust-optimization (separable economic threshold)", "rationale": "逐人净收益可分离，阈值与容量排序有交换论证", "assumptions": ["p为关联风险，q为条件平均成功率"], "equations": ["q3-person-net", "q3-threshold"], "constraints": ["成本、成功率、损失单位一致"], "expected_outputs": ["threshold", "capacity curve", "bootstrap policy interval"]},
                "fallbacks": [{"method_id": "risk-ranking", "trigger": "仅有固定容量"}],
                "prohibited_shortcuts": ["把观测流失率当挽留成功率", "把期望净收益当已实现利润"],
                "validation_plan": ["independent-arithmetic-check", "parameter-sensitivity", "policy-bootstrap"],
                "evidence_refs": ["src-review-2023", "src-review-2020"],
            },
            {
                "question_id": "Q4",
                "structural_cues": ["竞争/宏观变化", "策略稳健性", "缺少外部时间序列"],
                "baseline": {"method_id": "one-factor-scenarios", "rationale": "先逐个改变冲击方向并记录边界", "assumptions": ["外部冲击参数为假设"], "metrics": ["churn-rate", "positive-net-count"]},
                "primary": {"method_id": "robust-optimization + latin-hypercube-scenario-simulation", "rationale": "把缺失外部数据转化为显式不确定集合，报告最坏下界而非伪造弹性", "assumptions": ["参数区间是假设并需新数据校准"], "equations": ["q4-shift", "q4-robust"], "constraints": ["不声称识别竞争价格效应"], "expected_outputs": ["scenario envelope", "robust set", "counterexample boundary"]},
                "fallbacks": [{"method_id": "conservative-baseline", "trigger": "外部区间无法由Owner确认"}],
                "prohibited_shortcuts": ["无来源指定价格弹性", "把情景均值当事实", "把逐人下界当置信区间"],
                "validation_plan": ["uncertainty-set-sweep", "boundary-check", "assumption-red-team"],
                "evidence_refs": ["src-review-2023", "src-prize-paper-school-2026"],
            },
        ],
    }


def run(input_path: Path, output: Path, seed: int = DEFAULT_SEED) -> dict[str, Any]:
    started = time.time()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    raw, encoding = read_csv_detect(input_path)
    frame, quality = clean_data(raw)
    quality["encoding"] = encoding
    y = frame[TARGET].to_numpy(dtype=int)

    q1 = q1_effects(frame)
    core_p, core_metrics, core_folds = repeated_oof(frame, CORE_CATEGORICAL, CORE_NUMERIC, seed, splits=5, repeats=3)
    full_p, full_metrics, full_folds = repeated_oof(frame, CATEGORICAL, NUMERIC, seed, splits=5, repeats=3)
    full_holdout = holdout_route(frame, CATEGORICAL, NUMERIC, seed)
    majority_rate = float(y.mean())
    majority_metrics = {"roc_auc": 0.5, "average_precision": majority_rate, "brier": float(np.mean((y - majority_rate) ** 2)), "log_loss": float(-(y.mean() * math.log(majority_rate) + (1 - y.mean()) * math.log(1 - majority_rate)))}
    full_bootstrap = bootstrap_metrics(y, full_p, seed + 101, reps=500)
    calibration = expected_calibration_error(y, full_p, bins=10)
    calibration["quantile"] = quantile_calibration_error(y, full_p, bins=10)
    calibration["oof_probability_summary"] = {"min": float(full_p.min()), "max": float(full_p.max()), "mean": float(full_p.mean())}

    cost, success, loss = 150.0, 0.35, 2000.0
    policies = policy_table(y, full_p, cost, success, loss)
    policy_bootstrap_result = bootstrap_policy(y, full_p, cost, success, loss, seed + 202, reps=500)
    independent_check = independent_arithmetic_check(full_p, cost, success, loss)
    imputation = imputation_ablation(frame, seed + 303)
    stress = stress_analysis(frame, full_p, seed + 404, samples=256)
    intersections = make_intersection_summary(frame)

    # Save aggregate evidence.  A local customer-level file is intentionally
    # kept outside the committed package; it is useful only for Owner review.
    pd.DataFrame(q1["categorical"]).to_csv(output / "q1_categorical_effects.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(q1["numeric"]).to_csv(output / "q1_numeric_effects.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(q1["groups"]).to_csv(output / "q1_group_rates_ci.csv", index=False, encoding="utf-8-sig")
    intersections.to_csv(output / "q1_intersections.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(core_folds).to_csv(output / "q2_core_fold_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(full_folds).to_csv(output / "q2_full_fold_metrics.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(policies).to_csv(output / "q3_policy_table.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame({"risk_probability_oof": full_p, "observed_churn": y}).to_csv(output / "risk_scores_local.csv", index=False, encoding="utf-8-sig")
    write_json(output / "q2_calibration.json", calibration)
    write_json(output / "q3_policy_bootstrap.json", policy_bootstrap_result)
    write_json(output / "q3_independent_arithmetic_check.json", independent_check)
    write_json(output / "imputation_ablation.json", imputation)
    write_json(output / "q4_stress_envelope.json", stress)
    write_json(output / "model_route.json", build_model_route())
    figure_files = save_figures(q1, calibration, policies, stress, output)

    summary = {
        "schema": SCHEMA,
        "status": "READY_FOR_REVIEW",
        "input": {"path": "<owner-attachment>/校赛B题附件.csv", "encoding": encoding, "sha256": sha256_file(input_path)},
        "quality": quality,
        "q1": {"top_categorical": q1["categorical"][:10], "top_numeric": q1["numeric"], "top_groups": q1["groups"][:12]},
        "q2": {
            "baseline_majority": {"churn_rate": majority_rate, "metrics": majority_metrics},
            "core_logistic_repeated_oof": core_metrics,
            "full_logistic_repeated_oof": full_metrics,
            "full_logistic_holdout": full_holdout,
            "bootstrap95": full_bootstrap,
            "calibration": {"ece": calibration["ece"], "max_calibration_error": calibration["max_calibration_error"]},
            "quantile_calibration": {"ece": calibration["quantile"]["ece"], "max_calibration_error": calibration["quantile"]["max_calibration_error"]},
        },
        "q3": {"constants": {"cost": cost, "success_rate": success, "loss": loss, "break_even_probability": cost / (success * loss)}, "policies": policies, "bootstrap": policy_bootstrap_result, "independent_check": independent_check},
        "q4": stress,
        "figures": figure_files,
        "reproducibility": {"seed": seed, "python": sys.version.split()[0], "platform": platform.platform(), "packages": package_versions()},
        "skill_route": ["charter-and-safety", "scope-lock", "question-decomposition", "data-and-evidence", "model-routing", "mathematical-derivation", "solver-reproducibility", "validation-and-adversarial-review", "paper-and-typesetting", "defense-and-release", "workflow-cumcm-main"],
        "limitations": [
            "附件为横截面，重复分层CV不能替代未来时间回测。",
            "没有触达/优惠/续留反事实标签，p和q不能组成个体uplift。",
            "Q4参数区间是压力假设，不是竞争价格或宏观弹性的估计。",
            "官方校赛论文格式、匿名细则和页数尚未由当届通知锁定。",
        ],
    }
    write_json(output / "summary_v2.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    result = run(args.input.resolve(), args.output.resolve(), args.seed)
    print(json.dumps({"status": "PASS", "schema": SCHEMA, "rows": result["quality"]["rows"], "full_oof_auc": result["q2"]["full_logistic_repeated_oof"]["roc_auc"], "economic_threshold": result["q3"]["constants"]["break_even_probability"], "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
