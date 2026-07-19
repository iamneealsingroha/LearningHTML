# MANTHAN — Lecture Amnesia Fixer (Web Version)

A frictionless web app that fights the Ebbinghaus forgetting curve with
spaced retrieval practice, culminating in a Feynman-technique teach-back.
Named for *manthan* (मंथन) — the Sanskrit word for "churning," as in the
churning of the ocean that yields nectar from milk: the product churns
lecture noise into locked-in retention over 45 days.

## What's inside

```
manthan/
├── backend/
│   ├── app.py            Flask API + serves the frontend
│   ├── db.py              SQLite schema + connection helper
│   ├── ai_engine.py        MOCK AI pipeline (transcription, concept
│   │                        extraction, quiz/recap/case-study/teach-back
│   │                        generation) — see docstring for prod swap-in
│   ├── scheduler.py        Day 1/7/30/45 spaced-repetition scheduling
│   └── requirements.txt
└── frontend/
    ├── index.html
    ├── css/style.css       Visual identity ("churn ring" progress dial,
    │                        ocean-indigo + churned-gold palette)
    └── js/app.js            All API calls + UI rendering, MediaRecorder
                               integration for live lecture recording
```

## Running it

```bash
cd backend
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000** — the Flask app serves the frontend directly,
so there's nothing separate to run. A fresh `manthan.db` SQLite file is
created automatically on first run.

## The product loop, end to end

1. **Add a Lecture** (dashboard → "+ Add Lecture"): record live via the
   browser mic, upload an audio/video file, or paste a transcript/notes.
2. On submit, the backend "AI pipeline" (`ai_engine.py`) transcribes and
   extracts exactly 3–5 core concepts, and `scheduler.py` schedules the
   Day 1 / 7 / 30 / 45 review stages against the real lecture timestamp.
3. Each lecture card shows a **churn ring** (0/4 → 4/4) and a stage track
   (D1 · Starter → D7 · Walker → D30 · Flyer → D45 · Supreme). A stage
   is greyed out until due, glows gold when available, and turns teal
   once completed.
4. **Day 1 — Starter**: a 3-question quiz generated from the extracted
   concepts.
5. **Day 7 — Walker**: a 60-second recap script (swap in TTS for real
   audio in production).
6. **Day 30 — Flyer**: an interactive trend graph, a generated real-world
   case study, and open-ended analysis questions.
7. **Day 45 — Supreme**: the "Teach a Class" challenge — the student
   explains the subject back in their own words; a coverage-scoring
   heuristic (swap for an LLM rubric-grader in prod) decides pass/fail.
8. **Exam Mode**: ranks every subject by average review score, flags
   anything under 70% as "Needs work," and builds a mixed practice quiz
   pulled from every lecture in that subject.
9. **Badges tab**: lifetime counts of Starter/Walker/Flyer/Supreme badges
   plus a chronological award history.

A **dev-only "fast-forward" button** appears next to locked stages so you
can demo Day 7/30/45 without literally waiting weeks — remove or gate this
route (`/api/dev/fast-forward`) before shipping.

## Where the mock AI lives (and how to make it real)

Every mock is isolated in `backend/ai_engine.py` with a docstring at the
top of the file explaining exactly what production API to swap in for each
function (speech-to-text + speaker diarization for teacher-voice isolation,
an LLM call for concept/quiz/case-study generation, TTS for the audio
recap, and an LLM rubric-grader for the teach-back). Function signatures
are stable, so swapping the internals doesn't require touching `app.py`.

## Success-metric instrumentation hooks

The schema already captures what V1's test plan needs:
- `lectures.source_type` → live recording vs. file upload adoption
- `schedule.completed` / `completed_at` per stage → Starter→Walker→Flyer→
  Supreme progression funnel and drop-off
- `schedule.score` per stage, joined by subject → Exam Mode usage and
  which subjects get practiced ahead of test season
- A surprise 30-day quiz vs. control group would be layered on top as a
  separate `quiz_questions` stage tag (e.g. `"day30_surprise"`) reusing
  the same scheduler/grading path.
