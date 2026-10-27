// All question and model text is inserted with textContent, never innerHTML (SR7).
"use strict";

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;
  return n;
};
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
};

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = body.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : `HTTP ${r.status}`);
  }
  return body;
}
const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body ?? {}) });

const ERROR_TYPES = [
  ["concept-gap", "Concept gap"], ["terminology-confusion", "Terminology confusion"],
  ["misread-question", "Misread the question"], ["scenario-application", "Scenario application"],
];
const REPORT_REASONS = [
  ["wrong-answer", "Keyed answer is wrong"], ["factual-error", "Factual error"], ["ambiguous", "Ambiguous / two answers fit"],
  ["off-objective", "Tests a different objective"], ["typo-or-wording", "Typo or wording"], ["duplicate", "Duplicate"],
  ["too-easy", "Guessable / too easy"], ["other", "Other"],
];
const MODE_LABEL = { diagnostic: "Diagnostic", drill: "Targeted drill", exam: "Exam simulation", review: "Review misses" };
const ROLE_LABEL = { best: "Best answer", partial: "Technically correct, not the best", related: "Related concept", wrong: "Misconception" };
const LAST5_MARK = { right: "✓", guess: "?", wrong: "✗" };

// Log excerpt, config snippet, or command output shown under a stem; null when the question has none.
function exhibitEl(q) {
  return q.exhibit ? el("pre", "exhibit", q.exhibit) : null;
}

let chapters = [];
let names = {};
let S = null;          // active session
let timerHandle = null;

function show(view) {
  for (const v of document.querySelectorAll(".view")) v.hidden = v.id !== `v-${view}`;
  window.scrollTo(0, 0);
}

function selectedChapters() {
  return [...document.querySelectorAll("#chapter-list input:checked")].map((i) => Number(i.value));
}

// ---- home ---------------------------------------------------------------

async function loadStatus() {
  try {
    const s = await api("/api/status");
    const state = !s.health.reachable ? "not reachable" : s.health.model_present ? "ready" : "model not pulled";
    $("provider").textContent = `Local model: ${s.provider} · ${s.model} · ${state}`;
  } catch {
    $("provider").textContent = "Local model: unknown";
  }
}

async function loadHome() {
  chapters = await api("/api/chapters");
  const saved = new Set(store.get("ccst.chapters", [1]));
  const empty = chapters.filter((c) => c.draft + c.verified === 0);
  $("chapter-empty").textContent = empty.length
    ? `No questions yet: ${empty.map((c) => `Ch${c.chapter}`).join(", ")}` : "";
  $("chapter-list").replaceChildren(...chapters.filter((c) => c.draft + c.verified > 0).map((c) => {
    const active = c.draft + c.verified;
    const label = el("label", active ? "" : "empty");
    const box = el("input");
    box.type = "checkbox";
    box.value = String(c.chapter);
    box.checked = saved.has(c.chapter) && active > 0;
    box.disabled = active === 0;
    box.addEventListener("change", () => store.set("ccst.chapters", selectedChapters()));
    const text = el("span");
    text.append(el("span", null, c.title.replace(/^.*\| /, "")),
      el("small", null, active ? `${c.verified} verified · ${c.draft} draft` : "no questions yet"));
    label.append(box, text);
    return label;
  }));

  $("pool-actions").replaceChildren(...chapters.filter((c) => c.draft > 0).map((c) => {
    const b = el("button", "secondary small", `Review drafts: Ch${c.chapter} (${c.draft})`);
    b.type = "button";
    b.addEventListener("click", () => openQueue(c.chapter));
    return b;
  }));
  if (!$("pool-actions").children.length) $("pool-actions").append(el("span", "muted", "No drafts waiting for review."));

  $("gen-chapter").replaceChildren(...chapters.map((c) => {
    const o = el("option", null, `Ch${c.chapter}`);
    o.value = String(c.chapter);
    return o;
  }));

  const nameRows = await api(`/api/tracker?${chapters.map((c) => `chapter=${c.chapter}`).join("&")}`);
  names = Object.fromEntries(nameRows.map((r) => [r.objective, r.name]));
  show("home");
}

// ---- sessions -----------------------------------------------------------

