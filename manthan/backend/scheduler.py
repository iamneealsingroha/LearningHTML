"""
MANTHAN - Spaced repetition scheduler.
Implements the Day 1 / Day 7 / Day 30 / Day 45 intervention points chosen to
flatten the Ebbinghaus decay curve R = e^(-t/S):
  Day 1  -> Starter  (arrests the steepest part of the curve, ~1 day -> ~33% R)
  Day 7  -> Walker   (re-strengthens before the ~19% R point)
  Day 30 -> Flyer    (deep encoding before the ~10% R point)
  Day 45 -> Supreme  (retrieval via teaching = strongest encoding method)
"""
import datetime
from db import get_conn, now_iso

STAGE_OFFSETS_MINUTES = {
    # Real-world offsets in days, expressed as minutes so the dev/demo
    # "time_offset_minutes" field can compress them for testing.
    "day1": 1 * 24 * 60,
    "day7": 7 * 24 * 60,
    "day30": 30 * 24 * 60,
    "day45": 45 * 24 * 60,
}

BADGE_FOR_STAGE = {
    "day1": "Starter",
    "day7": "Walker",
    "day30": "Flyer",
    "day45": "Supreme",
}

STAGE_ORDER = ["day1", "day7", "day30", "day45"]


def create_schedule_for_lecture(lecture_id, created_at_iso):
    created_at = datetime.datetime.fromisoformat(created_at_iso)
    conn = get_conn()
    for stage, offset_min in STAGE_OFFSETS_MINUTES.items():
        due_at = created_at + datetime.timedelta(minutes=offset_min)
        conn.execute(
            "INSERT OR IGNORE INTO schedule (lecture_id, stage, due_at, completed) VALUES (?,?,?,0)",
            (lecture_id, stage, due_at.isoformat()),
        )
    conn.commit()
    conn.close()


def effective_now(lecture_row):
    """Applies the lecture's dev-only time_offset_minutes so demos don't
    require literally waiting 45 days."""
    offset = lecture_row["time_offset_minutes"] or 0
    return datetime.datetime.utcnow() + datetime.timedelta(minutes=offset)


def stage_status(lecture_row, stage_row):
    if stage_row["completed"]:
        return "completed"
    due_at = datetime.datetime.fromisoformat(stage_row["due_at"])
    if effective_now(lecture_row) >= due_at:
        return "available"
    return "locked"


def mark_stage_complete(lecture_id, stage, score=None):
    conn = get_conn()
    conn.execute(
        "UPDATE schedule SET completed=1, completed_at=?, score=? WHERE lecture_id=? AND stage=?",
        (now_iso(), score, lecture_id, stage),
    )
    conn.commit()
    conn.close()
