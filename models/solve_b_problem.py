"""可复算求解：校赛 B 题《电信客户流失分析与挽留策略》。

本脚本只读取命令行指定的原始 CSV，不把原始数据复制到仓库。它生成
聚合统计、模型指标、政策模拟、压力情景和论文图表；客户编码只留在
本地运行目录的风险明细中，论文与提交包不引用该明细。

模型边界：数据是观测期横截面，因此 Logistic/树模型给出关联性风险
排序，不宣称因果 uplift。题目给出的 35% 挽留成功率用于期望值政策
模拟；Q4 的外部冲击参数是明确标注的压力假设，不能解释为已估计的
竞争价格弹性。
"""

from __future__ import annotations

import argparse
import json
import math
import warnings
from pathlib import Path
from typing import Any, Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_predict,
    cross_val_score,
    train_test_split,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


CHINESE_TO_ENGLISH = {
    "客户编码": "customer_id",
    "性别": "gender",
    "是否为老年人": "senior",
    "是否有伴侣": "partner",
    "是否有家属": "dependents",
    "在网时长（月）": "tenure_months",
    "是否开通电话服务": "phone_service",
    "是否开通多条线路": "multiple_lines",
    "互联网服务类型": "internet_service",
    "是否开通在线安全": "online_security",
    "是否开通在线备份": "online_backup",
    "是否开通设备保护": "device_protection",
    "是否开通技术支持": "tech_support",
    "是否开通电视流媒体": "streaming_tv",
    "是否开通电影流媒体": "streaming_movies",
    "合同类型": "contract",
    "是否使用电子账单": "paperless_billing",
    "支付方式": "payment_method",
    "月费用": "monthly_charges",
    "总费用": "total_charges",
    "是否流失": "churn",
}

CATEGORICAL = [
    "gender",
    "senior",
    "partner",
    "dependents",
    "phone_service",
    "multiple_lines",
    "internet_service",
    "online_security",
    "online_backup",
    "device_protection",
    "tech_support",
    "streaming_tv",
    "streaming_movies",
    "contract",
    "paperless_billing",
    "payment_method",
]
NUMERIC = ["tenure_months", "monthly_charges", "total_charges"]
TARGET = "churn"
ID = "customer_id"

FEATURE_DISPLAY = {
    "contract": "合同类型",
    "internet_service": "互联网服务",
    "payment_method": "支付方式",
    "tenure_band": "在网时长",
    "monthly_charge_quintile": "月费用分位",
    "total_charge_quintile": "总费用分位",
    "senior": "老年人",
    "paperless_billing": "电子账单",
    "online_security": "在线安全",
    "tech_support": "技术支持",
    "online_backup": "在线备份",
    "device_protection": "设备保护",
    "streaming_tv": "电视流媒体",
    "streaming_movies": "电影流媒体",
    "multiple_lines": "多条线路",
    "phone_service": "电话服务",
    "dependents": "家属",
    "partner": "伴侣",
    "gender": "性别",
    "tenure_months": "在网时长（月）",
    "monthly_charges": "月费用",
    "total_charges": "总费用",
}

LEVEL_DISPLAY = {
    "Month-to-month": "月付",
    "One year": "一年",
    "Two year": "两年",
    "Fiber optic": "光纤",
    "Electronic check": "电子支票",
    "Mailed check": "邮寄支票",
    "Bank transfer (automatic)": "自动转账",
    "Credit card (automatic)": "自动信用卡",
    "DSL": "DSL",
    "Senior": "老年人",
}


def display_feature_token(token: str) -> str:
    """Map model feature names to compact Chinese labels for figures only."""
    text = str(token)
    if text.startswith("num__"):
        return FEATURE_DISPLAY.get(text[5:], text[5:])
    if text.startswith("cat__"):
        rest = text[5:]
        for feature in sorted(FEATURE_DISPLAY, key=len, reverse=True):
            prefix = feature + "_"
            if rest.startswith(prefix):
                level = rest[len(prefix):]
                return f"{FEATURE_DISPLAY[feature]}：{LEVEL_DISPLAY.get(level, level)}"
    return LEVEL_DISPLAY.get(text, text)


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (Path,)):
        return str(value)
    if isinstance(value, (np.ndarray,)):
        return value.tolist()
    if pd.isna(value):
        return None
    raise TypeError(f"not JSON serializable: {type(value)!r}")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def read_csv_detect(path: Path) -> tuple[pd.DataFrame, str]:
    errors: list[str] = []
    for encoding in ("utf-8-sig", "gb18030", "gbk", "utf-16"):
        try:
            frame = pd.read_csv(path, encoding=encoding, keep_default_na=False)
            return frame, encoding
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            errors.append(f"{encoding}: {exc}")
    raise ValueError("CSV 编码/结构无法识别；" + " | ".join(errors))


