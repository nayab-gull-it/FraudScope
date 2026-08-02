"""
engine/narrative.py

Generates a short, plain-English narrative summary of a fraud scan report
using Groq's LLM API. Privacy-safe by design: the caller is responsible for
passing ONLY the aggregated summary dict (never raw transaction rows), and
this module refuses to run entirely if offline mode is on.
"""

import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

MODEL = "llama-3.1-8b-instant"

_client = None


def _get_client():
    """Lazily create the Groq client so a missing API key doesn't crash
    the app at import time -- only when the feature is actually used."""
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file "
                "(local) or your Render environment variables (deployed)."
            )
        _client = Groq(api_key=api_key)
    return _client


def generate_narrative(summary: dict, offline_mode: bool = False) -> dict:
    """
    Generate a short AI narrative summary from aggregated scan stats.

    Args:
        summary: aggregated report data only, e.g.
            {
                "total_rows": 20,
                "high_risk": 7,
                "medium_risk": 6,
                "clear": 7,
                "method_counts": {"outlier": 1, "duplicate": 4, ...}
            }
            Do NOT pass raw transaction rows into this function.
        offline_mode: if True, no network call is made at all.

    Returns:
        dict with either {"narrative": "..."} on success,
        or {"narrative": None, "error": "..."} on failure/skip.
    """
    if offline_mode:
        return {
            "narrative": None,
            "error": "Offline Mode is on -- AI narrative was not generated.",
        }

    required_keys = {"total_rows", "high_risk", "medium_risk", "clear", "method_counts"}
    missing = required_keys - summary.keys()
    if missing:
        return {
            "narrative": None,
            "error": f"Summary missing required fields: {', '.join(sorted(missing))}",
        }

    prompt = (
        "You are a fraud analyst assistant. You are given ONLY aggregated, "
        "anonymized statistics from an automated ledger scan -- no vendor "
        "names, no transaction IDs, no raw amounts. Write a concise, "
        "professional 3-4 sentence narrative summary for a business user, "
        "explaining what the numbers suggest and what to prioritize "
        "reviewing first. Do not invent any specifics not present in the "
        "data below.\n\n"
        f"Total transactions scanned: {summary['total_rows']}\n"
        f"High risk: {summary['high_risk']}\n"
        f"Medium risk: {summary['medium_risk']}\n"
        f"Clear: {summary['clear']}\n"
        f"Detection method breakdown: {summary['method_counts']}\n"
    )

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=220,
            temperature=0.4,
        )
        text = response.choices[0].message.content.strip()
        return {"narrative": text, "error": None}
    except Exception as exc:
        return {"narrative": None, "error": f"AI narrative unavailable: {exc}"}