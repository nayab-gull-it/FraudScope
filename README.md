# FraudScope

**Find what shouldn't be there.**

🔗 **Live demo:** [fraud-scope.onrender.com](https://fraud-scope.onrender.com)
*(hosted on Render's free tier — the first request after a period of inactivity may take 30–60 seconds to wake the server up)*

FraudScope is a fraud and anomaly detection tool for financial ledgers. Upload a CSV of transactions, and it scans every row using statistical forensics — not a language model guessing at numbers — to surface duplicates, threshold-skirting, timing anomalies, and other classic fraud signals, each with a plain-language explanation of *why* it was flagged.

---

## The problem this solves

Most "AI CSV analyzer" tools solve the wrong problem: they ask companies to hand raw financial data to a third-party LLM and hope for the best. That's a non-starter for anyone handling real transaction records — payroll, vendor payments, expense logs — where the data itself is sensitive.

FraudScope is built around a different, stricter architecture:

- **All detection math runs locally.** Every statistical check — outlier detection, duplicate matching, round-number bias, threshold-skirting, time-based anomalies, vendor concentration — is pure `pandas`/`numpy`, computed in memory, and never leaves the server.
- **The LLM only ever sees aggregated, anonymized statistics** (row counts, risk totals, method counts) — never a single raw transaction, vendor name, or amount, unless a user explicitly opts in for a specific chatbot question.
- **Offline Mode** disables every external call entirely, for users who want zero network activity beyond the scan itself.

This isn't a privacy disclaimer bolted on afterward — it's the reason the app is architected the way it is.

---

## Features

- **Smart column detection** — auto-identifies amount, date, ID, and vendor columns from any CSV, with a confirm-before-you-scan step so nothing runs on a bad guess.
- **Seven-method detection engine** — statistical outliers (z-score), duplicate transactions, round-number bias, threshold-skirting against approval limits (custom or common defaults), time-based anomalies (weekends/odd hours), and vendor concentration, each contributing to a weighted High / Medium / Clear risk score per row.
- **AI narrative summary** — an optional, one-paragraph plain-English summary of the scan, generated from aggregated stats only.
- **Consent-aware chatbot** — ask follow-up questions about the report. By default it answers only from aggregate numbers; if a question needs transaction-level detail, it explicitly asks for permission before accessing anything more specific — no silent data access.
- **Branded PDF export** — a polished, downloadable report generated entirely server-side.
- **Offline Mode** — one toggle disables all AI features and external calls for the entire session.

---

## Tech stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Flask (Python) | Routing, request handling, JSON APIs |
| Detection engine | pandas, numpy | All statistical fraud-detection logic — runs 100% locally |
| AI narrative & chatbot | Groq API (`llama-3.1-8b-instant`) | Optional narrative generation and Q&A, restricted to aggregated data by design |
| PDF generation | reportlab | Server-side, branded PDF report export |
| Frontend | Vanilla HTML/CSS/JS, Jinja templates | No framework — deliberately lightweight, `fetch()`-based communication with the backend |
| Secrets | python-dotenv | Local `.env` for API keys, kept out of version control |
| Deployment target | Render | — |

No React, no jQuery, no ORM — the stack is intentionally minimal so every request/response cycle is easy to trace end to end.

---

## Architecture

```
Browser (vanilla JS)
   │  fetch() — multipart CSV upload / JSON
   ▼
Flask app.py
   │
   ├── /api/detect-columns  →  engine/detection.py   (pandas — column guessing)
   ├── /api/scan            →  engine/detection.py   (pandas + numpy — full scan)
   ├── /api/narrative       →  engine/narrative.py   (Groq — aggregated stats only)
   ├── /api/chat            →  engine/chatbot.py     (Groq — consent-gated data access)
   └── /api/export          →  engine/report_export.py (reportlab — PDF rendering)
```

Every request that touches raw transaction data (`/api/scan`, `/api/detect-columns`) never leaves the Flask process. Only `/api/narrative` and `/api/chat` make outbound calls, and only with data that's already been reduced to counts and aggregates — with `/api/chat` requiring explicit per-question consent before it can see anything more granular.

---

## Project structure

```
Fraudscope/
├── app.py
├── requirements.txt
├── .env                  (not committed — holds GROQ_API_KEY)
├── engine/
│   ├── detection.py       # core statistical detection logic
│   ├── narrative.py       # AI narrative summary (Groq)
│   ├── chatbot.py         # consent-aware chatbot (Groq)
│   └── report_export.py   # PDF report generation (reportlab)
├── sample_data/
│   └── sample_ledger.csv
├── templates/
│   ├── index.html
│   └── scan.html
└── static/
    ├── favicon.svg
    ├── css/
    │   ├── style.css
    │   └── scan.css
    └── js/
        ├── main.js
        └── scan.js
```

---

## Running locally

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root:
```
GROQ_API_KEY=your_key_here
```

Then:
```bash
python app.py
```

The app runs at `http://127.0.0.1:5000`.

---

## Roadmap

- [ ] Data visualizations (risk distribution, detection method breakdown)
- [ ] Deployment to Render

---

## Why this project exists

This was built as a portfolio project to demonstrate a specific point: AI features are more credible — and more useful — when they're scoped tightly around what actually needs intelligence, instead of being handed everything by default. The detection engine here does the real analytical work with deterministic statistics; the LLM is a thin, consent-gated layer on top for communication, not computation.