def clean_data(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    missing_columns = sorted(set(CHINESE_TO_ENGLISH) - set(raw.columns))
    if missing_columns:
        raise ValueError(f"缺少题面字段: {missing_columns}")
    frame = raw.rename(columns=CHINESE_TO_ENGLISH).copy()
    for column in frame.columns:
        if frame[column].dtype == object:
            frame[column] = frame[column].astype(str).str.strip()

    frame["tenure_months"] = pd.to_numeric(frame["tenure_months"], errors="coerce")
    frame["monthly_charges"] = pd.to_numeric(frame["monthly_charges"], errors="coerce")
    raw_total = frame["total_charges"].astype(str).str.strip()
    blank_total = raw_total.eq("")
    frame["total_charges"] = pd.to_numeric(raw_total.replace("", np.nan), errors="coerce")
    zero_tenure_blank = blank_total & frame["tenure_months"].eq(0)
    frame.loc[zero_tenure_blank, "total_charges"] = 0.0
    remaining_total_missing = int(frame["total_charges"].isna().sum())
    if remaining_total_missing:
        frame["total_charges"] = frame["total_charges"].fillna(frame["total_charges"].median())

    frame[TARGET] = frame[TARGET].map({"是": 1, "否": 0})
    if frame[TARGET].isna().any():
        raise ValueError("是否流失存在无法映射的取值")
    frame[TARGET] = frame[TARGET].astype(int)

    quality = {
        "rows": int(len(frame)),
        "columns": int(len(frame.columns)),
        "duplicate_rows": int(frame.duplicated().sum()),
        "duplicate_customer_ids": int(frame[ID].duplicated().sum()),
        "target_count": {"churn": int(frame[TARGET].sum()), "stay": int((1 - frame[TARGET]).sum())},
        "churn_rate": float(frame[TARGET].mean()),
        "blank_total_charges": int(blank_total.sum()),
        "blank_total_imputed_as_zero": int(zero_tenure_blank.sum()),
        "remaining_total_imputed_as_median": remaining_total_missing,
        "numeric_ranges": {
            column: {
                "min": float(frame[column].min()),
                "max": float(frame[column].max()),
                "median": float(frame[column].median()),
            }
            for column in NUMERIC
        },
        "categorical_levels": {column: sorted(frame[column].dropna().unique().tolist()) for column in CATEGORICAL},
    }
    return frame, quality


def cramers_v(table: pd.DataFrame) -> float:
    if table.empty or table.shape[0] < 2 or table.shape[1] < 2:
        return 0.0
    chi2, _, _, _ = chi2_contingency(table)
    n = table.to_numpy().sum()
    if n == 0:
        return 0.0
    phi2 = chi2 / n
    r, k = table.shape
    correction = max(0.0, phi2 - ((k - 1) * (r - 1)) / max(1, n - 1))
    denom = min(k - 1, r - 1)
    return float(math.sqrt(correction / denom)) if denom else 0.0


def categorical_associations(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    overall = float(frame[TARGET].mean())
    rows: list[dict[str, Any]] = []
    for column in CATEGORICAL:
        table = pd.crosstab(frame[column], frame[TARGET])
        if table.shape[0] > 1 and table.shape[1] > 1:
            chi2, p_value, dof, _ = chi2_contingency(table)
        else:
            chi2, p_value, dof = 0.0, 1.0, 0
        rows.append({
            "feature": column,
            "levels": int(table.shape[0]),
            "chi2": float(chi2),
            "p_value": float(p_value),
            "dof": int(dof),
            "cramers_v": cramers_v(table),
        })

    group_rows: list[dict[str, Any]] = []
    for column in CATEGORICAL:
        grouped = frame.groupby(column, dropna=False)[TARGET].agg(n="size", churn_rate="mean").reset_index()
        for row in grouped.to_dict("records"):
            n = int(row["n"])
            rate = float(row["churn_rate"])
            if n < 30:
                continue
            value = row[column]
            group_rows.append({
                "feature": column,
                "level": str(value),
                "n": n,
                "churn_rate": rate,
                "risk_ratio_vs_overall": float(rate / overall) if overall else None,
                "rate_diff": float(rate - overall),
            })

    tenure_bins = pd.cut(
        frame["tenure_months"],
        bins=[-1, 0, 6, 12, 24, 48, 72],
        labels=["0", "1-6", "7-12", "13-24", "25-48", "49-72"],
        include_lowest=True,
    )
    monthly_bins = pd.qcut(frame["monthly_charges"], q=5, duplicates="drop")
    total_bins = pd.qcut(frame["total_charges"], q=5, duplicates="drop")
    for feature, series in (("tenure_band", tenure_bins), ("monthly_charge_quintile", monthly_bins), ("total_charge_quintile", total_bins)):
        grouped = frame.assign(_band=series).groupby("_band", observed=False)[TARGET].agg(n="size", churn_rate="mean").reset_index()
        for row in grouped.to_dict("records"):
            group_rows.append({
                "feature": feature,
                "level": str(row["_band"]),
                "n": int(row["n"]),
                "churn_rate": float(row["churn_rate"]),
                "risk_ratio_vs_overall": float(row["churn_rate"] / overall) if overall else None,
                "rate_diff": float(row["churn_rate"] - overall),
            })
    return pd.DataFrame(rows).sort_values("cramers_v", ascending=False), pd.DataFrame(group_rows).sort_values("churn_rate", ascending=False)


def make_encoder() -> OneHotEncoder:
    """Create a reference-coded encoder for interpretable logistic effects.

    Dropping the first level is deliberate: with an intercept, a full dummy
    basis is rank deficient and each reported coefficient would depend on an
    arbitrary regularisation convention.  Reference coding lets the paper
    state an odds-ratio comparison against the first (lexicographically
    stable) level of each categorical field.  ``handle_unknown`` still keeps
    scoring safe when a future batch contains a novel level.
    """
    try:
        return OneHotEncoder(handle_unknown="ignore", drop="first", sparse_output=False)
    except TypeError:  # pragma: no cover - compatibility with older sklearn
        return OneHotEncoder(handle_unknown="ignore", drop="first", sparse=False)


def make_logistic() -> Pipeline:
    transformer = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), NUMERIC),
            ("cat", Pipeline([("impute", SimpleImputer(strategy="most_frequent")), ("onehot", make_encoder())]), CATEGORICAL),
        ],
        remainder="drop",
    )
    return Pipeline([
        ("preprocess", transformer),
        ("model", LogisticRegression(max_iter=3000, C=1.0, solver="lbfgs", random_state=42)),
    ])


