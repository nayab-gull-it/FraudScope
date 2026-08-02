"""
engine/chatbot.py

Consent-aware chatbot for answering questions about a fraud scan report.

Two modes, controlled by the `consent` flag (per-session, sent by the
frontend on every request -- nothing is stored server-side):

  consent=False (default / no data access):
      Only the aggregated summary (same shape as narrative.py uses) is
      sent to the model. If the user asks something that needs
      transaction-level detail (vendor names, specific amounts, specific
      rows) the model is instructed to say so and the response comes back
      with needs_data_access=True, so the frontend can show an
      "Allow access?" prompt instead of guessing from free text.

  consent=True (user explicitly allowed data access for this session):
      The flagged transaction rows (id/vendor/amount/risk/reason -- the
      same fields already shown in the report table, not the raw CSV)
      are sent to the model so it can answer specific questions.

Backend is stateless: the caller must pass the full conversation history
on every call, same as any other Claude/Groq-style chat integration.
"""

import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

MODEL = "llama-3.1-8b-instant"

_client = None


def _get_client():
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


def _build_system_prompt(summary: dict, rows: list, consent: bool) -> str:
    if consent:
        rows_json = json.dumps(rows, ensure_ascii=False)
        return (
            "You are a fraud analyst assistant answering questions about a "
            "ledger scan report. The user has explicitly allowed you to "
            "access the flagged transaction data below for this session. "
            "Answer ONLY using this data -- never invent vendors, amounts, "
            "IDs, or reasons that are not present in it. If the answer "
            "isn't in the data, say so plainly instead of guessing. If the "
            "user's latest message is not a question but a short "
            "conversational remark (like 'ok', 'good', 'thanks', "
            "'perfect'), reply briefly and naturally -- do not repeat "
            "previous data or re-answer an earlier question.\n\n"
            f"Aggregated summary: {json.dumps(summary, ensure_ascii=False)}\n"
            f"Flagged transactions: {rows_json}\n\n"
            "Respond ONLY with a JSON object of the exact shape "
            '{"answer": "...", "needs_data_access": false} '
            "and nothing else -- no markdown, no code fences."
        )
    else:
        return (
            "You are a fraud analyst assistant answering questions about a "
            "ledger scan report. You do NOT have access to individual "
            "transaction data (no vendor names, no specific amounts, no "
            "transaction IDs) -- only the aggregated summary below. Answer "
            "general questions using only these aggregate numbers. If the "
            "user asks something that requires transaction-level detail "
            "you don't have, do not guess or invent an answer -- instead "
            "reply with a short, polite note that you don't have access to "
            "that data and ask if they'd like to allow access, and set "
            "needs_data_access to true. If the user's latest message is "
            "not a question but a short conversational remark (like 'ok', "
            "'good', 'thanks', 'perfect'), reply briefly and naturally -- "
            "do not repeat previous data or re-answer an earlier question, "
            "and set needs_data_access to false.\n\n"
            f"Aggregated summary: {json.dumps(summary, ensure_ascii=False)}\n\n"
            "Respond ONLY with a JSON object of the exact shape "
            '{"answer": "...", "needs_data_access": true or false} '
            "and nothing else -- no markdown, no code fences."
        )


def chat_response(
    user_message: str,
    conversation_history: list,
    summary: dict,
    rows: list,
    consent: bool,
    offline_mode: bool = False,
) -> dict:
    """
    Args:
        user_message: the latest question from the user.
        conversation_history: list of {"role": "user"|"assistant", "content": "..."}
            from earlier turns in this chat (empty list on first message).
        summary: aggregated report stats (always required).
        rows: flagged transaction rows (only actually sent to the model
            if consent=True -- pass [] when consent is False).
        consent: whether the user has allowed data access this session.
        offline_mode: if True, no network call is made at all.

    Returns:
        {"answer": "...", "needs_data_access": bool, "error": None}
        or {"answer": None, "needs_data_access": False, "error": "..."}
    """
    if offline_mode:
        return {
            "answer": None,
            "needs_data_access": False,
            "error": "Offline Mode is on -- chatbot is disabled.",
        }

    system_prompt = _build_system_prompt(summary, rows, consent)

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_message})

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            max_tokens=300,
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content.strip()
        parsed = json.loads(raw)

        return {
            "answer": parsed.get("answer", "").strip(),
            "needs_data_access": bool(parsed.get("needs_data_access", False)),
            "error": None,
        }
    except json.JSONDecodeError:
        return {
            "answer": None,
            "needs_data_access": False,
            "error": "AI response could not be parsed. Please try asking again.",
        }
    except Exception as exc:
        return {
            "answer": None,
            "needs_data_access": False,
            "error": f"Chatbot unavailable: {exc}",
        }