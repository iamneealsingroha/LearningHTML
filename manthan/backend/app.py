"""
MANTHAN - Lecture Amnesia Fixer (Web Version)
Flask backend. Run with: python app.py  (defaults to http://localhost:5000)
"""
from flask import Flask, request, jsonify, send_from_directory
import os
import json

import db
import ai_engine
import scheduler
from db import get_conn, now_iso

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")


@app.after_request
def add_cors_headers(response):
    # Manual CORS (avoids an extra pip dependency). Useful if you ever serve
    # the frontend from a different origin than the API during development.
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


# ---------------------------------------------------------------------------
# Static frontend serving (so `python app.py` alone serves the whole app)
# ---------------------------------------------------------------------------
@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    full = os.path.join(FRONTEND_DIR, path)
    if os.path.exists(full):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


# ---------------------------------------------------------------------------
# Auth (deliberately minimal for V1 demo — email-only, no password)
# ---------------------------------------------------------------------------
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400

    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO users (name, email, streak, created_at) VALUES (?,?,0,?)",
            (name or email.split("@")[0], email, now_iso()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    return jsonify(dict(row))


# ---------------------------------------------------------------------------
# Lecture ingestion: live recording / file upload / text paste
# ---------------------------------------------------------------------------
@app.route("/api/lectures", methods=["POST"])
def create_lecture():
    """
    Accepts JSON:
      user_id, title, subject, source_type ('live_recording'|'file_upload'|'text_paste')
      filename (optional, for uploads/recordings)
      transcript_text (optional, for text_paste - real extraction runs on this)
    """
    data = request.get_json(force=True)
    user_id = data.get("user_id")
    title = (data.get("title") or "Untitled Lecture").strip()
    subject = (data.get("subject") or "General").strip()
    source_type = data.get("source_type", "file_upload")
    filename = data.get("filename", "recording.webm")
    transcript_text = data.get("transcript_text", "")

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    # --- AI step 1: transcription (teacher-voice isolation happens here in prod) ---
    if source_type == "text_paste" and transcript_text.strip():
        transcript = transcript_text.strip()
    else:
        transcript = ai_engine.transcribe_audio(filename, subject)

    # --- AI step 2: extract exactly 3-5 core concepts ---
    concepts = ai_engine.extract_concepts(transcript, subject)

    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO lectures (user_id, title, subject, source_type, transcript, created_at) VALUES (?,?,?,?,?,?)",
        (user_id, title, subject, source_type, transcript, now_iso()),
    )
    lecture_id = cur.lastrowid
    for i, c in enumerate(concepts):
        conn.execute(
            "INSERT INTO concepts (lecture_id, order_index, concept_text) VALUES (?,?,?)",
            (lecture_id, i, c),
        )
    conn.commit()

    # --- Build the Day 1 quiz right away so the notification can deep-link to it ---
    quiz = ai_engine.generate_quiz(concepts, stage="day1", n_questions=3)
    for q in quiz:
        conn.execute(
            "INSERT INTO quiz_questions (lecture_id, stage, question, options_json, correct_index, explanation) VALUES (?,?,?,?,?,?)",
            (lecture_id, "day1", q["question"], json.dumps(q["options"]), q["correct_index"], q["explanation"]),
        )
    conn.commit()
    conn.close()

    scheduler.create_schedule_for_lecture(lecture_id, now_iso())

    return jsonify({
        "lecture_id": lecture_id,
        "title": title,
        "subject": subject,
        "concepts": concepts,
        "message": "Lecture processed. Day 1 quiz notification scheduled."
    }), 201