def metrics(y_true: np.ndarray, probabilities: np.ndarray, threshold: float = 0.5) -> dict[str, float]:
    predictions = (probabilities >= threshold).astype(int)
    return {
        "roc_auc": float(roc_auc_score(y_true, probabilities)),
        "average_precision": float(average_precision_score(y_true, probabilities)),
        "brier": float(brier_score_loss(y_true, probabilities)),
        "log_loss": float(log_loss(y_true, probabilities, labels=[0, 1])),
        "accuracy_at_0_5": float(accuracy_score(y_true, predictions)),
        "precision_at_0_5": float(precision_score(y_true, predictions, zero_division=0)),
        "recall_at_0_5": float(recall_score(y_true, predictions, zero_division=0)),
        "f1_at_0_5": float(f1_score(y_true, predictions, zero_division=0)),
    }


def calibration_table(y: np.ndarray, probabilities: np.ndarray, bins: int = 10) -> pd.DataFrame:
    frame = pd.DataFrame({"y": y, "probability": probabilities})
    frame["bin"] = pd.qcut(frame["probability"].rank(method="first"), q=bins, labels=False) + 1
    return frame.groupby("bin", observed=False).agg(
        n=("y", "size"), predicted_rate=("probability", "mean"), observed_rate=("y", "mean")
    ).reset_index()


