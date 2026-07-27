"""
Local-only web form for self-administered assessments (PHQ-9, GAD-7,
PCL-5). Binds to 127.0.0.1 only — never exposed to the network.

Every submission is timestamped and stored as its own row in the
`assessments` table, so scores trend over time rather than overwriting
a single value. A positive PHQ-9 risk-item response routes to a
hardcoded crisis-resources page — never LLM-generated — regardless of
total score.
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from reflector.config import load_config
from reflector.db import get_connection, init_db
from reflector.instruments import INSTRUMENTS, score
from reflector.llm import get_provider
from reflector.prompts import CHAT_SYSTEM_PROMPT
from reflector.safety import contains_crisis_language

app = Flask(__name__)

_provider = None


def get_llm_provider():
    global _provider
    if _provider is None:
        _provider = get_provider(load_config())
    return _provider

# Lightweight lifecycle logging — event names and counts only, never
# response values or entry content.
logger = logging.getLogger("reflector.web")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(_handler)


@app.route("/")
def index():
    return render_template("index.html", instruments=INSTRUMENTS.values())


@app.route("/assessment/<instrument_id>", methods=["GET"])
def assessment_form(instrument_id):
    instrument = INSTRUMENTS.get(instrument_id)
    if not instrument:
        abort(404)
    logger.info(f"form GET instrument={instrument_id} ua={request.headers.get('User-Agent')}")
    return render_template("form.html", instrument=instrument)


@app.route("/assessment/<instrument_id>", methods=["POST"])
def assessment_submit(instrument_id):
    instrument = INSTRUMENTS.get(instrument_id)
    if not instrument:
        abort(404)

    n_items = len(instrument["items"])
    try:
        responses = [int(request.form[f"item_{i}"]) for i in range(n_items)]
    except (KeyError, ValueError) as e:
        logger.warning(f"form POST validation failed instrument={instrument_id} error={type(e).__name__}")
        return render_template("form.html", instrument=instrument, error="Please answer every item."), 400

    total, severity, risk_flag = score(instrument, responses)
    logger.info(f"form POST valid instrument={instrument_id} items_received={n_items}")
    administered_at = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    cur = conn.execute(
        "INSERT INTO assessments (instrument, administered_at, total_score, severity, risk_flag) "
        "VALUES (?, ?, ?, ?, ?)",
        (instrument_id, administered_at, total, severity, risk_flag),
    )
    assessment_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO assessment_responses (assessment_id, item_index, item_text, response_value) "
        "VALUES (?, ?, ?, ?)",
        [(assessment_id, i, instrument["items"][i], responses[i]) for i in range(n_items)],
    )
    conn.commit()
    conn.close()

    if risk_flag:
        return redirect(url_for("crisis"))
    return redirect(url_for("result", assessment_id=assessment_id))


@app.route("/result/<int:assessment_id>")
def result(assessment_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM assessments WHERE id = ?", (assessment_id,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    instrument = INSTRUMENTS[row["instrument"]]
    return render_template("result.html", assessment=row, instrument=instrument)


@app.route("/crisis")
def crisis():
    return render_template("crisis.html")


@app.route("/chat", methods=["GET"])
def chat_page():
    conn = get_connection()
    rows = conn.execute("SELECT role, content, crisis_flag FROM chat_messages ORDER BY id ASC").fetchall()
    conn.close()
    return render_template("chat.html", messages=rows)


@app.route("/chat", methods=["POST"])
def chat_submit():
    user_message = request.form.get("message", "").strip()
    if not user_message:
        return redirect(url_for("chat_page"))

    crisis_flag = contains_crisis_language(user_message)
    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    history = conn.execute("SELECT role, content FROM chat_messages ORDER BY id ASC").fetchall()
    conn.execute(
        "INSERT INTO chat_messages (role, content, created_at, crisis_flag) VALUES (?, ?, ?, ?)",
        ("user", user_message, now, crisis_flag),
    )
    conn.commit()

    messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}]
    messages.extend({"role": row["role"], "content": row["content"]} for row in history)
    messages.append({"role": "user", "content": user_message})

    try:
        reply = get_llm_provider().chat(messages)
    except Exception as e:
        logger.warning(f"chat provider call failed error={type(e).__name__}")
        reply = f"(The configured model backend failed to respond: {type(e).__name__}. Check config.yaml and that the backend is reachable.)"

    conn.execute(
        "INSERT INTO chat_messages (role, content, created_at, crisis_flag) VALUES (?, ?, ?, ?)",
        ("assistant", reply, datetime.now(timezone.utc).isoformat(), False),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("chat_page"))


@app.route("/history/<instrument_id>")
def history(instrument_id):
    instrument = INSTRUMENTS.get(instrument_id)
    if not instrument:
        abort(404)
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, administered_at, total_score, severity FROM assessments "
        "WHERE instrument = ? ORDER BY administered_at ASC",
        (instrument_id,),
    ).fetchall()
    conn.close()
    return render_template("history.html", instrument=instrument, rows=rows)


if __name__ == "__main__":
    import os

    init_db()
    # LAN_ACCESS=1 binds to all interfaces so a phone on the same WiFi can
    # reach it. Default stays localhost-only. Never bind this to a public
    # interface or run it on untrusted/public WiFi.
    host = "0.0.0.0" if os.environ.get("LAN_ACCESS") == "1" else "127.0.0.1"
    app.run(host=host, port=5050, debug=False)