async function startSession(mode) {
  $("home-msg").textContent = "";
  const chs = selectedChapters();
  if (!chs.length) { $("home-msg").textContent = "Select at least one chapter."; return; }
  const body = { mode, chapters: chs };
  if (mode === "drill") body.count = Number($("drill-count").value);
  if (mode === "exam") { body.count = Number($("exam-count").value); body.minutes = Number($("exam-minutes").value); }
  try {
    const s = await post("/api/sessions", body);
    // Recall-first notes stay in this page only; they are never sent (SR6).
    S = { ...s, i: 0, revealed: {}, recall: $("recall-first").checked && mode !== "exam", shown: {}, notes: {} };
    show("session");
    startTimer();
    renderQuestion();
  } catch (e) {
    $("home-msg").textContent = e.message;
  }
}

function startTimer() {
  clearInterval(timerHandle);
  $("s-timer").textContent = "";
  if (!S.time_limit_s) return;
  const end = new Date(S.started_at).getTime() + S.time_limit_s * 1000;
  const tick = () => {
    const left = Math.max(0, Math.round((end - Date.now()) / 1000));
    $("s-timer").textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
    $("s-timer").classList.toggle("low", left < 300);
    if (left === 0) { clearInterval(timerHandle); finishSession(true); }
  };
  tick();
  timerHandle = setInterval(tick, 1000);
}

function renderNavigator() {
  const nav = $("s-nav");
  nav.hidden = !S.deferred;
  if (!S.deferred) return;
  nav.replaceChildren(...S.questions.map((q, i) => {
    const a = S.answers[q.id];
    const b = el("button", [a ? "answered" : "", a?.flagged ? "flagged" : "", i === S.i ? "current" : ""].join(" "), String(i + 1));
    b.type = "button";
    b.setAttribute("aria-label", `Question ${i + 1}${a ? ", answered" : ""}${a?.flagged ? ", flagged" : ""}`);
    b.addEventListener("click", () => { S.i = i; renderQuestion(); });
    return b;
  }));
}

function renderQuestion() {
  const q = S.questions[S.i];
  const prior = S.answers[q.id];
  $("s-mode").textContent = MODE_LABEL[S.mode];
  const answered = Object.keys(S.answers).length;
  $("s-progress").textContent = `Question ${S.i + 1} of ${S.questions.length} · ${answered} answered`;
  $("s-meta").replaceChildren(el("span", `tag-${q.status}`, q.status === "draft" ? "Draft (unreviewed)" : "Verified"));
  $("s-stem").textContent = q.stem;
  $("s-exhibit").textContent = q.exhibit ?? "";
  $("s-exhibit").hidden = !q.exhibit;
  const hideOptions = S.recall && !prior && !S.shown[q.id];
  $("s-recall").hidden = !hideOptions;
  $("s-form").hidden = hideOptions;
  const note = S.notes[q.id]?.trim();
  $("s-recall-shown").textContent = note ? `Your answer before the options: ${note}` : "";
  $("s-recall-shown").hidden = hideOptions || !note;
  if (hideOptions) {
    $("s-recall-note").value = S.notes[q.id] ?? "";
    $("s-feedback").hidden = true;
    renderNavigator();
    $("s-recall-note").focus();
    return;
  }
  $("s-legend").textContent = q.type === "multi" ? `Choose ${q.choose}` : "Choose one";
  const type = q.type === "multi" ? "checkbox" : "radio";
  $("s-options").replaceChildren(...q.options.map((o) => {
    const label = el("label", "opt");
    label.dataset.key = o.key;
    const input = el("input");
    input.type = type;
    input.name = "opt";
    input.value = o.key;
    input.checked = !!prior?.selected.includes(o.key);
    const body = el("span");
    body.append(el("strong", null, `${o.key}. `), el("span", null, o.text));
    label.append(input, body);
    return label;
  }));
  for (const r of document.querySelectorAll("input[name=conf]")) r.checked = r.value === (prior?.confidence ?? "unsure");

  const revealed = S.revealed[q.id];
  $("s-feedback").hidden = true;
  $("s-submit").hidden = false;
  $("s-submit").disabled = false;
  $("s-submit").textContent = S.deferred ? (prior ? "Update answer" : "Save answer") : "Submit";
  $("s-next").hidden = true;
  $("s-prev").hidden = !S.deferred || S.i === 0;
  $("s-flag-wrap").hidden = !S.deferred;
  $("s-flag").checked = !!prior?.flagged;
  $("s-finish").textContent = S.mode === "exam" ? "Finish exam" : "Finish";
  renderNavigator();
  if (revealed) showFeedback(revealed.correct, revealed.question, prior.selected);
  else $("s-options").querySelector("input")?.focus();
}