def fit_models(frame: pd.DataFrame, seed: int) -> dict[str, Any]:
    X = frame[CATEGORICAL + NUMERIC]
    y = frame[TARGET].to_numpy()
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=seed)

    logistic = make_logistic()
    logistic.fit(X_train, y_train)
    logistic_test = logistic.predict_proba(X_test)[:, 1]
    logistic_metrics = metrics(y_test, logistic_test)

    # A nonlinear benchmark on the same fields.  One-hot encoding is fitted
    # from the training split and columns are aligned before the tree model.
    encoded = pd.get_dummies(X, columns=CATEGORICAL, dummy_na=True)
    encoded = encoded.apply(pd.to_numeric, errors="coerce")
    train_index, test_index = train_test_split(np.arange(len(frame)), test_size=0.2, stratify=y, random_state=seed)
    hgb = HistGradientBoostingClassifier(
        max_iter=250, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0, random_state=seed
    )
    train_matrix = encoded.iloc[train_index].copy()
    test_matrix = encoded.iloc[test_index].copy()
    medians = train_matrix.median(numeric_only=True)
    train_matrix = train_matrix.fillna(medians).fillna(0.0)
    test_matrix = test_matrix.fillna(medians).fillna(0.0)
    hgb.fit(train_matrix, y[train_index])
    hgb_test = hgb.predict_proba(test_matrix)[:, 1]
    hgb_metrics = metrics(y[test_index], hgb_test)

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    cv_auc = cross_val_score(make_logistic(), X, y, cv=cv, scoring="roc_auc", n_jobs=1)
    oof = cross_val_predict(make_logistic(), X, y, cv=cv, method="predict_proba", n_jobs=1)[:, 1]
    logistic.fit(X, y)

    transformed_names = list(logistic.named_steps["preprocess"].get_feature_names_out())
    coefficients = logistic.named_steps["model"].coef_[0]
    effects = pd.DataFrame({"feature": transformed_names, "coefficient": coefficients})
    effects["odds_ratio"] = np.exp(effects["coefficient"])
    effects["direction"] = np.where(effects["coefficient"] >= 0, "提高流失风险", "降低流失风险")
    effects["abs_coefficient"] = effects["coefficient"].abs()
    effects = effects.sort_values("coefficient", ascending=False).drop(columns=["abs_coefficient"])

    result = {
        "logistic_holdout": logistic_metrics,
        "hist_gradient_boosting_holdout": hgb_metrics,
        "logistic_cv_roc_auc": {"mean": float(cv_auc.mean()), "std": float(cv_auc.std()), "folds": cv_auc.tolist()},
        "oof_metrics": metrics(y, oof),
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
        "logistic_model": logistic,
        "oof_probability": oof,
        "full_probability": logistic.predict_proba(X)[:, 1],
        "effects": effects,
        "calibration": calibration_table(y, oof),
        "roc": {
            "y_test": y_test,
            "logistic": logistic_test,
            "hgb": hgb_test,
        },
    }
    return result


def evaluate_policy(name: str, selected: np.ndarray, probabilities: np.ndarray, y: np.ndarray, cost: float, success: float, loss: float) -> dict[str, Any]:
    selected = np.asarray(selected, dtype=bool)
    expected_avoided = float(np.sum(probabilities[selected] * success * loss))
    intervention_cost = float(selected.sum() * cost)
    observed_rate = float(y[selected].mean()) if selected.any() else None
    return {
        "strategy": name,
        "selected_count": int(selected.sum()),
        "selected_rate": float(selected.mean()),
        "observed_churn_rate_in_selected": observed_rate,
        "expected_avoided_loss": expected_avoided,
        "intervention_cost": intervention_cost,
        "expected_net_benefit": float(expected_avoided - intervention_cost),
        "assumption": "p 为关联性风险；success 为对将要流失客户的平均条件成功率，非个体 uplift",
    }


