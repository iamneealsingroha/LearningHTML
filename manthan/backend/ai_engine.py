"""
MANTHAN - Lecture Amnesia Fixer
AI pipeline for the V1 web app.

IMPORTANT (read me before deploying):
This module is a clearly-isolated MOCK of the AI pipeline described in the
product spec ("teacher-voice isolation -> transcription -> 3-5 concept
extraction -> quiz/recap/case-study/teach-back generation"). It runs fully
offline with no external calls, so the whole app is runnable/demoable with
zero API keys.

To go to production, swap the internals of the functions below for:
  - transcribe_audio()      -> a speech-to-text + speaker-isolation API
                                (e.g. Whisper / AssemblyAI with speaker
                                diarization to isolate the teacher's voice)
  - extract_concepts()      -> an LLM call (e.g. Claude via the Messages API)
                                prompted to return exactly 3-5 core concepts
                                as strict JSON
  - generate_quiz()         -> an LLM call prompted for N MCQs as strict JSON
  - generate_recap_script() -> an LLM call for a <=60-second spoken script,
                                then a TTS API to render audio
  - generate_case_study()   -> an LLM call for a real-world case study +
                                a small numeric series for the trend graph
  - grade_teach_back()      -> an LLM call comparing the student's spoken/
                                typed explanation against the concept list,
                                returning a coverage score + feedback

The function signatures are deliberately kept stable so that swap-in is a
drop-in replacement with no changes needed to app.py.
"""
import re
import random
import hashlib

STOPWORDS = set("""
a an the of to in on for and or is are was were be been being with this that
these those it its as at by from into over under about than then so such not
we you they i he she his her their our your can will would should could may
might do does did have has had also which who whom
""".split())


def _sentences(text):
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 0]


def _keywordify(sentence, top_n=6):
    words = re.findall(r"[A-Za-z][A-Za-z\-]+", sentence.lower())
    keywords = [w for w in words if w not in STOPWORDS and len(w) > 3]
    return keywords[:top_n]


def transcribe_audio(filename, subject):
    """MOCK: In production this isolates the teacher's voice (speaker
    diarization) and returns a clean transcript. Here we synthesize a
    plausible placeholder transcript since we have no real audio model."""
    return (
        f"[Auto-transcript placeholder for uploaded file '{filename}']. "
        f"This lecture on {subject} covered several core ideas, worked "
        f"through examples, and connected them to prior topics. "
        f"(Swap ai_engine.transcribe_audio with a real speech-to-text + "
        f"speaker-isolation API to produce a real transcript.)"
    )


def extract_concepts(transcript, subject, min_n=3, max_n=5):
    """MOCK concept extraction. Real version: single LLM call asking for
    3-5 core concepts as JSON. Here we do light heuristic extraction from
    real pasted text, or fall back to templated concepts for placeholder
    (audio/video) transcripts."""
    if "Auto-transcript placeholder" in transcript:
        # Templated fallback so the demo still has believable content
        templates = [
            f"Core definition and scope of {subject}",
            f"The key mechanism/process taught in this {subject} session",
            f"A worked example illustrating {subject} in practice",
            f"Common misconception or edge case in {subject}",
            f"How today's {subject} topic connects to the next lecture",
        ]
        n = random.randint(min_n, max_n)
        return templates[:n]

    sentences = _sentences(transcript)
    if not sentences:
        return [f"Core idea from {subject} lecture"]

    # naive salience score = sentence length + keyword density, dedup by keyword overlap
    scored = sorted(sentences, key=lambda s: len(_keywordify(s)) + len(s.split()) * 0.05, reverse=True)
    picked, used_keys = [], set()
    for s in scored:
        keys = set(_keywordify(s, 4))
        if keys & used_keys and len(picked) > 0:
            continue
        picked.append(s.strip().rstrip('.') + '.')
        used_keys |= keys
        if len(picked) >= max_n:
            break
    if len(picked) < min_n:
        for s in sentences:
            if s not in picked:
                picked.append(s)
            if len(picked) >= min_n:
                break
    return picked[:max_n]


def generate_quiz(concepts, stage="day1", n_questions=3):
    """MOCK quiz generator: builds simple recognition MCQs from the concept
    list with plausible distractors drawn from other concepts."""
    questions = []
    pool = concepts[:]
    for i in range(min(n_questions, len(concepts))):
        correct = concepts[i]
        distractor_pool = [c for j, c in enumerate(pool) if j != i]
        distractors = random.sample(distractor_pool, k=min(2, len(distractor_pool)))
        while len(distractors) < 2:
            distractors.append("None of the concepts covered in this lecture")
        options = distractors + [correct]
        random.shuffle(options)
        correct_index = options.index(correct)
        questions.append({
            "question": f"Which of these was a core concept covered in this lecture?",
            "options": options,
            "correct_index": correct_index,
            "explanation": f"'{correct}' was one of the {len(concepts)} core concepts extracted from this session."
        })
    return questions


def generate_recap_script(concepts, subject):
    """MOCK 60-second audio recap script (production: feed to a TTS API)."""
    body = " ".join(f"{i+1}. {c}" for i, c in enumerate(concepts))
    return (
        f"Quick 60-second recap of your {subject} lecture from last week. "
        f"Here are the core ideas: {body} "
        f"Keep these fresh — you'll be tested on them again in three weeks."
    )


def generate_case_study(concepts, subject):
    """MOCK deep-dive content for Day 30: an interactive graph's data series
    plus a real-world case study paragraph and analysis questions."""
    # synthetic trend data representing e.g. adoption/impact over time
    graph_points = [round(10 + i * random.uniform(3, 9), 1) for i in range(8)]
    case_study = (
        f"Consider a real-world scenario where the principles of {subject} "
        f"directly explain an observed outcome, tying together: "
        + "; ".join(concepts) + ". Analyze how each concept contributes."
    )
    analysis_questions = [
        f"How does '{concepts[0]}' change the outcome in the case study above?",
        f"Where would '{concepts[-1]}' break down if a key assumption changed?",
        "What single modification would most improve the outcome, and why?",
    ]
    return {
        "graph_labels": [f"Week {i+1}" for i in range(len(graph_points))],
        "graph_values": graph_points,
        "case_study": case_study,
        "analysis_questions": analysis_questions,
    }


def grade_teach_back(explanation_text, concepts):
    """MOCK grading for the Day 45 'Teach a Class' challenge. Real version:
    LLM call comparing explanation against concepts + rubric, returning a
    structured critique. Here: keyword-overlap coverage heuristic."""
    explanation_keywords = set(_keywordify(explanation_text, top_n=999))
    covered = 0
    missed = []
    for c in concepts:
        concept_keywords = set(_keywordify(c, top_n=999))
        overlap = concept_keywords & explanation_keywords
        if len(overlap) >= max(1, len(concept_keywords) // 3):
            covered += 1
        else:
            missed.append(c)

    coverage = round(100 * covered / max(1, len(concepts)), 1)
    passed = coverage >= 70 and len(explanation_text.split()) >= 40

    if passed:
        feedback = "Strong teach-back — you clearly explained most core concepts in your own words."
    else:
        gaps = "; ".join(missed) if missed else "depth and specificity"
        feedback = (
            f"Not quite certified yet. Your explanation needs more coverage of: {gaps}. "
            f"Try explaining it like you're teaching a curious 10-year-old — cover the 'why', not just the 'what'."
        )
    return {"coverage_score": coverage, "passed": passed, "feedback": feedback}
