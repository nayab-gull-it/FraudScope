"""
FraudScope detection engine.

Every function here does real computation against the uploaded data —
nothing here is hardcoded or simulated. This module never makes a network
call, so it works identically whether Offline Mode is on or off; the
LLM-narrative layer (added later) sits entirely outside this file.
"""

import numpy as np
import pandas as pd

# ---------- how much each finding contributes to a row's risk score ----------
RISK_WEIGHTS = {
    "outlier":              30,
    "mild_outlier":         15,
    "duplicate":            25,
    "round_number":         10,
    "threshold_skirt":      35,
    "time_anomaly":         15,
    "vendor_concentration": 15,
}

HIGH_RISK_THRESHOLD = 35
MEDIUM_RISK_THRESHOLD = 15

# Common approval/reporting limits worth checking for "just under the limit"
# behavior. Extend this list if a domain needs different thresholds.
COMMON_THRESHOLDS = (10_000, 25_000, 50_000, 100_000, 500_000, 1_000_000)


# =========================================================
# Column detection
# =========================================================
def detect_columns(df: pd.DataFrame) -> dict:
    """Guess which column is amount / date / id / vendor from name + dtype."""
    columns = {"amount": None, "date": None, "id": None, "vendor": None}
    lower = {c: str(c).lower() for c in df.columns}

    amount_keys = ["amount", "amt", "total", "value", "price", "cost", "sum", "balance"]
    date_keys   = ["date", "time", "timestamp", "created", "posted"]
    id_keys     = ["id", "txn", "transaction", "ref", "invoice", "no."]
    vendor_keys = ["vendor", "supplier", "payee", "account", "merchant", "customer", "name"]

    for col, low in lower.items():
        if columns["amount"] is None and any(k in low for k in amount_keys) and pd.api.types.is_numeric_dtype(df[col]):
            columns["amount"] = col
        elif columns["date"] is None and any(k in low for k in date_keys):
            columns["date"] = col
        elif columns["id"] is None and any(k in low for k in id_keys):
            columns["id"] = col
        elif columns["vendor"] is None and any(k in low for k in vendor_keys):
            columns["vendor"] = col

    # fallback: first numeric column becomes the amount column
    if columns["amount"] is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if numeric_cols:
            columns["amount"] = numeric_cols[0]

    # fallback: first column becomes the id column
    if columns["id"] is None:
        columns["id"] = df.columns[0]

    return columns


# =========================================================
# Individual checks — each returns {row_index: reason_string}
# =========================================================
def check_outliers(df: pd.DataFrame, amount_col: str) -> dict:
    flags = {}
    values = df[amount_col].astype(float)
    std = values.std()
    if not std or np.isnan(std):
        return flags
    z_scores = (values - values.mean()) / std
    for idx, z in z_scores.items():
        if abs(z) >= 3:
            flags[idx] = (f"Statistical outlier — {abs(z):.1f} standard deviations from the average transaction", "outlier")
        elif abs(z) >= 2:
            flags[idx] = (f"Mildly unusual amount — {abs(z):.1f} standard deviations from the average", "mild_outlier")
    return flags


def check_duplicates(df: pd.DataFrame, amount_col: str, vendor_col: str | None) -> dict:
    flags = {}
    if vendor_col is None:
        return flags
    dup_mask = df.duplicated(subset=[vendor_col, amount_col], keep=False)
    for idx in df[dup_mask].index:
        flags[idx] = (f"Duplicate — same amount and vendor recorded more than once", "duplicate")
    return flags


def check_round_numbers(df: pd.DataFrame, amount_col: str) -> dict:
    flags = {}
    values = df[amount_col].astype(float)
    round_mask = (values > 0) & (values % 1000 == 0)
    if round_mask.mean() > 0.15:  # only flag if suspiciously frequent dataset-wide
        for idx in df[round_mask].index:
            flags[idx] = ("Round-number amount, part of an unusually high concentration of round figures in this file", "round_number")
    return flags