def policy_analysis(frame: pd.DataFrame, probabilities: np.ndarray, seed: int) -> dict[str, Any]:
    y = frame[TARGET].to_numpy()
    cost, success, loss = 150.0, 0.35, 2000.0
    threshold = cost / (success * loss)
    policies = [
        evaluate_policy("不干预", np.zeros(len(frame), dtype=bool), probabilities, y, cost, success, loss),
        evaluate_policy("全员干预", np.ones(len(frame), dtype=bool), probabilities, y, cost, success, loss),
        evaluate_policy(f"期望净收益阈值 p≥{threshold:.4f}", probabilities >= threshold, probabilities, y, cost, success, loss),
    ]
    for ratio in (0.01, 0.05, 0.10, 0.20):
        k = max(1, int(len(frame) * ratio))
        order = np.argsort(-probabilities)
        selected = np.zeros(len(frame), dtype=bool)
        selected[order[:k]] = True
        policies.append(evaluate_policy(f"风险排序前 {ratio:.0%}", selected, probabilities, y, cost, success, loss))

    sensitivity_rows = []
    for success_rate in (0.25, 0.30, 0.35, 0.40, 0.45):
        for loss_value in (1500.0, 2000.0, 2500.0):
            cutoff = cost / (success_rate * loss_value)
            selected = probabilities >= cutoff
            row = evaluate_policy(f"q={success_rate:.2f},L={loss_value:.0f}", selected, probabilities, y, cost, success_rate, loss_value)
            row.update({"success_rate": success_rate, "loss_value": loss_value, "threshold": cutoff})
            sensitivity_rows.append(row)

    return {
        "constants": {"intervention_cost": cost, "success_rate": success, "loss_per_churn": loss, "break_even_probability": threshold},
        "policies": policies,
        "sensitivity": pd.DataFrame(sensitivity_rows),
    }


def scenario_analysis(frame: pd.DataFrame, probabilities: np.ndarray) -> dict[str, Any]:
    """Q4 pressure scenarios; shifts are assumptions, not causal estimates."""
    contracts = frame["contract"].astype(str).to_numpy()
    tenure = frame["tenure_months"].to_numpy(dtype=float)
    competitor_shift = np.select(
        [contracts == "Month-to-month", contracts == "One year", contracts == "Two year"],
        [0.35, 0.15, 0.05],
        default=0.20,
    )
    macro_shift = 0.20 + np.where(tenure < 12, 0.05, 0.0)
    specs = [
        {"scenario": "基准", "delta": np.zeros(len(frame)), "success_rate": 0.35, "cost": 150.0},
        {"scenario": "竞争对手降价", "delta": competitor_shift, "success_rate": 0.33, "cost": 150.0},
        {"scenario": "宏观下行", "delta": macro_shift, "success_rate": 0.30, "cost": 165.0},
        {"scenario": "复合压力", "delta": competitor_shift + macro_shift, "success_rate": 0.28, "cost": 180.0},
    ]
    logits = np.log(np.clip(probabilities, 1e-6, 1 - 1e-6) / np.clip(1 - probabilities, 1e-6, 1))
    rows = []
    scenario_net: dict[str, np.ndarray] = {}
    scenario_probability: dict[str, np.ndarray] = {}
    for spec in specs:
        shifted = 1.0 / (1.0 + np.exp(-(logits + spec["delta"])))
        net = shifted * spec["success_rate"] * 2000.0 - spec["cost"]
        scenario_probability[spec["scenario"]] = shifted
        scenario_net[spec["scenario"]] = net
        rows.append({
            "scenario": spec["scenario"],
            "assumed_logit_shift_mean": float(np.mean(spec["delta"])),
            "assumed_success_rate": spec["success_rate"],
            "assumed_cost": spec["cost"],
            "predicted_churn_rate": float(shifted.mean()),
            "positive_net_count": int((net > 0).sum()),
            "positive_net_rate": float((net > 0).mean()),
            "net_benefit_if_target_positive": float(np.maximum(net, 0).sum()),
        })
    net_matrix = np.vstack([scenario_net[item["scenario"]] for item in specs])
    robust_score = net_matrix.min(axis=0)
    robust_selected = robust_score > 0
    # Equal intervention cost makes a conservative lower-bound robust ranking
    # exact for the separable objective sum_i min_s(net_i,s).
    robust_rows = []
    for ratio in (0.05, 0.10, 0.20):
        k = max(1, int(len(frame) * ratio))
        selected = np.zeros(len(frame), dtype=bool)
        selected[np.argsort(-robust_score)[:k]] = True
        robust_rows.append({
            "strategy": f"稳健排序前 {ratio:.0%}",
            "selected_count": int(selected.sum()),
            "selected_rate": float(selected.mean()),
            "worst_case_total_net": float(sum(np.minimum(net_matrix[:, selected], np.inf).min(axis=0))) if selected.any() else 0.0,
            "lower_bound_sum_min_person_net": float(np.maximum(robust_score[selected], 0).sum()),
        })
    robust_rows.append({
        "strategy": "稳健正收益集合",
        "selected_count": int(robust_selected.sum()),
        "selected_rate": float(robust_selected.mean()),
        "worst_case_total_net": float(net_matrix[:, robust_selected].sum(axis=1).min()) if robust_selected.any() else 0.0,
        "lower_bound_sum_min_person_net": float(np.maximum(robust_score[robust_selected], 0).sum()),
    })

    # Segment-level stress summary helps formulate the dynamic adjustment rule.
    segment_rows = []
    for contract in ["Month-to-month", "One year", "Two year"]:
        mask = contracts == contract
        if not mask.any():
            continue
        for spec in specs:
            p = scenario_probability[spec["scenario"]]
            segment_rows.append({
                "segment": contract,
                "scenario": spec["scenario"],
                "n": int(mask.sum()),
                "predicted_churn_rate": float(p[mask].mean()),
                "positive_net_rate": float((scenario_net[spec["scenario"]][mask] > 0).mean()),
            })
    return {
        "assumptions": [
            "竞争降价冲击按合同类型施加 log-odds 压力：月付 0.35、一年 0.15、两年 0.05。",
            "宏观下行施加全体 0.20，且在网不足 12 个月者额外 0.05。",
            "压力情景中的成功率/成本为敏感性假设，不是本数据估计的因果参数。",
        ],
        "scenarios": pd.DataFrame(rows),
        "segment_scenarios": pd.DataFrame(segment_rows),
        "robust_policies": pd.DataFrame(robust_rows),
        "robust_score": robust_score,
        "scenario_probability": scenario_probability,
        "scenario_net": scenario_net,
    }