async function submitAnswer(ev) {
  ev.preventDefault();
  const q = S.questions[S.i];
  const selected = [...$("s-options").querySelectorAll("input:checked")].map((i) => i.value);
  if (!selected.length) return;
  const confidence = document.querySelector("input[name=conf]:checked").value;
  const flagged = S.deferred && $("s-flag").checked;
  $("s-submit").disabled = true;
  try {
    const r = await post(`/api/sessions/${S.id}/answer`, { question_id: q.id, selected, confidence, flagged });
    S.answers[q.id] = { selected, confidence, flagged };
    if (S.deferred) {
      if (S.i < S.questions.length - 1) S.i++;
      renderQuestion();
    } else {
      S.revealed[q.id] = { correct: r.correct, question: r.question };
      $("s-progress").textContent = `Question ${S.i + 1} of ${S.questions.length} · ${Object.keys(S.answers).length} answered`;
      showFeedback(r.correct, r.question, selected);
    }
  } catch (e) {
    $("s-submit").disabled = false;
    alert(e.message);
  }
}

function markOptions(container, full, selected) {
  const byKey = Object.fromEntries(full.options.map((o) => [o.key, o]));
  for (const label of container.querySelectorAll(".opt")) {
    const key = label.dataset.key;
    const input = label.querySelector("input");
    if (input) input.disabled = true;
    if (full.answer.includes(key)) label.classList.add("correct");
    else if (selected.includes(key)) label.classList.add("wrong");
    if (!label.querySelector(".rationale")) {
      const r = el("span", "rationale");
      const role = ROLE_LABEL[byKey[key].role];
      if (role) r.append(el("em", "role", `${role}: `));
      r.append(byKey[key].rationale);
      label.querySelector("span").append(r);
    }
  }
}

function showFeedback(correct, full, selected) {
  markOptions($("s-options"), full, selected);
  const fb = $("s-feedback");
  fb.replaceChildren(
    el("p", correct ? "verdict-ok" : "verdict-bad", correct ? "Correct" : `Incorrect. Answer: ${full.answer.join(", ")}`),
    el("p", null, full.explanation),
    el("p", "muted", `Discriminator: ${full.discriminator_tested}`),
    el("p", "muted", `${full.objectives.map((o) => `${o} ${names[o] ?? ""}`.trim()).join(" · ")} · angle: ${full.angle} · ${full.id}`),
    questionTools(full, correct, S.id),
  );
  fb.hidden = false;
  $("s-submit").hidden = true;
  const last = S.i === S.questions.length - 1;
  $("s-next").hidden = last;
  if (!last) $("s-next").focus();
}

// Error type (for misses), report, and explain controls shared by feedback and reports.
function questionTools(full, correct, sessionId) {
  const tools = el("div", "tools");
  if (!correct && sessionId) {
    const sel = el("select");
    sel.setAttribute("aria-label", "Why did you miss it?");
    sel.append(el("option", null, "Why did you miss it?"));
    sel.options[0].value = "";
    for (const [v, t] of ERROR_TYPES) { const o = el("option", null, t); o.value = v; sel.append(o); }
    const status = el("span", "muted");
    sel.addEventListener("change", async () => {
      try {
        await post(`/api/sessions/${sessionId}/error-type`, { question_id: full.id, error_type: sel.value || null });
        status.textContent = sel.value ? "saved" : "";
      } catch (e) { status.textContent = e.message; }
    });
    tools.append(sel, status);
  }
  const explainBtn = el("button", "secondary small", "Explain this (local model)");
  explainBtn.type = "button";
  const out = el("div", "explain-out");
  out.hidden = true;
  explainBtn.addEventListener("click", () => runExplain(full.id, explainBtn, out));
  tools.append(explainBtn, reportControl(full.id), out);
  return tools;
}

function reportControl(questionId, onDone, preset) {
  const wrap = el("span");
  const btn = el("button", "secondary small danger", "Report this question");
  btn.type = "button";
  btn.addEventListener("click", () => {
    const sel = el("select");
    for (const [v, t] of REPORT_REASONS) { const o = el("option", null, t); o.value = v; sel.append(o); }
    if (preset) sel.value = preset;
    const note = el("input");
    note.type = "text";
    note.maxLength = 300;
    note.placeholder = "Optional note (kept for your records)";
    const go = el("button", "small danger", "Retire question");
    go.type = "button";
    go.addEventListener("click", async () => {
      try {
        await post(`/api/questions/${questionId}/report`, { reason: sel.value, note: note.value });
        wrap.replaceChildren(el("span", "muted", "Reported and retired. It will not be served again."));
        onDone?.();
      } catch (e) { alert(e.message); }
    });
    wrap.replaceChildren(sel, note, go);
  });
  wrap.append(btn);
  return wrap;
}