def check_threshold_skirting(df: pd.DataFrame, amount_col: str) -> dict:
    flags = {}
    values = df[amount_col].astype(float)
    for idx, val in values.items():
        for t in COMMON_THRESHOLDS:
            if t * 0.95 <= val < t:
                flags[idx] = (f"Sits just under the {t:,.0f} mark — a common pattern for evading an approval limit", "threshold_skirt")
                break
    return flags


def check_time_anomalies(df: pd.DataFrame, date_col: str | None) -> dict:
    flags = {}
    if date_col is None:
        return flags
    dates = pd.to_datetime(df[date_col], errors="coerce")
    has_time_component = dates.dt.hour.nunique(dropna=True) > 1
    for idx, d in dates.items():
        if pd.isna(d):
            continue
        if d.weekday() >= 5:
            flags[idx] = ("Recorded on a weekend", "time_anomaly")
        elif has_time_component and (d.hour < 6 or d.hour > 22):
            flags[idx] = ("Recorded outside normal business hours", "time_anomaly")
    return flags


def check_vendor_concentration(df: pd.DataFrame, amount_col: str, vendor_col: str | None) -> dict:
    flags = {}
    if vendor_col is None:
        return flags
    totals = df.groupby(vendor_col)[amount_col].sum()
    grand_total = totals.sum()
    if not grand_total:
        return flags
    heavy_vendors = set(totals[totals / grand_total > 0.3].index)
    if not heavy_vendors:
        return flags
    for idx, vendor in df[vendor_col].items():
        if vendor in heavy_vendors:
            flags[idx] = (f"'{vendor}' accounts for a disproportionately large share of total spend", "vendor_concentration")
    return flags


# =========================================================
# Orchestration
# =========================================================
def run_scan(df: pd.DataFrame) -> dict:
    columns = detect_columns(df)
    amount_col, date_col, id_col, vendor_col = (
        columns["amount"], columns["date"], columns["id"], columns["vendor"]
    )

    if amount_col is None:
        raise ValueError("Couldn't find a numeric amount column in this file.")

    df = df.copy()
    df[amount_col] = pd.to_numeric(df[amount_col], errors="coerce")
    df = df.dropna(subset=[amount_col]).reset_index(drop=True)

    if df.empty:
        raise ValueError("No valid numeric amounts were found to scan.")

    check_results = {
        "outlier_check":    check_outliers(df, amount_col),
        "duplicate_check":  check_duplicates(df, amount_col, vendor_col),
        "round_check":      check_round_numbers(df, amount_col),
        "threshold_check":  check_threshold_skirting(df, amount_col),
        "time_check":       check_time_anomalies(df, date_col),
        "vendor_check":     check_vendor_concentration(df, amount_col, vendor_col),
    }

    # merge all flags per row: a row can trigger more than one method
    per_row_flags = {}
    method_counts = {}
    for flags in check_results.values():
        for idx, (reason, method) in flags.items():
            per_row_flags.setdefault(idx, []).append((method, reason))
            method_counts[method] = method_counts.get(method, 0) + 1

    rows = []
    high_count = medium_count = clear_count = 0

    for idx, row in df.iterrows():
        row_flags = per_row_flags.get(idx, [])
        score = sum(RISK_WEIGHTS.get(m, 0) for m, _ in row_flags)

        if score >= HIGH_RISK_THRESHOLD:
            risk = "high"
            high_count += 1
        elif score >= MEDIUM_RISK_THRESHOLD:
            risk = "med"
            medium_count += 1
        else:
            risk = "clear"
            clear_count += 1

        rows.append({
            "id": str(row[id_col]) if id_col else f"ROW-{idx + 1}",
            "vendor": str(row[vendor_col]) if vendor_col else "—",
            "amount": f"{row[amount_col]:,.0f}",
            "risk": risk,
            "reason": "; ".join(r for _, r in row_flags) if row_flags else "—",
        })

    risk_order = {"high": 0, "med": 1, "clear": 2}
    rows.sort(key=lambda r: risk_order[r["risk"]])

    return {
        "columns_detected": columns,
        "total_rows": len(df),
        "high_risk": high_count,
        "medium_risk": medium_count,
        "clear": clear_count,
        "method_counts": method_counts,
        "rows": rows,
    }