@app.route("/api/lectures/<int:lecture_id>", methods=["GET"])
def get_lecture(lecture_id):
    conn = get_conn()
    lecture = conn.execute("SELECT * FROM lectures WHERE id=?", (lecture_id,)).fetchone()
    if not lecture:
        return jsonify({"error": "not found"}), 404
    concepts = conn.execute(
        "SELECT concept_text FROM concepts WHERE lecture_id=? ORDER BY order_index", (lecture_id,)
    ).fetchall()
    stages = conn.execute("SELECT * FROM schedule WHERE lecture_id=?", (lecture_id,)).fetchall()
    conn.close()

    stage_info = []
    for s in stages:
        stage_info.append({
            "stage": s["stage"],
            "due_at": s["due_at"],
            "completed": bool(s["completed"]),
            "score": s["score"],
            "status": scheduler.stage_status(lecture, s),
            "badge": scheduler.BADGE_FOR_STAGE[s["stage"]],
        })
    stage_info.sort(key=lambda s: scheduler.STAGE_ORDER.index(s["stage"]))

    return jsonify({
        "id": lecture["id"], "title": lecture["title"], "subject": lecture["subject"],
        "source_type": lecture["source_type"], "created_at": lecture["created_at"],
        "concepts": [c["concept_text"] for c in concepts],
        "stages": stage_info,
    })


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/api/dashboard/<int:user_id>", methods=["GET"])
def dashboard(user_id):
    conn = get_conn()
    user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        return jsonify({"error": "user not found"}), 404

    lectures = conn.execute(
        "SELECT * FROM lectures WHERE user_id=? ORDER BY created_at DESC", (user_id,)
    ).fetchall()

    lecture_cards = []
    next_action = None
    for lec in lectures:
        stages = conn.execute("SELECT * FROM schedule WHERE lecture_id=?", (lec["id"],)).fetchall()
        stage_list = []
        for s in stages:
            status = scheduler.stage_status(lec, s)
            stage_list.append({
                "stage": s["stage"], "status": status, "score": s["score"],
                "badge": scheduler.BADGE_FOR_STAGE[s["stage"]],
            })
            if status == "available" and next_action is None:
                next_action = {"lecture_id": lec["id"], "title": lec["title"], "stage": s["stage"]}
        stage_list.sort(key=lambda s: scheduler.STAGE_ORDER.index(s["stage"]))
        lecture_cards.append({
            "id": lec["id"], "title": lec["title"], "subject": lec["subject"],
            "source_type": lec["source_type"], "created_at": lec["created_at"],
            "time_offset_minutes": lec["time_offset_minutes"],
            "stages": stage_list,
        })

    badges = conn.execute(
        "SELECT badge_name, COUNT(*) as n FROM badges WHERE user_id=? GROUP BY badge_name", (user_id,)
    ).fetchall()
    badge_counts = {b["badge_name"]: b["n"] for b in badges}
    conn.close()

    return jsonify({
        "user": {"id": user["id"], "name": user["name"], "email": user["email"], "streak": user["streak"]},
        "badge_counts": {
            "Starter": badge_counts.get("Starter", 0),
            "Walker": badge_counts.get("Walker", 0),
            "Flyer": badge_counts.get("Flyer", 0),
            "Supreme": badge_counts.get("Supreme", 0),
        },
        "next_action": next_action,
        "lectures": lecture_cards,
    })


# ---------------------------------------------------------------------------
# Day 1 — Starter quiz
# ---------------------------------------------------------------------------
@app.route("/api/lectures/<int:lecture_id>/quiz/day1", methods=["GET"])
def get_day1_quiz(lecture_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM quiz_questions WHERE lecture_id=? AND stage='day1'", (lecture_id,)
    ).fetchall()
    conn.close()
    questions = [{
        "id": r["id"], "question": r["question"], "options": json.loads(r["options_json"])
    } for r in rows]
    return jsonify({"lecture_id": lecture_id, "stage": "day1", "questions": questions})


@app.route("/api/lectures/<int:lecture_id>/quiz/day1/submit", methods=["POST"])
def submit_day1_quiz(lecture_id):
    data = request.get_json(force=True)
    answers = data.get("answers", {})  # {question_id: selected_index}
    user_id = data.get("user_id")

    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM quiz_questions WHERE lecture_id=? AND stage='day1'", (lecture_id,)
    ).fetchall()
    total = len(rows)
    correct = 0
    for r in rows:
        chosen = answers.get(str(r["id"]))
        if chosen is not None and int(chosen) == r["correct_index"]:
            correct += 1
    score = round(100 * correct / max(1, total), 1)
    conn.close()

    scheduler.mark_stage_complete(lecture_id, "day1", score)
    _award_badge(user_id, lecture_id, "Starter")
    _bump_streak(user_id)

    return jsonify({"score": score, "correct": correct, "total": total, "badge_awarded": "Starter"})