def set_chinese_font() -> str:
    candidates = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS"]
    available = {item.name for item in matplotlib.font_manager.fontManager.ttflist}
    for candidate in candidates:
        if candidate in available:
            plt.rcParams["font.sans-serif"] = [candidate]
            plt.rcParams["axes.unicode_minus"] = False
            return candidate
    plt.rcParams["axes.unicode_minus"] = False
    return "matplotlib-default"


def save_figures(frame: pd.DataFrame, associations: pd.DataFrame, groups: pd.DataFrame, model: dict[str, Any], policy: dict[str, Any], scenario: dict[str, Any], output: Path) -> dict[str, str]:
    font = set_chinese_font()
    figures: dict[str, str] = {}

    def save(name: str) -> None:
        path = output / name
        plt.tight_layout()
        plt.savefig(path, dpi=180, bbox_inches="tight")
        plt.close()
        figures[name] = str(path.name)

    colors = ["#2c7a7b", "#d97706", "#9f1239", "#4f46e5", "#64748b", "#0f766e"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2))
    charts = [("contract", "合同类型", "合同"), ("internet_service", "互联网服务类型", "互联网"), ("payment_method", "支付方式", "支付"), ("tenure_band", "在网时长（月）", "在网时长")]
    for ax, (feature, title, _) in zip(axes.ravel(), charts):
        subset = groups[groups["feature"] == feature].copy()
        if subset.empty:
            ax.axis("off")
            continue
        subset = subset.sort_values("churn_rate", ascending=False)
        labels = subset["level"].astype(str).map(display_feature_token)
        ax.barh(labels, subset["churn_rate"] * 100, color=colors[: len(subset)])
        ax.invert_yaxis()
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("流失率（%）")
        ax.grid(axis="x", alpha=0.2)
    fig.suptitle("图1 关键群体的观测流失率", fontsize=14, fontweight="bold")
    save("fig_churn_groups.png")

    fig, ax = plt.subplots(figsize=(6.6, 5.3))
    y_test = model["roc"]["y_test"]
    for label, pred, color in [("Logistic", model["roc"]["logistic"], "#0f766e"), ("梯度提升", model["roc"]["hgb"], "#d97706")]:
        fpr, tpr, _ = roc_curve(y_test, pred)
        ax.plot(fpr, tpr, label=f"{label} AUC={roc_auc_score(y_test, pred):.3f}", color=color, linewidth=2)
    ax.plot([0, 1], [0, 1], "--", color="#94a3b8", linewidth=1)
    ax.set_xlabel("假阳性率")
    ax.set_ylabel("真阳性率")
    ax.set_title("图2 留出集 ROC 曲线")
    ax.legend(frameon=False)
    ax.grid(alpha=0.2)
    save("fig_roc.png")

    fig, ax = plt.subplots(figsize=(7.3, 4.8))
    policies = pd.DataFrame(policy["policies"])
    ax.bar(policies["strategy"], policies["expected_net_benefit"], color=["#94a3b8", "#9f1239", "#0f766e", "#2c7a7b", "#2c7a7b", "#2c7a7b", "#2c7a7b"][: len(policies)])
    ax.axhline(0, color="#334155", linewidth=0.8)
    ax.set_ylabel("期望净收益（元）")
    ax.set_title("图3 不同干预策略的期望净收益（OOF 风险）")
    ax.tick_params(axis="x", rotation=25)
    ax.grid(axis="y", alpha=0.2)
    save("fig_policy.png")

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.5))
    scen = scenario["scenarios"]
    axes[0].bar(scen["scenario"], scen["predicted_churn_rate"] * 100, color=["#2c7a7b", "#d97706", "#9f1239", "#7f1d1d"])
    axes[0].set_ylabel("预测流失率（%）")
    axes[0].set_title("冲击下的风险水平")
    axes[0].tick_params(axis="x", rotation=20)
    axes[0].grid(axis="y", alpha=0.2)
    robust = scenario["robust_policies"]
    axes[1].bar(robust["strategy"], robust["lower_bound_sum_min_person_net"], color="#0f766e")
    axes[1].set_ylabel("保守净收益下界（元）")
    axes[1].set_title("稳健排序策略")
    axes[1].tick_params(axis="x", rotation=20)
    axes[1].grid(axis="y", alpha=0.2)
    fig.suptitle("图4 外部冲击与稳健调整")
    save("fig_scenarios.png")

    fig, ax = plt.subplots(figsize=(8.0, 5.6))
    effects = model["effects"].copy()
    positive = effects.sort_values("coefficient", ascending=False).head(8)
    negative = effects.sort_values("coefficient", ascending=True).head(8)
    selected = pd.concat([negative, positive]).drop_duplicates("feature")
    labels = selected["feature"].map(display_feature_token)
    ax.barh(labels, selected["coefficient"], color=np.where(selected["coefficient"] >= 0, "#9f1239", "#0f766e"))
    ax.axvline(0, color="#334155", linewidth=0.8)
    ax.set_xlabel("Logistic 系数（数值变量为标准化后）")
    ax.set_title("图5 Logistic 主要关联方向")
    ax.grid(axis="x", alpha=0.2)
    save("fig_feature_effects.png")
    return {"font": font, **figures}


