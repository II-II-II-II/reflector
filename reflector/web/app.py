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
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from reflector.config import load_config
from reflector.db import get_connection, init_db
from reflector.instruments import INSTRUMENTS, score, score_subscales
from reflector.llm import get_provider
from reflector.llm.pricing import estimate_cost_usd
from reflector.prompts import CHAT_SYSTEM_PROMPT
from reflector.safety import contains_crisis_language

app = Flask(__name__)

_provider = None


def _detect_code_version() -> str:
    """Git short hash this process is actually running, +dirty if the
    working tree has uncommitted changes — so a logged reply can always be
    traced back to the exact code that produced it, not just a model name."""
    repo_root = Path(__file__).parent.parent.parent
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True, check=True
            ).stdout.strip()
        )
        return f"{commit}+dirty" if dirty else commit
    except Exception:
        return "unknown"


CODE_VERSION = _detect_code_version()


def get_llm_provider():
    global _provider
    if _provider is None:
        _provider = get_provider(load_config())
    return _provider


REQUIRED_BEFORE_CHAT = ["ace", "big5"]


def missing_required_assessments() -> list[dict]:
    conn = get_connection()
    taken = {
        row["instrument"]
        for row in conn.execute(
            f"SELECT DISTINCT instrument FROM assessments WHERE instrument IN "
            f"({','.join('?' * len(REQUIRED_BEFORE_CHAT))})",
            REQUIRED_BEFORE_CHAT,
        )
    }
    conn.close()
    return [INSTRUMENTS[i] for i in REQUIRED_BEFORE_CHAT if i not in taken]


def current_model_id(config: dict) -> str:
    provider_name = config["llm"]["provider"]
    key = "model_id" if provider_name == "bedrock" else "model"
    return config["llm"][provider_name][key]


