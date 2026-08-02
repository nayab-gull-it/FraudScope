import pandas as pd
from flask import Flask, render_template, request, jsonify

from engine.detection import run_scan

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/scan")
def scan():
    return render_template("scan.html")


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Receives a CSV, runs the real detection engine, returns JSON.
    The file is processed entirely in memory and never written to disk."""

    if "file" not in request.files:
        return jsonify({"error": "No file was uploaded."}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file was selected."}), 400

    if not file.filename.lower().endswith(".csv"):
        return jsonify({"error": "Only CSV files are supported right now."}), 400

    try:
        df = pd.read_csv(file)
    except Exception:
        return jsonify({"error": "Couldn't read this file. Make sure it's a valid CSV."}), 400

    if df.empty:
        return jsonify({"error": "This file has no rows to scan."}), 400

    try:
        result = run_scan(df)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    result["filename"] = file.filename
    return jsonify(result)


if __name__ == "__main__":
    # Local dev server. Run with: py app.py
    app.run(debug=True, port=5000)