def make_intersection_summary(frame: pd.DataFrame) -> pd.DataFrame:
    conditions = {
        "月付合同": frame["contract"].eq("Month-to-month"),
        "光纤服务": frame["internet_service"].eq("Fiber optic"),
        "电子支票": frame["payment_method"].eq("Electronic check"),
        "在网≤6个月": frame["tenure_months"].le(6),
        "月付+光纤": frame["contract"].eq("Month-to-month") & frame["internet_service"].eq("Fiber optic"),
        "月付+电子支票": frame["contract"].eq("Month-to-month") & frame["payment_method"].eq("Electronic check"),
        "月付+光纤+电子支票": frame["contract"].eq("Month-to-month") & frame["internet_service"].eq("Fiber optic") & frame["payment_method"].eq("Electronic check"),
        "月付+光纤+电子支票+在网≤6个月": frame["contract"].eq("Month-to-month") & frame["internet_service"].eq("Fiber optic") & frame["payment_method"].eq("Electronic check") & frame["tenure_months"].le(6),
    }
    rows = []
    for name, mask in conditions.items():
        rows.append({"segment": name, "n": int(mask.sum()), "churn_rate": float(frame.loc[mask, TARGET].mean()) if mask.any() else None})
    return pd.DataFrame(rows)


def run(input_path: Path, output: Path, seed: int = 42) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    raw, encoding = read_csv_detect(input_path)
    frame, quality = clean_data(raw)
    quality["encoding"] = encoding
    associations, groups = categorical_associations(frame)
    model = fit_models(frame, seed)
    policy = policy_analysis(frame, model["oof_probability"], seed)
    scenario = scenario_analysis(frame, model["oof_probability"])
    intersections = make_intersection_summary(frame)

    # Save only aggregate tables plus a local risk file.  The latter is useful
    # for the Owner's operational review and is intentionally outside Git.
    write_json(output / "data_quality.json", quality)
    associations.to_csv(output / "associations.csv", index=False, encoding="utf-8-sig")
    groups.to_csv(output / "group_rates.csv", index=False, encoding="utf-8-sig")
    intersections.to_csv(output / "intersection_rates.csv", index=False, encoding="utf-8-sig")
    model_metrics = {key: value for key, value in model.items() if key in {"logistic_holdout", "hist_gradient_boosting_holdout", "logistic_cv_roc_auc", "oof_metrics", "n_train", "n_test"}}
    write_json(output / "model_metrics.json", model_metrics)
    model["effects"].to_csv(output / "feature_effects.csv", index=False, encoding="utf-8-sig")
    model["calibration"].to_csv(output / "calibration.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(policy["policies"]).to_csv(output / "policy_comparison.csv", index=False, encoding="utf-8-sig")
    policy["sensitivity"].to_csv(output / "policy_sensitivity.csv", index=False, encoding="utf-8-sig")
    scenario["scenarios"].to_csv(output / "scenario_summary.csv", index=False, encoding="utf-8-sig")
    scenario["segment_scenarios"].to_csv(output / "scenario_segments.csv", index=False, encoding="utf-8-sig")
    scenario["robust_policies"].to_csv(output / "robust_policy.csv", index=False, encoding="utf-8-sig")
    risk = frame[[ID, "contract", "internet_service", "payment_method", "tenure_months", "monthly_charges", TARGET]].copy()
    risk["risk_probability_oof"] = model["oof_probability"]
    risk["expected_net_benefit"] = model["oof_probability"] * 0.35 * 2000 - 150
    risk["robust_net_benefit_lower_bound"] = scenario["robust_score"]
    risk.sort_values("risk_probability_oof", ascending=False).to_csv(output / "risk_scores_local.csv", index=False, encoding="utf-8-sig")

    figure_info = save_figures(frame, associations, groups, model, policy, scenario, output)
    summary = {
        "input": {"path": str(input_path), "encoding": encoding},
        "quality": quality,
        "models": model_metrics,
        "top_associations": associations.head(8).to_dict("records"),
        "top_groups": groups.head(12).to_dict("records"),
        "intersections": intersections.to_dict("records"),
        "policy": {"constants": policy["constants"], "policies": policy["policies"]},
        "scenarios": {
            "assumptions": scenario["assumptions"],
            "summary": scenario["scenarios"].to_dict("records"),
            "robust_policies": scenario["robust_policies"].to_dict("records"),
        },
        "figures": figure_info,
        "reproducibility": {"seed": seed, "python_packages": {"pandas": pd.__version__}},
    }
    write_json(output / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="题目附件 CSV")
    parser.add_argument("--output", required=True, type=Path, help="运行输出目录")
    parser.add_argument("--seed", default=42, type=int)
    args = parser.parse_args()
    warnings.filterwarnings("ignore", category=FutureWarning)
    summary = run(args.input.resolve(), args.output.resolve(), args.seed)
    print(json.dumps({
        "status": "PASS",
        "rows": summary["quality"]["rows"],
        "churn_rate": summary["quality"]["churn_rate"],
        "logistic_auc": summary["models"]["logistic_holdout"]["roc_auc"],
        "hgb_auc": summary["models"]["hist_gradient_boosting_holdout"]["roc_auc"],
        "break_even_probability": summary["policy"]["constants"]["break_even_probability"],
        "output": str(args.output.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
