// MANTHAN - Lecture Amnesia Fixer — frontend logic
// Talks to the Flask API. All endpoints are same-origin (served by app.py).

const API = ""; // same origin
let CURRENT_USER = null;
let mediaRecorder = null;
let recordedChunks = [];
let recording = false;

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// ---------------------------------------------------------------------------
// Toast helper
// ---------------------------------------------------------------------------
function toast(msg, ms = 2600) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), ms);
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed: ${res.status}`);
  }
  return res.json();
}

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = $("#login-name").value.trim();
  const email = $("#login-email").value.trim();
  try {
    const user = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ name, email }),
    });
    CURRENT_USER = user;
    $("#screen-login").classList.remove("active");
    $("#app-shell").classList.remove("hidden");
    $("#user-name-pill").textContent = user.name;
    await refreshDashboard();
  } catch (err) {
    toast("Login failed: " + err.message);
  }
});

// ---------------------------------------------------------------------------
// Tab navigation
// ---------------------------------------------------------------------------
$$(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".tab-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    const target = btn.dataset.screen;
    $$(".screen-panel").forEach((p) => p.classList.remove("active"));
    $("#screen-" + target).classList.add("active");
    if (target === "examMode") loadExamMode();
    if (target === "badges") loadBadges();
    if (target === "dashboard") refreshDashboard();
  });
});

// ---------------------------------------------------------------------------
// Dashboard rendering
// ---------------------------------------------------------------------------
const STAGE_LABEL = { day1: "D1", day7: "D7", day30: "D30", day45: "D45" };
const STAGE_BADGE = { day1: "Starter", day7: "Walker", day30: "Flyer", day45: "Supreme" };

async function refreshDashboard() {
  if (!CURRENT_USER) return;
  const data = await api(`/api/dashboard/${CURRENT_USER.id}`);
  $("#streak-pill").textContent = "🔥 " + data.user.streak;

  const list = $("#lecture-list");
  list.innerHTML = "";
  const empty = $("#empty-state");
  if (data.lectures.length === 0) {
    empty.classList.remove("hidden");
  } else {
    empty.classList.add("hidden");
  }

  const banner = $("#next-action-banner");
  if (data.next_action) {
    banner.classList.remove("hidden");
    banner.innerHTML = `<span class="naction-text">Ready now: <strong>${escapeHtml(data.next_action.title)}</strong> — ${stageFriendlyName(data.next_action.stage)}</span>
      <button class="btn btn-primary" onclick="openStage(${data.next_action.lecture_id}, '${data.next_action.stage}')">Do it now (2 min)</button>`;
  } else {
    banner.classList.add("hidden");
  }

  data.lectures.forEach((lec) => {
    list.appendChild(renderLectureCard(lec));
  });
}

function stageFriendlyName(stage) {
  return { day1: "Day 1 Quiz", day7: "Day 7 Audio Recap", day30: "Day 30 Deep Dive", day45: "Day 45 Teach-Back" }[stage] || stage;
}

function renderLectureCard(lec) {
  const card = document.createElement("div");
  card.className = "lecture-card";

  const completedCount = lec.stages.filter((s) => s.status === "completed").length;
  const pct = (completedCount / 4) * 100;
  const ring = document.createElement("div");
  ring.className = "churn-ring";
  ring.style.background = `conic-gradient(var(--gold) ${pct}%, rgba(255,255,255,0.08) ${pct}%)`;
  ring.innerHTML = `<div class="ring-center">${completedCount}/4</div>`;

  const info = document.createElement("div");
  info.className = "lecture-info";
  const sourceLabel = { live_recording: "🎙 Recorded", file_upload: "📁 Uploaded", text_paste: "📝 Text" }[lec.source_type] || lec.source_type;
  info.innerHTML = `
    <h4>${escapeHtml(lec.title)}</h4>
    <div class="lecture-meta">
      <span class="subject-chip">${escapeHtml(lec.subject)}</span>
      <span>${sourceLabel}</span>
      <span>${new Date(lec.created_at).toLocaleDateString()}</span>
    </div>
    <div class="stage-track">
      ${lec.stages.map((s) => `<span class="stage-dot ${s.status}">${STAGE_LABEL[s.stage]} · ${STAGE_BADGE[s.stage]}</span>`).join("")}
    </div>
  `;

  const actions = document.createElement("div");
  actions.className = "lecture-actions";
  const availableStage = lec.stages.find((s) => s.status === "available");
  if (availableStage) {
    const btn = document.createElement("button");
    btn.className = "btn btn-primary";
    btn.textContent = stageFriendlyName(availableStage.stage);
    btn.onclick = () => openStage(lec.id, availableStage.stage);
    actions.appendChild(btn);
  } else {
    const nextLocked = lec.stages.find((s) => s.status === "locked");
    const btn = document.createElement("button");
    btn.className = "btn btn-secondary";
    btn.disabled = !nextLocked;
    btn.textContent = nextLocked ? `Unlocks ${new Date(nextLocked.due_at).toLocaleDateString()}` : "All stages complete 🎉";
    actions.appendChild(btn);
    if (nextLocked) {
      const ff = document.createElement("button");
      ff.className = "btn btn-secondary";
      ff.style.marginTop = "8px";
      ff.textContent = "⏩ Dev: fast-forward";
      ff.onclick = async () => {
        await api(`/api/dev/fast-forward/${lec.id}`, { method: "POST", body: JSON.stringify({ minutes: 45 * 24 * 60 }) });
        toast("Fast-forwarded lecture clock for demo purposes");
        refreshDashboard();
      };
      actions.appendChild(document.createElement("br"));
      actions.appendChild(ff);
    }
  }

  card.appendChild(ring);
  card.appendChild(info);
  card.appendChild(actions);
  return card;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

// ---------------------------------------------------------------------------
// Add Lecture modal
// ---------------------------------------------------------------------------
$("#btn-add-lecture").addEventListener("click", () => $("#modal-add-lecture").classList.remove("hidden"));
$$("[data-close-modal]").forEach((b) => b.addEventListener("click", (e) => {
  e.target.closest(".modal-overlay").classList.add("hidden");
  stopRecordingIfActive();
}));

$$(".source-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".source-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    $$(".source-panel").forEach((p) => p.classList.add("hidden"));
    $("#source-panel-" + { live_recording: "live", file_upload: "file", text_paste: "text" }[btn.dataset.source]).classList.remove("hidden");
  });
});

$("#btn-record").addEventListener("click", async () => {
  if (!recording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordedChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => recordedChunks.push(e.data);
      mediaRecorder.start();
      recording = true;
      $("#btn-record").textContent = "■ Stop Recording";
      $("#btn-record").classList.add("recording");
      $("#record-status").textContent = "Recording... (teacher-voice isolation runs after upload)";
    } catch (err) {
      toast("Microphone access denied or unavailable.");
    }
  } else {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach((t) => t.stop());
    recording = false;
    $("#btn-record").textContent = "● Start Recording";
    $("#btn-record").classList.remove("recording");
    $("#record-status").textContent = "Captured " + recordedChunks.length + " chunk(s). Ready to process.";
  }
});

function stopRecordingIfActive() {
  if (recording && mediaRecorder) {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach((t) => t.stop());
    recording = false;
  }
}

$("#add-lecture-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const title = $("#lecture-title").value.trim();
  const subject = $("#lecture-subject").value.trim();
  const activeSource = $(".source-btn.active").dataset.source;

  let payload = { user_id: CURRENT_USER.id, title, subject, source_type: activeSource };

  if (activeSource === "text_paste") {
    payload.transcript_text = $("#lecture-transcript").value.trim();
    if (!payload.transcript_text) return toast("Paste some transcript/notes text first.");
  } else if (activeSource === "file_upload") {
    const f = $("#lecture-file").files[0];
    payload.filename = f ? f.name : "upload.mp4";
  } else {
    payload.filename = "live-recording-" + Date.now() + ".webm";
  }

  $("#processing-indicator").classList.remove("hidden");
  try {
    const result = await api("/api/lectures", { method: "POST", body: JSON.stringify(payload) });
    toast("Lecture processed — " + result.concepts.length + " core concepts extracted.");
    $("#modal-add-lecture").classList.add("hidden");
    $("#add-lecture-form").reset();
    await refreshDashboard();
  } catch (err) {
    toast("Error: " + err.message);
  } finally {
    $("#processing-indicator").classList.add("hidden");
  }
});

// ---------------------------------------------------------------------------
// Stage modal: routes to quiz / recap / deepdive / teach
// ---------------------------------------------------------------------------
async function openStage(lectureId, stage) {
  $("#modal-stage").classList.remove("hidden");
  $("#stage-modal-title").textContent = stageFriendlyName(stage);
  const body = $("#stage-modal-body");
  body.innerHTML = "<p>Loading...</p>";

  if (stage === "day1") return renderDay1Quiz(lectureId, body);
  if (stage === "day7") return renderDay7Recap(lectureId, body);
  if (stage === "day30") return renderDay30DeepDive(lectureId, body);
  if (stage === "day45") return renderDay45Teach(lectureId, body);
}
window.openStage = openStage;

async function renderDay1Quiz(lectureId, body) {
  const data = await api(`/api/lectures/${lectureId}/quiz/day1`);
  const answers = {};
  body.innerHTML = data.questions.map((q, qi) => `
    <div class="quiz-question" data-qid="${q.id}">
      <p>${qi + 1}. ${escapeHtml(q.question)}</p>
      ${q.options.map((opt, oi) => `<button type="button" class="quiz-option" data-qid="${q.id}" data-oi="${oi}">${escapeHtml(opt)}</button>`).join("")}
    </div>
  `).join("") + `<button id="submit-day1" class="btn btn-primary btn-block" style="margin-top:10px;">Submit Quiz</button><div id="day1-result"></div>`;

  $$(".quiz-option", body).forEach((btn) => {
    btn.addEventListener("click", () => {
      const qid = btn.dataset.qid;
      $$(`.quiz-option[data-qid="${qid}"]`, body).forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
      answers[qid] = btn.dataset.oi;
    });
  });

  $("#submit-day1", body).addEventListener("click", async () => {
    const result = await api(`/api/lectures/${lectureId}/quiz/day1/submit`, {
      method: "POST",
      body: JSON.stringify({ user_id: CURRENT_USER.id, answers }),
    });
    $("#day1-result", body).innerHTML = `<div class="result-banner ${result.score >= 60 ? "pass" : "fail"}">
      Scored ${result.score}% (${result.correct}/${result.total}) — 🏅 Starter badge earned!</div>`;
    toast("🏅 Starter badge earned!");
    refreshDashboard();
  });
}

async function renderDay7Recap(lectureId, body) {
  const data = await api(`/api/lectures/${lectureId}/recap/day7`);
  body.innerHTML = `
    <p class="subtle">60-second audio recap script (production version plays real TTS audio):</p>
    <div class="recap-script-box">${escapeHtml(data.recap_script)}</div>
    <button id="complete-day7" class="btn btn-primary btn-block" style="margin-top:14px;">Mark Recap Listened</button>
    <div id="day7-result"></div>
  `;
  $("#complete-day7", body).addEventListener("click", async () => {
    await api(`/api/lectures/${lectureId}/recap/day7/complete`, { method: "POST", body: JSON.stringify({ user_id: CURRENT_USER.id }) });
    $("#day7-result", body).innerHTML = `<div class="result-banner pass">🥾 Walker badge earned!</div>`;
    toast("🥾 Walker badge earned!");
    refreshDashboard();
  });
}

async function renderDay30DeepDive(lectureId, body) {
  const data = await api(`/api/lectures/${lectureId}/deepdive/day30`);
  const max = Math.max(...data.graph_values);
  body.innerHTML = `
    <div class="graph-wrap">
      <div class="mini-bar-row">
        ${data.graph_values.map((v) => `<div class="mini-bar" style="height:${(v / max) * 100}%" title="${v}"></div>`).join("")}
      </div>
    </div>
    <p><strong>Case study:</strong> ${escapeHtml(data.case_study)}</p>
    <div id="analysis-qs">
      ${data.analysis_questions.map((q, i) => `<p>${escapeHtml(q)}</p><textarea class="long-answer" data-qi="${i}" rows="2" placeholder="Your analysis..."></textarea>`).join("")}
    </div>
    <button id="submit-day30" class="btn btn-primary btn-block">Submit Analysis</button>
    <div id="day30-result"></div>
  `;
  $("#submit-day30", body).addEventListener("click", async () => {
    const responses = $$(".long-answer", body).map((t) => t.value.trim());
    const result = await api(`/api/lectures/${lectureId}/deepdive/day30/submit`, {
      method: "POST", body: JSON.stringify({ user_id: CURRENT_USER.id, responses }),
    });
    $("#day30-result", body).innerHTML = `<div class="result-banner pass">🪁 Flyer badge earned! (Depth score: ${result.score}%)</div>`;
    toast("🪁 Flyer badge earned!");
    refreshDashboard();
  });
}

async function renderDay45Teach(lectureId, body) {
  body.innerHTML = `
    <p class="subtle">Explain this subject out loud (or typed) like you're teaching it to a classmate who missed the lecture. Cover the "why", not just the "what".</p>
    <textarea id="teach-explanation" class="long-answer" rows="6" placeholder="Start explaining..."></textarea>
    <button id="submit-teach" class="btn btn-primary btn-block">Submit Teach-Back</button>
    <div id="teach-result"></div>
  `;
  $("#submit-teach", body).addEventListener("click", async () => {
    const text = $("#teach-explanation", body).value.trim();
    if (text.length < 5) return toast("Write or dictate your explanation first.");
    const result = await api(`/api/lectures/${lectureId}/teach/day45`, {
      method: "POST", body: JSON.stringify({ user_id: CURRENT_USER.id, explanation_text: text }),
    });
    $("#teach-result", body).innerHTML = `<div class="result-banner ${result.passed ? "pass" : "fail"}">
      Coverage: ${result.coverage_score}% — ${escapeHtml(result.feedback)}
      ${result.passed ? " 👑 Supreme badge earned!" : " Try adding more detail and resubmit."}</div>`;
    if (result.passed) { toast("👑 Supreme badge earned! Fully certified."); refreshDashboard(); }
  });
}

// ---------------------------------------------------------------------------
// Exam Mode
// ---------------------------------------------------------------------------
async function loadExamMode() {
  const data = await api(`/api/exam-mode/${CURRENT_USER.id}`);
  const list = $("#exam-subject-list");
  if (data.subjects.length === 0) {
    list.innerHTML = `<p class="subtle">No scored reviews yet. Complete a Day 1 quiz to populate Exam Mode.</p>`;
    return;
  }
  list.innerHTML = data.subjects.map((s, i) => `
    <div class="exam-subject-row ${s.is_weak ? "weak" : ""}">
      <span class="exam-rank">#${i + 1}</span>
      <span class="exam-subject-name">${escapeHtml(s.subject)} ${s.is_weak ? '<span class="weak-tag">Needs work</span>' : ""}</span>
      <div class="exam-score-bar"><div class="exam-score-fill ${s.average_score >= 70 ? "strong" : ""}" style="width:${s.average_score}%"></div></div>
      <span class="exam-score-label">${s.average_score}%</span>
      <button class="btn btn-secondary" onclick="practiceSubject('${encodeURIComponent(s.subject)}')">Practice</button>
    </div>
  `).join("");
  $("#exam-quiz-area").classList.add("hidden");
}

async function practiceSubject(encodedSubject) {
  const subject = decodeURIComponent(encodedSubject);
  const data = await api(`/api/exam-mode/${CURRENT_USER.id}/practice/${encodeURIComponent(subject)}`);
  const area = $("#exam-quiz-area");
  area.classList.remove("hidden");
  if (data.questions.length === 0) {
    area.innerHTML = `<p class="subtle">No practice questions available yet for ${escapeHtml(subject)}.</p>`;
    return;
  }
  area.innerHTML = `<h3 class="section-sub">Practicing: ${escapeHtml(subject)}</h3>` + data.questions.map((q, qi) => `
    <div class="quiz-question">
      <p>${qi + 1}. ${escapeHtml(q.question)}</p>
      ${q.options.map((opt) => `<button type="button" class="quiz-option">${escapeHtml(opt)}</button>`).join("")}
    </div>
  `).join("");
  $$(".quiz-option", area).forEach((btn) => {
    btn.addEventListener("click", () => btn.classList.toggle("selected"));
  });
}
window.practiceSubject = practiceSubject;

// ---------------------------------------------------------------------------
// Badges tab
// ---------------------------------------------------------------------------
async function loadBadges() {
  const dash = await api(`/api/dashboard/${CURRENT_USER.id}`);
  const grid = $("#badge-summary-grid");
  const icons = { Starter: "🏅", Walker: "🥾", Flyer: "🪁", Supreme: "👑" };
  grid.innerHTML = Object.entries(dash.badge_counts).map(([name, n]) => `
    <div class="badge-tile">
      <span class="badge-icon">${icons[name]}</span>
      <div class="badge-count">${n}</div>
      <div class="badge-label">${name}</div>
    </div>
  `).join("");

  const history = await api(`/api/badges/${CURRENT_USER.id}`);
  const hist = $("#badge-history");
  if (history.length === 0) {
    hist.innerHTML = `<p class="subtle">No badges yet — complete a Day 1 quiz to earn your first Starter badge.</p>`;
    return;
  }
  hist.innerHTML = history.map((h) => `
    <div class="badge-history-row">
      <span>${icons[h.badge_name] || "🏅"} ${h.badge_name} — ${escapeHtml(h.title)} <span class="subject-chip">${escapeHtml(h.subject)}</span></span>
      <span class="bh-when">${new Date(h.awarded_at).toLocaleString()}</span>
    </div>
  `).join("");
}
