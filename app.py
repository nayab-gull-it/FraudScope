import pandas as pd
from flask import Flask, render_template, request, jsonify

from engine.detection import run_scan, detect_columns, describe_columns

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/scan")
def scan():
    return render_template("scan.html")


def _read_uploaded_csv():
    """Shared validation for both /api/detect-columns and /api/scan.
    Returns (df, error_response). Exactly one of the two will be None."""
    if "file" not in request.files:
        return None, (jsonify({"error": "No file was uploaded."}), 400)

    file = request.files["file"]

    if file.filename == "":
        return None, (jsonify({"error": "No file was selected."}), 400)

    if not file.filename.lower().endswith(".csv"):
        return None, (jsonify({"error": "Only CSV files are supported right now."}), 400)

    try:
        df = pd.read_csv(file)
    except Exception:
        return None, (jsonify({"error": "Couldn't read this file. Make sure it's a valid CSV."}), 400)

    if df.empty:
        return None, (jsonify({"error": "This file has no rows to scan."}), 400)

    return df, None


@app.route("/api/detect-columns", methods=["POST"])
def api_detect_columns():
    """Quick pass over an uploaded CSV: guesses amount/date/id/vendor
    columns and returns the full column list so the frontend can show a
    confirm-before-you-scan step instead of silently trusting a guess."""
    df, error = _read_uploaded_csv()
    if error:
        return error

    detected = detect_columns(df)

    return jsonify({
        "columns_detected": detected["columns"],
        "confidence": detected["confidence"],
        "all_columns": describe_columns(df),
    })


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Receives a CSV, runs the real detection engine, returns JSON.
    The file is processed entirely in memory and never written to disk.

    Optionally accepts amount_col / date_col / id_col / vendor_col form
    fields — these come from the user confirming (or correcting) the
    auto-detected columns on the frontend. When amount_col is present,
    it takes priority over auto-detection entirely."""
    df, error = _read_uploaded_csv()
    if error:
        return error

    override_columns = None
    if request.form.get("amount_col"):
        override_columns = {
            "amount": request.form.get("amount_col") or None,
            "date":   request.form.get("date_col") or None,
            "id":     request.form.get("id_col") or None,
            "vendor": request.form.get("vendor_col") or None,
        }

    try:
        result = run_scan(df, override_columns=override_columns)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    result["filename"] = request.files["file"].filename
    return jsonify(result)


if __name__ == "__main__":
    # Local dev server. Run with: py app.py
    app.run(debug=True, port=5000)

from engine.narrative import generate_narrative

@app.route("/api/narrative", methods=["POST"])
def api_narrative():
    data = request.get_json(silent=True) or {}
    offline_mode = bool(data.get("offline_mode", False))
    summary = data.get("summary", {})

    result = generate_narrative(summary, offline_mode=offline_mode)
    return jsonify(result)
from engine.chatbot import chat_response

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}

    result = chat_response(
        user_message=data.get("message", ""),
        conversation_history=data.get("history", []),
        summary=data.get("summary", {}),
        rows=data.get("rows", []),
        consent=bool(data.get("consent", False)),
        offline_mode=bool(data.get("offline_mode", False)),
    )
    return jsonify(result)
from engine.chatbot import chat_response

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}

    result = chat_response(
        user_message=data.get("message", ""),
        conversation_history=data.get("history", []),
        summary=data.get("summary", {}),
        rows=data.get("rows", []),
        consent=bool(data.get("consent", False)),
        offline_mode=bool(data.get("offline_mode", False)),
    )
    return jsonify(result)
from io import BytesIO
from flask import send_file
from engine.report_export import generate_pdf_report

@app.route("/api/export", methods=["POST"])
def api_export():
    scan_data = request.get_json(silent=True) or {}
    pdf_buffer = generate_pdf_report(scan_data)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="fraudscope_report.pdf",
    )