def session_usage_summary() -> dict:
    """Running totals across the whole chat log, cost estimated per-message
    using the model_id recorded at the time (correct even if the active
    model changes later)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT model_id, input_tokens, output_tokens FROM chat_messages "
        "WHERE input_tokens IS NOT NULL OR output_tokens IS NOT NULL"
    ).fetchall()
    conn.close()

    total_input = sum(r["input_tokens"] or 0 for r in rows)
    total_output = sum(r["output_tokens"] or 0 for r in rows)
    total_cost = 0.0
    cost_known = True
    for r in rows:
        c = estimate_cost_usd(r["model_id"], r["input_tokens"] or 0, r["output_tokens"] or 0)
        if c is None:
            cost_known = False
        else:
            total_cost += c

    return {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cost_usd": total_cost if cost_known else None,
        "cost_partial": not cost_known and (total_input or total_output),
    }


def assessment_context() -> str:
    """Most recent score per instrument, for chat grounding. Includes the
    highest-scored individual items alongside the total — a total/severity
    label alone flattens exactly the kind of specific signal (e.g. "anxious
    thoughts nearly every day") a person would want acknowledged directly,
    not just summarized as "mild"."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, instrument, administered_at, total_score, severity, risk_flag FROM assessments "
        "ORDER BY administered_at DESC"
    ).fetchall()

    latest_per_instrument = {}
    for row in rows:
        latest_per_instrument.setdefault(row["instrument"], row)

    if not latest_per_instrument:
        conn.close()
        return "No structured self-assessments have been taken yet."

    lines = []
    for instrument_id, row in latest_per_instrument.items():
        instrument = INSTRUMENTS[instrument_id]
        name = instrument["full_name"]
        taken = row["administered_at"][:10]
        if "subscales" in instrument:
            subscores = conn.execute(
                "SELECT subscale, score FROM assessment_subscores WHERE assessment_id = ?", (row["id"],)
            ).fetchall()
            traits = ", ".join(f"{s['subscale']} {s['score']}" for s in subscores)
            lines.append(f"- {name} (stable trait profile, taken {taken}): {traits}")
        else:
            flag = " (risk indicator flagged)" if row["risk_flag"] else ""
            endorsed = conn.execute(
                "SELECT item_index, item_text, response_value FROM assessment_responses "
                "WHERE assessment_id = ? AND response_value > 0",
                (row["id"],),
            ).fetchall()
            if "weights" in instrument:
                # Binary yes/no items (e.g. Holmes-Rahe) all tie at response_value=1 —
                # rank by the item's own weight instead, so "Divorce" outranks "Christmas".
                weights = instrument["weights"]
                top_items = sorted(endorsed, key=lambda e: weights[e["item_index"]], reverse=True)[:3]
            else:
                top_items = sorted(endorsed, key=lambda e: e["response_value"], reverse=True)[:2]
            detail = ""
            if top_items:
                scale_labels = dict(instrument["scale"])
                detail = " | highest-rated: " + "; ".join(
                    f"\"{t['item_text']}\" ({scale_labels.get(t['response_value'], t['response_value'])})"
                    for t in top_items
                )
            lines.append(f"- {name}: {row['total_score']} ({row['severity']}), taken {taken}{flag}{detail}")
    conn.close()
    return "Most recent self-assessment scores:\n" + "\n".join(lines)

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
    is_subscale_instrument = "subscales" in instrument
    if is_subscale_instrument:
        # total/severity aren't meaningful for a trait instrument — keep the
        # NOT NULL columns satisfied with a clear placeholder, real result
        # goes in assessment_subscores.
        severity = "See subscale breakdown"
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
    if is_subscale_instrument:
        subscores = score_subscales(instrument, responses)
        conn.executemany(
            "INSERT INTO assessment_subscores (assessment_id, subscale, score) VALUES (?, ?, ?)",
            [(assessment_id, name, sub_score) for name, sub_score in subscores],
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
    subscores = conn.execute(
        "SELECT subscale, score FROM assessment_subscores WHERE assessment_id = ?", (assessment_id,)
    ).fetchall()
    conn.close()
    if not row:
        abort(404)
    instrument = INSTRUMENTS[row["instrument"]]
    return render_template("result.html", assessment=row, instrument=instrument, subscores=subscores)


@app.route("/crisis")
def crisis():
    return render_template("crisis.html")


@app.route("/chat", methods=["GET"])
def chat_page():
    missing = missing_required_assessments()
    if missing:
        return render_template("chat_gate.html", missing=missing)

    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content, crisis_flag, created_at, model_id, code_version FROM chat_messages ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return render_template("chat.html", messages=rows, usage=session_usage_summary())


@app.route("/chat", methods=["POST"])
def chat_submit():
    if missing_required_assessments():
        return redirect(url_for("chat_page"))

    user_message = request.form.get("message", "").strip()
    if not user_message:
        return redirect(url_for("chat_page"))

    crisis_flag = contains_crisis_language(user_message)
    now = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    history = conn.execute("SELECT role, content FROM chat_messages ORDER BY id ASC").fetchall()
    conn.execute(
        "INSERT INTO chat_messages (role, content, created_at, crisis_flag, code_version) VALUES (?, ?, ?, ?, ?)",
        ("user", user_message, now, crisis_flag, CODE_VERSION),
    )
    conn.commit()

    assessment_ctx = assessment_context()
    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "system", "content": assessment_ctx},
    ]
    messages.extend({"role": row["role"], "content": row["content"]} for row in history)
    messages.append({"role": "user", "content": user_message})

    model_id = current_model_id(load_config())
    try:
        result = get_llm_provider().chat(messages)
        reply, input_tokens, output_tokens = result.text, result.input_tokens, result.output_tokens
    except Exception as e:
        logger.warning(f"chat provider call failed error={type(e).__name__}")
        reply = f"(The configured model backend failed to respond: {type(e).__name__}. Check config.yaml and that the backend is reachable.)"
        input_tokens = output_tokens = None

    conn.execute(
        "INSERT INTO chat_messages "
        "(role, content, created_at, crisis_flag, input_tokens, output_tokens, model_id, code_version, system_prompt) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "assistant",
            reply,
            datetime.now(timezone.utc).isoformat(),
            False,
            input_tokens,
            output_tokens,
            model_id,
            CODE_VERSION,
            f"{CHAT_SYSTEM_PROMPT}\n\n{assessment_ctx}",
        ),
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
    subscores_by_assessment = {}
    if "subscales" in instrument:
        for row in rows:
            subscores_by_assessment[row["id"]] = conn.execute(
                "SELECT subscale, score FROM assessment_subscores WHERE assessment_id = ?", (row["id"],)
            ).fetchall()
    conn.close()
    return render_template(
        "history.html", instrument=instrument, rows=rows, subscores_by_assessment=subscores_by_assessment
    )


if __name__ == "__main__":
    import os

    init_db()
    # LAN_ACCESS=1 binds to all interfaces so a phone on the same WiFi can
    # reach it. Default stays localhost-only. Never bind this to a public
    # interface or run it on untrusted/public WiFi.
    host = "0.0.0.0" if os.environ.get("LAN_ACCESS") == "1" else "127.0.0.1"
    app.run(host=host, port=5050, debug=False)