# ---------------------------------------------------------------------------
# Day 7 — Walker audio recap
# ---------------------------------------------------------------------------
@app.route("/api/lectures/<int:lecture_id>/recap/day7", methods=["GET"])
def get_day7_recap(lecture_id):
    conn = get_conn()
    lec = conn.execute("SELECT * FROM lectures WHERE id=?", (lecture_id,)).fetchone()
    concepts = [c["concept_text"] for c in conn.execute(
        "SELECT concept_text FROM concepts WHERE lecture_id=? ORDER BY order_index", (lecture_id,)
    ).fetchall()]
    conn.close()
    script = ai_engine.generate_recap_script(concepts, lec["subject"])
    return jsonify({"lecture_id": lecture_id, "stage": "day7", "recap_script": script, "duration_seconds": 60})


@app.route("/api/lectures/<int:lecture_id>/recap/day7/complete", methods=["POST"])
def complete_day7_recap(lecture_id):
    data = request.get_json(force=True)
    user_id = data.get("user_id")
    scheduler.mark_stage_complete(lecture_id, "day7", score=100)
    _award_badge(user_id, lecture_id, "Walker")
    _bump_streak(user_id)
    return jsonify({"badge_awarded": "Walker"})


# ---------------------------------------------------------------------------
# Day 30 — Flyer deep dive (graph + case study + analysis Qs)
# ---------------------------------------------------------------------------
@app.route("/api/lectures/<int:lecture_id>/deepdive/day30", methods=["GET"])
def get_day30_deepdive(lecture_id):
    conn = get_conn()
    lec = conn.execute("SELECT * FROM lectures WHERE id=?", (lecture_id,)).fetchone()
    concepts = [c["concept_text"] for c in conn.execute(
        "SELECT concept_text FROM concepts WHERE lecture_id=? ORDER BY order_index", (lecture_id,)
    ).fetchall()]
    conn.close()
    payload = ai_engine.generate_case_study(concepts, lec["subject"])
    payload["lecture_id"] = lecture_id
    payload["stage"] = "day30"
    return jsonify(payload)


@app.route("/api/lectures/<int:lecture_id>/deepdive/day30/submit", methods=["POST"])
def submit_day30_deepdive(lecture_id):
    data = request.get_json(force=True)
    user_id = data.get("user_id")
    responses = data.get("responses", [])  # free-text answers to analysis questions
    # V1 scoring heuristic: reward thoughtful (longer, non-empty) responses.
    score = round(min(100, sum(min(100, len(r.split()) * 8) for r in responses) / max(1, len(responses))), 1) if responses else 0
    scheduler.mark_stage_complete(lecture_id, "day30", score)
    _award_badge(user_id, lecture_id, "Flyer")
    _bump_streak(user_id)
    return jsonify({"score": score, "badge_awarded": "Flyer"})


# ---------------------------------------------------------------------------
# Day 45 — Supreme "Teach a Class" challenge
# ---------------------------------------------------------------------------
@app.route("/api/lectures/<int:lecture_id>/teach/day45", methods=["POST"])
def submit_teach_back(lecture_id):
    data = request.get_json(force=True)
    user_id = data.get("user_id")
    explanation = (data.get("explanation_text") or "").strip()
    if len(explanation) < 5:
        return jsonify({"error": "explanation_text is required"}), 400

    conn = get_conn()
    concepts = [c["concept_text"] for c in conn.execute(
        "SELECT concept_text FROM concepts WHERE lecture_id=? ORDER BY order_index", (lecture_id,)
    ).fetchall()]

    result = ai_engine.grade_teach_back(explanation, concepts)
    conn.execute(
        "INSERT INTO teach_submissions (lecture_id, explanation_text, coverage_score, feedback, passed, submitted_at) VALUES (?,?,?,?,?,?)",
        (lecture_id, explanation, result["coverage_score"], result["feedback"], int(result["passed"]), now_iso()),
    )
    conn.commit()
    conn.close()

    if result["passed"]:
        scheduler.mark_stage_complete(lecture_id, "day45", result["coverage_score"])
        _award_badge(user_id, lecture_id, "Supreme")
        _bump_streak(user_id)

    return jsonify(result)