async function pollJob(job, onTick) {
  const t0 = Date.now();
  while (job.status === "queued" || job.status === "running") {
    onTick?.(((Date.now() - t0) / 60000).toFixed(1));
    await new Promise((r) => setTimeout(r, 3000));
    job = await api(`/api/jobs/${job.id}`);
  }
  return job;
}

async function runExplain(questionId, btn, out) {
  btn.disabled = true;
  out.hidden = false;
  try {
    const job = await pollJob(await post(`/api/questions/${questionId}/explain`),
      (m) => { out.textContent = `Asking the local model… ${m} min (CPU explanations can take a few minutes)`; });
    out.textContent = job.status === "done"
      ? `${job.result.explanation}\n\n(${job.result.provider}/${job.result.model}, ${job.result.seconds} s; check it against the objective file)`
      : `Explanation failed: ${job.error}`;
  } catch (e) {
    out.textContent = `Explanation failed: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

async function finishSession(timeUp = false) {
  if (!S) return;
  const unanswered = S.questions.length - Object.keys(S.answers).length;
  if (!timeUp && unanswered > 0 && S.deferred && !confirm(`${unanswered} question(s) unanswered. Finish anyway?`)) return;
  clearInterval(timerHandle);
  const rep = await post(`/api/sessions/${S.id}/finish`);
  renderReport(rep, timeUp);
}

// ---- report -------------------------------------------------------------

function table(target, head, rows) {
  const thead = el("thead");
  const tr = el("tr");
  for (const h of head) tr.append(el("th", null, h));
  thead.append(tr);
  const tbody = el("tbody");
  for (const r of rows) {
    const row = el("tr");
    for (const c of r) row.append(c instanceof Node ? (() => { const td = el("td"); td.append(c); return td; })() : el("td", null, c));
    tbody.append(row);
  }
  target.replaceChildren(thead, tbody);
}

function renderReport(rep, timeUp) {
  const s = rep.session;
  $("r-h").textContent = `${MODE_LABEL[s.mode]} results`;
  const pct = rep.percent === null ? "" : ` (${rep.percent}%)`;
  $("r-score").textContent = `${rep.correct} / ${s.mode === "exam" ? rep.total : rep.answered} correct${pct}`;
  $("r-note").textContent = [timeUp ? "Time ran out." : "", s.mode === "exam" ? `${rep.answered} of ${rep.total} answered; unanswered count as wrong.` : "",
    rep.weights_note ?? ""].filter(Boolean).join(" ");
  table($("r-domains"), ["Domain", "Correct", "%"],
    Object.entries(rep.by_domain).map(([d, v]) => [d, `${v.correct}/${v.answered}`, v.percent ?? "-"]));
  table($("r-objectives"), ["Objective", "Correct"],
    Object.entries(rep.by_objective).map(([o, v]) => [`${o} ${names[o] ?? ""}`, `${v.correct}/${v.answered}`]));

  $("r-items").replaceChildren(...rep.items.map((it, i) => {
    const q = it.question;
    const box = el("details", "item");
    const sum = el("summary", null, `${i + 1}. ${it.attempt ? (it.correct ? "Correct" : "Incorrect") : "Unanswered"} · ${q.id} · ${q.objectives[0]}`);
    box.append(sum, el("p", "stem", q.stem));
    const ex = exhibitEl(q);
    if (ex) box.append(ex);
    const opts = el("div");
    for (const o of q.options) {
      const label = el("div", "opt");
      label.dataset.key = o.key;
      const body = el("span");
      body.append(el("strong", null, `${o.key}. `), el("span", null, o.text));
      label.append(body);
      opts.append(label);
    }
    markOptions(opts, q, it.attempt?.selected ?? []);
    box.append(opts, el("p", null, q.explanation), el("p", "muted", `Discriminator: ${q.discriminator_tested}`));
    if (it.attempt) box.append(el("p", "muted", `Your confidence: ${it.attempt.confidence}`));
    if (!q.retired_reason) box.append(questionTools(q, it.correct || !it.attempt, s.id));
    // Misses start expanded where feedback was withheld until now.
    box.open = !it.correct && (s.mode === "exam" || s.mode === "diagnostic");
    return box;
  }));
  S = null;
  show("report");
}

// ---- draft review queue -------------------------------------------------

let Q = null;

async function openQueue(chapter) {
  Q = { chapter, items: await api(`/api/review-queue?chapter=${chapter}`), i: 0, verified: 0, reported: 0 };
  show("queue");
  renderQueueCard();
}

function renderQueueCard() {
  const card = $("q-card");
  $("q-h").textContent = `Review drafts: Chapter ${Q.chapter}`;
  $("q-progress").textContent = `${Q.items.length - Q.i} left · ${Q.verified} verified · ${Q.reported} reported this visit. ` +
    "Check the keyed answer, every rationale, and the facts against the book and objective file.";
  if (Q.i >= Q.items.length) {
    card.replaceChildren(el("p", null, "No drafts left in this chapter."));
    return;
  }
  const q = Q.items[Q.i];
  const opts = el("div");
  for (const o of q.options) {
    const label = el("div", "opt");
    label.dataset.key = o.key;
    const body = el("span");
    body.append(el("strong", null, `${o.key}. `), el("span", null, o.text));
    label.append(body);
    opts.append(label);
  }
  markOptions(opts, q, []);
  const verify = el("button", null, "Verify");
  verify.type = "button";
  verify.addEventListener("click", async () => {
    try { await post(`/api/questions/${q.id}/verify`); Q.verified++; Q.i++; renderQueueCard(); }
    catch (e) { alert(e.message); }
  });
  const skip = el("button", "secondary", "Skip for now");
  skip.type = "button";
  skip.addEventListener("click", () => { Q.i++; renderQueueCard(); });
  const actions = el("div", "row");
  actions.append(verify, skip, reportControl(q.id, () => { Q.reported++; setTimeout(() => { Q.i++; renderQueueCard(); }, 600); }));
  card.replaceChildren(
    el("p", "muted", `${q.id} · ${q.objectives.map((o, k) => `${o} ${q.objective_names[k]}`).join(" · ")}`),
    el("p", "muted", `Angle: ${q.angle} · difficulty ${q.difficulty} · ${q.type} · written by ${q.provider}/${q.model}`),
    el("p", "stem", q.stem), ...[exhibitEl(q)].filter(Boolean), opts,
    el("p", null, q.explanation), el("p", "muted", `Discriminator: ${q.discriminator_tested}`),
    actions,
  );
  verify.focus();
}

// ---- tracker, export, reset ----------------------------------------------

async function openProgress() {
  const chs = chapters.filter((c) => c.draft + c.verified > 0).map((c) => c.chapter);
  const rows = await api(`/api/tracker?${chs.map((c) => `chapter=${c}`).join("&")}`);
  const counts = rows.reduce((m, r) => ((m[r.status] = (m[r.status] || 0) + 1), m), {});
  $("p-summary").textContent = ["Weak", "Improving", "Solid", "New"].map((s) => `${s}: ${counts[s] || 0}`).join(" · ") +
    ". Solid needs 3 correct across 2+ sessions and 2+ angles with the last five at 80% or better." +
    " Correct answers marked Guess don't count toward mastery (shown as ?).";
  table($("p-table"), ["ID", "Objective", "Status", "Tries", "Last five", "Sure-wrong", "Main error", "Revisit"],
    rows.map((r) => [r.objective, r.name, el("span", `status-${r.status}`, r.status), String(r.attempts),
      r.last5_marks.map((m) => LAST5_MARK[m]).join(" "), r.sure_wrong_recent ? String(r.sure_wrong_recent) : "",
      r.dominant_error ?? "", r.revisit_due ? "due" : ""]));
  await renderTooEasy(chs);
  show("progress");
}

// Questions answered correctly and "sure" every recent time. "Keep" is remembered in this browser only.
async function renderTooEasy(chs) {
  const kept = new Set(store.get("ccst.keepEasy", []));
  const items = (await api(`/api/too-easy?${chs.map((c) => `chapter=${c}`).join("&")}`)).filter((q) => !kept.has(q.id));
  if (!items.length) { $("p-easy").replaceChildren(el("p", "muted", "None flagged yet.")); return; }
  $("p-easy").replaceChildren(...items.map((q) => {
    const box = el("details", "item");
    box.append(el("summary", null, `${q.id} · ${q.objectives[0]} ${q.objective_names[0]} · sure and correct ${q.attempts}×`),
      el("p", "stem", q.stem));
    const ex = exhibitEl(q);
    if (ex) box.append(ex);
    const opts = el("div");
    for (const o of q.options) {
      const label = el("div", "opt");
      label.dataset.key = o.key;
      const body = el("span");
      body.append(el("strong", null, `${o.key}. `), el("span", null, o.text));
      label.append(body);
      opts.append(label);
    }
    markOptions(opts, q, []);
    const keep = el("button", "secondary small", "Keep it");
    keep.type = "button";
    keep.addEventListener("click", () => { kept.add(q.id); store.set("ccst.keepEasy", [...kept]); box.remove(); });
    const actions = el("div", "row");
    actions.append(keep, reportControl(q.id, () => setTimeout(() => box.remove(), 600), "too-easy"));
    box.append(opts, actions);
    return box;
  }));
}

async function exportSummary() {
  const { text } = await api("/api/export");
  $("export-text").value = text;
  $("export-box").hidden = false;
}

async function resetProgress() {
  if (!confirm("Delete all sessions and answers? Question pools are kept. This cannot be undone.")) return;
  await post("/api/tracker/reset", { confirm: "RESET" });
  $("home-msg").textContent = "";
  $("export-box").hidden = true;
  alert("Progress reset.");
}

async function generate() {
  const chapter = Number($("gen-chapter").value);
  const count = Number($("gen-count").value);
  $("gen-btn").disabled = true;
  try {
    const job = await pollJob(await post("/api/generate", { chapter, count }),
      (m) => { $("gen-status").textContent = `Generating ${count} locally… ${m} min`; });
    if (job.status === "failed") $("gen-status").textContent = `Generation failed: ${job.error}`;
    else {
      const r = job.result;
      $("gen-status").textContent = `Added ${r.accepted.length} of ${r.requested} as draft (${r.rejected.length} rejected) in ${r.seconds} s.`;
    }
  } catch (e) {
    $("gen-status").textContent = `Generation failed: ${e.message}`;
  } finally {
    $("gen-btn").disabled = false;
    loadHome();
  }
}

// ---- wiring -------------------------------------------------------------

for (const b of document.querySelectorAll("[data-mode]")) b.addEventListener("click", () => startSession(b.dataset.mode));
$("sel-all").addEventListener("click", () => {
  for (const i of document.querySelectorAll("#chapter-list input:not(:disabled)")) i.checked = true;
  store.set("ccst.chapters", selectedChapters());
});
$("sel-none").addEventListener("click", () => {
  for (const i of document.querySelectorAll("#chapter-list input")) i.checked = false;
  store.set("ccst.chapters", []);
});
$("s-form").addEventListener("submit", submitAnswer);
const revealOptions = () => {
  const q = S.questions[S.i];
  S.notes[q.id] = $("s-recall-note").value;
  S.shown[q.id] = true;
  renderQuestion();
};
$("s-reveal").addEventListener("click", revealOptions);
$("s-recall-note").addEventListener("keydown", (e) => { if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); revealOptions(); } });
$("recall-first").checked = store.get("ccst.recall", false);
$("recall-first").addEventListener("change", () => store.set("ccst.recall", $("recall-first").checked));
$("s-next").addEventListener("click", () => { S.i++; renderQuestion(); });
$("s-prev").addEventListener("click", () => { S.i--; renderQuestion(); });
$("s-flag").addEventListener("change", async () => {
  const q = S.questions[S.i];
  if (!S.answers[q.id]) return; // sent with the answer instead
  S.answers[q.id].flagged = $("s-flag").checked;
  await post(`/api/sessions/${S.id}/flag`, { question_id: q.id, flagged: $("s-flag").checked }).catch(() => {});
  renderNavigator();
});
$("s-finish").addEventListener("click", () => finishSession(false));
$("progress-btn").addEventListener("click", openProgress);
$("export-btn").addEventListener("click", exportSummary);
$("copy-btn").addEventListener("click", () => navigator.clipboard?.writeText($("export-text").value));
$("reset-btn").addEventListener("click", resetProgress);
$("gen-btn").addEventListener("click", generate);
$("home-link").addEventListener("click", (e) => { e.preventDefault(); if (!S || confirm("Leave this session?")) { clearInterval(timerHandle); S = null; loadHome(); } });
for (const b of document.querySelectorAll(".back-btn")) b.addEventListener("click", loadHome);

loadStatus();
loadHome();
