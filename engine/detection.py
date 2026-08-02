"""
FraudScope detection engine.

Every function here does real computation against the uploaded data —
nothing here is hardcoded or simulated. This module never makes a network
call, so it works identically whether Offline Mode is on or off; the
LLM-narrative layer (added later) sits entirely outside this file.

Reason strings are written for a non-technical reader (an accountant, a
school admin, a small-business owner) — no z-scores or statistics jargon,
just plain comparisons using the actual numbers in the file.
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

# Default approval/reporting limits checked when the user hasn't told us
# their organization's actual approval threshold. These are generic
# guesses, not a real policy — check_threshold_skirting() words its
# message differently depending on whether a real, user-provided limit
# was used or we fell back to these defaults.
DEFAULT_THRESHOLDS = (10_000, 25_000, 50_000, 100_000, 500_000, 1_000_000)


# =========================================================
# Column detection
# =========================================================
def detect_columns(df: pd.DataFrame) -> dict:
    """Guess which column is amount / date / id / vendor from name + dtype.

    This is a heuristic, not a domain-aware understanding of the file —
    it matches header text against keyword lists and falls back to dtype
    when nothing matches. Returns both the guess and how confident that
    guess is, so the frontend can ask the user to confirm anything that
    wasn't a clean keyword match:

      "detected" -> a header keyword matched, reasonably safe
      "guessed"  -> no keyword matched, we fell back to a heuristic
      "none"     -> nothing usable found at all
    """
    columns = {"amount": None, "date": None, "id": None, "vendor": None}
    confidence = {"amount": "none", "date": "none", "id": "none", "vendor": "none"}
    lower = {c: str(c).lower() for c in df.columns}

    amount_keys = ["amount", "amt", "total", "value", "price", "cost", "sum", "balance"]
    date_keys   = ["date", "time", "timestamp", "created", "posted"]
    id_keys     = ["id", "txn", "transaction", "ref", "invoice", "no."]
    vendor_keys = ["vendor", "supplier", "payee", "account", "merchant", "customer", "name"]

    for col, low in lower.items():
        if columns["amount"] is None and any(k in low for k in amount_keys) and pd.api.types.is_numeric_dtype(df[col]):
            columns["amount"] = col
            confidence["amount"] = "detected"
        elif columns["date"] is None and any(k in low for k in date_keys):
            columns["date"] = col
            confidence["date"] = "detected"
        elif columns["id"] is None and any(k in low for k in id_keys):
            columns["id"] = col
            confidence["id"] = "detected"
        elif columns["vendor"] is None and any(k in low for k in vendor_keys):
            columns["vendor"] = col
            confidence["vendor"] = "detected"

    # fallback: first numeric column becomes the amount column
    if columns["amount"] is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if numeric_cols:
            columns["amount"] = numeric_cols[0]
            confidence["amount"] = "guessed"

    # fallback: first column becomes the id column
    if columns["id"] is None:
        columns["id"] = df.columns[0]
        confidence["id"] = "guessed"

    return {"columns": columns, "confidence": confidence}


def describe_columns(df: pd.DataFrame) -> list[dict]:
    """Lightweight per-column type hints, used to populate the
    column-confirmation dropdowns on the frontend (so a user picking a
    replacement column can see at a glance whether it's numeric/date/text)."""
    described = []
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            dtype = "numeric"
        else:
            sample = df[col].dropna().astype(str).head(20)
            if len(sample) > 0:
                parsed = pd.to_datetime(sample, errors="coerce")
                looks_like_date = parsed.notna().mean() > 0.7
            else:
                looks_like_date = False
            dtype = "date-like" if looks_like_date else "text"
        described.append({"name": str(col), "dtype": dtype})
    return described


# =========================================================
# Individual checks — each returns {row_index: (reason_string, method_key)}
# =========================================================
def check_outliers(df: pd.DataFrame, amount_col: str) -> dict:
    """Flags amounts far from the average — worded as a plain comparison
    to the file's own average instead of a standard-deviation figure."""
    flags = {}
    values = df[amount_col].astype(float)
    mean = values.mean()
    std = values.std()
    if not std or np.isnan(std):
        return flags

    z_scores = (values - mean) / std
    for idx, val in values.items():
        z = z_scores[idx]
        direction = "higher" if val > mean else "lower"
        ratio = (val / mean) if mean else None

        if abs(z) >= 3:
            if ratio and mean > 0:
                reason = (f"This amount ({val:,.0f}) is far {direction} than usual for this file — "
                          f"about {ratio:.1f}x the average transaction ({mean:,.0f}).")
            else:
                reason = f"This amount ({val:,.0f}) stands out sharply from every other transaction in this file."
            flags[idx] = (reason, "outlier")
        elif abs(z) >= 2:
            reason = (f"This amount ({val:,.0f}) is somewhat {direction} than the typical transaction "
                      f"in this file (around {mean:,.0f}).")
            flags[idx] = (reason, "mild_outlier")
    return flags


def check_duplicates(df: pd.DataFrame, amount_col: str, vendor_col: str | None) -> dict:
    flags = {}
    if vendor_col is None:
        return flags
    dup_mask = df.duplicated(subset=[vendor_col, amount_col], keep=False)
    for idx in df[dup_mask].index:
        vendor = df.loc[idx, vendor_col]
        amount = df.loc[idx, amount_col]
        flags[idx] = (f"The same amount ({amount:,.0f}) from '{vendor}' also appears in another row — "
                      f"could be a duplicate payment.", "duplicate")
    return flags


def check_round_numbers(df: pd.DataFrame, amount_col: str) -> dict:
    flags = {}
    values = df[amount_col].astype(float)
    round_mask = (values > 0) & (values % 1000 == 0)
    share = round_mask.mean()
    if share > 0.15:  # only flag if suspiciously frequent dataset-wide
        pct = share * 100
        for idx in df[round_mask].index:
            flags[idx] = (f"This is a round number. {pct:.0f}% of the amounts in this file are round "
                          f"numbers — an unusually high share, which can point to estimated or "
                          f"manually adjusted figures rather than exact recorded ones.", "round_number")
    return flags


def check_threshold_skirting(df: pd.DataFrame, amount_col: str, thresholds: tuple, is_custom: bool) -> dict:
    flags = {}
    values = df[amount_col].astype(float)
    for idx, val in values.items():
        for t in thresholds:
            if t * 0.95 <= val < t:
                if is_custom:
                    reason = (f"Sits just under your approval limit of {t:,.0f} — a common pattern for "
                              f"avoiding a required sign-off.")
                else:
                    reason = (f"Sits just under {t:,.0f}, a commonly used approval limit. We don't know "
                              f"your organization's actual limit — enter it when scanning to check this "
                              f"more precisely.")
                flags[idx] = (reason, "threshold_skirt")
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
            day_name = d.strftime("%A")
            flags[idx] = (f"Recorded on a {day_name} — outside normal weekday business activity.", "time_anomaly")
        elif has_time_component and (d.hour < 6 or d.hour > 22):
            time_str = d.strftime("%I:%M %p").lstrip("0")
            flags[idx] = (f"Recorded at {time_str} — outside normal business hours.", "time_anomaly")
    return flags


def check_vendor_concentration(df: pd.DataFrame, amount_col: str, vendor_col: str | None) -> dict:
    flags = {}
    if vendor_col is None:
        return flags
    totals = df.groupby(vendor_col)[amount_col].sum()
    grand_total = totals.sum()
    if not grand_total:
        return flags
    shares = totals / grand_total
    heavy_vendors = shares[shares > 0.3]
    if heavy_vendors.empty:
        return flags
    for idx, vendor in df[vendor_col].items():
        if vendor in heavy_vendors.index:
            pct = heavy_vendors[vendor] * 100
            flags[idx] = (f"'{vendor}' accounts for {pct:.0f}% of the total spend in this file — "
                          f"concentrating this much spend with one party is worth a closer look.",
                          "vendor_concentration")
    return flags


# =========================================================
# Orchestration
# =========================================================
def run_scan(df: pd.DataFrame, override_columns: dict | None = None, custom_threshold: float | None = None) -> dict:
    """Run the full detection pipeline.

    override_columns, if given, is a dict like
    {"amount": "Fee", "date": "Paid_On", "id": None, "vendor": "Student_Name"}
    coming from the user confirming/correcting the auto-detected columns
    on the frontend. When provided, it's used as-is instead of guessing.

    custom_threshold, if given, is the organization's real approval limit
    (e.g. 50000) — when provided, threshold-skirting checks against that
    single real number instead of the generic DEFAULT_THRESHOLDS list.
    """
    if override_columns:
        columns = {
            "amount": override_columns.get("amount") or None,
            "date":   override_columns.get("date") or None,
            "id":     override_columns.get("id") or None,
            "vendor": override_columns.get("vendor") or None,
        }
        # ignore anything that doesn't actually exist in this file
        for key, col in list(columns.items()):
            if col is not None and col not in df.columns:
                columns[key] = None
    else:
        columns = detect_columns(df)["columns"]

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

    if custom_threshold and custom_threshold > 0:
        thresholds = (float(custom_threshold),)
        is_custom_threshold = True
    else:
        thresholds = DEFAULT_THRESHOLDS
        is_custom_threshold = False

    check_results = {
        "outlier_check":    check_outliers(df, amount_col),
        "duplicate_check":  check_duplicates(df, amount_col, vendor_col),
        "round_check":      check_round_numbers(df, amount_col),
        "threshold_check":  check_threshold_skirting(df, amount_col, thresholds, is_custom_threshold),
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
        "threshold_used": {"value": thresholds[0] if is_custom_threshold else None, "is_custom": is_custom_threshold},
        "total_rows": len(df),
        "high_risk": high_count,
        "medium_risk": medium_count,
        "clear": clear_count,
        "method_counts": method_counts,
        "rows": rows,
    }