# ---------------------------------------------------------------------------
# Exam Mode — surfaces weak subjects for targeted revision
# ---------------------------------------------------------------------------
@app.route("/api/exam-mode/<int:user_id>", methods=["GET"])
def exam_mode(user_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT l.subject as subject, s.stage as stage, s.score as score
        FROM schedule s
        JOIN lectures l ON l.id = s.lecture_id
        WHERE l.user_id=? AND s.completed=1 AND s.score IS NOT NULL
    """, (user_id,)).fetchall()
    conn.close()

    subject_scores = {}
    for r in rows:
        subject_scores.setdefault(r["subject"], []).append(r["score"])

    ranked = []
    for subject, scores in subject_scores.items():
        avg = round(sum(scores) / len(scores), 1)
        ranked.append({
            "subject": subject,
            "average_score": avg,
            "attempts": len(scores),
            "is_weak": avg < 70,
        })
    ranked.sort(key=lambda x: x["average_score"])  # weakest first

    return jsonify({"user_id": user_id, "subjects": ranked})


@app.route("/api/exam-mode/<int:user_id>/practice/<subject>", methods=["GET"])
def exam_mode_practice(user_id, subject):
    """Builds a mixed practice quiz pulling questions from every lecture the
    user has in this subject — the 'selectively revise weak subjects' flow."""
    conn = get_conn()
    lectures = conn.execute(
        "SELECT id FROM lectures WHERE user_id=? AND subject=?", (user_id, subject)
    ).fetchall()
    all_questions = []
    for lec in lectures:
        qs = conn.execute(
            "SELECT * FROM quiz_questions WHERE lecture_id=?", (lec["id"],)
        ).fetchall()
        for q in qs:
            all_questions.append({
                "id": q["id"], "lecture_id": q["lecture_id"],
                "question": q["question"], "options": json.loads(q["options_json"]),
            })
    conn.close()
    return jsonify({"subject": subject, "questions": all_questions})


# ---------------------------------------------------------------------------
# Badges helper + streaks
# ---------------------------------------------------------------------------
def _award_badge(user_id, lecture_id, badge_name):
    if not user_id:
        return
    conn = get_conn()
    existing = conn.execute(
        "SELECT id FROM badges WHERE user_id=? AND lecture_id=? AND badge_name=?",
        (user_id, lecture_id, badge_name),
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO badges (user_id, lecture_id, badge_name, awarded_at) VALUES (?,?,?,?)",
            (user_id, lecture_id, badge_name, now_iso()),
        )
        conn.commit()
    conn.close()


def _bump_streak(user_id):
    if not user_id:
        return
    conn = get_conn()
    conn.execute("UPDATE users SET streak = streak + 1, last_active_date=? WHERE id=?", (now_iso(), user_id))
    conn.commit()
    conn.close()


@app.route("/api/badges/<int:user_id>", methods=["GET"])
def list_badges(user_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT b.badge_name, b.awarded_at, l.title, l.subject
        FROM badges b JOIN lectures l ON l.id = b.lecture_id
        WHERE b.user_id=? ORDER BY b.awarded_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# DEV-ONLY: fast-forward a lecture's clock so Day 7/30/45 can be demoed
# without waiting real days. Remove/guard this route in production.
# ---------------------------------------------------------------------------
@app.route("/api/dev/fast-forward/<int:lecture_id>", methods=["POST"])
def fast_forward(lecture_id):
    data = request.get_json(force=True)
    minutes = int(data.get("minutes", 0))
    conn = get_conn()
    conn.execute(
        "UPDATE lectures SET time_offset_minutes = time_offset_minutes + ? WHERE id=?",
        (minutes, lecture_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"lecture_id": lecture_id, "added_minutes": minutes})


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=5000)
