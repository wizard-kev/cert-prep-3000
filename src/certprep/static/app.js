// All question text is inserted with textContent, never innerHTML (SR7).
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

// Sent with every request; the server refuses changes without it (SR-1). It changes each time the app starts.
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.content ?? "";

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json", "X-CSRF-Token": CSRF_TOKEN }, ...opts });
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
const MODE_LABEL = { practice: "Practice", focus: "Focus", exam: "Exam simulation",
  diagnostic: "Diagnostic (retired mode)", drill: "Targeted drill (now Practice)", review: "Review misses (now in Practice)" };
const CONF_LABEL = { 1: "Guessing", 2: "Unsure", 3: "Leaning", 4: "Confident", 5: "Certain" };
const STATUS_LABEL = { unreviewed: "Unreviewed", passive: "Passively-Validated", validated: "Validated", disputed: "Disputed", retired: "Retired" };
const ROLE_LABEL = { best: "Best answer", partial: "Technically correct, not the best", related: "Related concept", wrong: "Misconception" };
const LAST5_MARK = { right: "✓", guess: "?", wrong: "✗" };

// Log excerpt, config snippet, or command output shown under a stem; null when the question has none.
function exhibitEl(q) {
  return q.exhibit ? el("pre", "exhibit", q.exhibit) : null;
}

let certs = [];        // installed certifications
let cert = null;       // the one being studied (full cert.json plus exam defaults)
let sections = [];
let names = {};
let S = null;          // active session
let timerHandle = null;

// Settings saved by the CCST-only app (before v2) carry over once.
(function migrateOldPrefs() {
  const moves = [["ccst.recall", "certprep.recall"], ["ccst.keepEasy", "certprep.keepEasy.ccst-cyber"]];
  for (const [from, to] of moves) {
    if (store.get(to, null) === null && store.get(from, null) !== null) store.set(to, store.get(from, null));
  }
  const chs = store.get("ccst.chapters", null);
  if (Array.isArray(chs) && store.get("certprep.sections.ccst-cyber", null) === null) {
    store.set("certprep.sections.ccst-cyber", chs.map((n) => `C${String(n).padStart(2, "0")}`));
  }
  for (const [from] of moves) { try { localStorage.removeItem(from); } catch { /* ignore */ } }
  try { localStorage.removeItem("ccst.chapters"); } catch { /* ignore */ }
})();

const certPath = (rest = "") => `/api/certs/${encodeURIComponent(cert.id)}${rest}`;
const sectionQuery = (codes) => codes.map((c) => `section=${encodeURIComponent(c)}`).join("&");
const sectionsKey = () => `certprep.sections.${cert.id}`;

function show(view) {
  for (const v of document.querySelectorAll(".view")) v.hidden = v.id !== `v-${view}`;
  window.scrollTo(0, 0);
}

function selectedSections() {
  return [...document.querySelectorAll("#section-list input:checked")].map((i) => i.value);
}

// ---- certification --------------------------------------------------------

async function loadCert() {
  if (!certs.length) certs = await api("/api/certs");
  if (!certs.length) return false;
  const wanted = store.get("certprep.cert", null);
  const id = certs.some((c) => c.id === wanted) ? wanted : certs[0].id;
  if (!cert || cert.id !== id) {
    cert = await api(`/api/certs/${encodeURIComponent(id)}`);
    $("exam-count").value = cert.exam_defaults.questions;
    $("exam-minutes").value = cert.exam_defaults.minutes;
    $("exam-note").textContent = cert.weights.confidence === "official" ? "" : "Domain weights are estimates.";
  }
  const sel = $("cert-select");
  sel.replaceChildren(...certs.map((c) => { const o = el("option", null, c.short_name); o.value = c.id; return o; }));
  sel.value = cert.id;
  sel.hidden = certs.length < 2;
  $("cert-name").textContent = cert.short_name;
  $("cert-name").hidden = certs.length >= 2;
  return true;
}

// ---- home ---------------------------------------------------------------

async function loadHome() {
  drafts = await api("/api/wizard");
  renderDraftNote();
  if (!(await loadCert())) {
    $("section-list").replaceChildren();
    $("section-empty").textContent = "No certifications are installed yet. Use \"Add a certification\" at the top to set one up.";
    show("home");
    return;
  }
  sections = await api(certPath("/sections"));
  updatePackLink();
  const withQuestions = sections.filter((s) => s.served > 0);
  const saved = new Set(store.get(sectionsKey(), withQuestions.slice(0, 1).map((s) => s.code)));
  const empty = sections.filter((s) => s.served === 0);
  $("section-empty").textContent = empty.length
    ? `No questions yet: ${empty.map((s) => s.name).join(", ")}` : "";
  $("section-list").replaceChildren(...withQuestions.map((s) => {
    const label = el("label");
    const box = el("input");
    box.type = "checkbox";
    box.value = s.code;
    box.checked = saved.has(s.code);
    box.addEventListener("change", () => store.set(sectionsKey(), selectedSections()));
    const text = el("span");
    const checked = s.passive + s.validated;
    text.append(el("span", null, s.name),
      el("small", null, `${plural(s.served, "question")} · ${checked} answered or validated · ${s.unreviewed} unreviewed`));
    label.append(box, text);
    return label;
  }));

  const [disputed, recs] = await Promise.all([api(certPath("/disputes")), api(certPath("/recommendations"))]);
  $("dispute-count").textContent = String(disputed.length);
  $("dispute-row").hidden = disputed.length === 0;
  $("suggest-note").hidden = recs.length === 0;
  $("suggest-link").textContent = `Suggested: ${recs.length} objective${recs.length === 1 ? " could" : "s could"} use more questions`;

  const nameRows = sections.length ? await api(certPath(`/tracker?${sectionQuery(sections.map((s) => s.code))}`)) : [];
  names = Object.fromEntries(nameRows.map((r) => [r.objective, r.name]));
  show("home");
}

// ---- sessions -----------------------------------------------------------

// Practice and exam use the sections ticked on home; focus passes its chosen objectives.
async function startSession(mode, objectives = null) {
  const msg = mode === "focus" ? $("f-msg") : $("home-msg");
  msg.textContent = "";
  const body = { mode };
  if (mode === "focus") {
    Object.assign(body, { objectives, count: Number($("f-qcount").value) });
  } else {
    const secs = selectedSections();
    if (!secs.length) { msg.textContent = "Select at least one section."; return; }
    body.sections = secs;
  }
  if (mode === "practice") body.count = Number($("practice-count").value);
  if (mode === "exam") { body.count = Number($("exam-count").value); body.minutes = Number($("exam-minutes").value); }
  try {
    const s = await post(certPath("/sessions"), body);
    // Recall-first notes stay in this page only; they are never sent (SR6).
    S = { ...s, i: 0, revealed: {}, recall: $("recall-first").checked && mode !== "exam", shown: {}, notes: {}, held: {} };
    show("session");
    startTimer();
    renderQuestion();
  } catch (e) {
    msg.textContent = e.message;
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
    b.setAttribute("aria-label", `Question ${i + 1}${a ? ", answered" : ""}${a?.flagged ? ", marked for review" : ""}`);
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
  $("s-meta").replaceChildren(el("span", `tag tag-${q.status}`, STATUS_LABEL[q.status]));
  $("s-msg").textContent = "";
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
  // No default confidence: an honest rating each time is what makes progress tracking meaningful.
  for (const r of document.querySelectorAll("input[name=conf]")) {
    r.checked = prior ? Number(r.value) === prior.confidence : false;
    r.disabled = false;
  }

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
  renderExamReport(q);
  renderNavigator();
  if (revealed) showFeedback(revealed.correct, revealed.question, prior.selected);
  else $("s-options").querySelector("input")?.focus();
}

async function submitAnswer(ev) {
  ev.preventDefault();
  const q = S.questions[S.i];
  const selected = [...$("s-options").querySelectorAll("input:checked")].map((i) => i.value);
  if (!selected.length) { $("s-msg").textContent = q.type === "multi" ? `Choose ${q.choose} options.` : "Choose an option."; return; }
  const chosen = document.querySelector("input[name=conf]:checked");
  if (!chosen) { $("s-msg").textContent = "How sure are you? Pick 1 (Guessing) to 5 (Certain)."; $("s-conf").querySelector("input").focus(); return; }
  $("s-msg").textContent = "";
  const confidence = Number(chosen.value);
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

// A question's status changed (answered, Looks right, reported): keep the session's copy and its tag in step.
function setStatus(id, status) {
  if (!S) return;
  const q = S.questions.find((x) => x.id === id);
  if (!q) return;
  q.status = status;
  if (S.revealed[id]) S.revealed[id].question.status = status;
  if (S.questions[S.i] === q) $("s-meta").replaceChildren(el("span", `tag tag-${status}`, STATUS_LABEL[status]));
}

function showFeedback(correct, full, selected) {
  setStatus(full.id, full.status);
  markOptions($("s-options"), full, selected);
  for (const r of document.querySelectorAll("input[name=conf]")) r.disabled = true;
  const fb = $("s-feedback");
  fb.replaceChildren(
    el("p", correct ? "verdict-ok" : "verdict-bad", correct ? "Correct" : `Incorrect. Answer: ${full.answer.join(", ")}`),
    el("p", null, full.explanation),
    el("p", "muted", `Discriminator: ${full.discriminator_tested}`),
    el("p", "muted", `${full.objectives.map((o) => `${o} ${names[o] ?? ""}`.trim()).join(" · ")} · angle: ${full.angle} · ${full.id}`),
    questionTools(full, correct, S.id, selected),
  );
  fb.hidden = false;
  $("s-submit").hidden = true;
  const last = S.i === S.questions.length - 1;
  $("s-next").hidden = last;
  if (!last) $("s-next").focus();
}

// A prompt ready to copy into a Claude chat: read-only text, a Copy button, and where to paste it.
function promptWidget(title, text, hint) {
  const box = el("div", "prompt-widget");
  const area = el("textarea");
  area.readOnly = true;
  area.rows = 10;
  area.value = text;
  area.setAttribute("aria-label", title);
  const copy = el("button", "small", "Copy prompt");
  copy.type = "button";
  const status = el("span", "muted", `${text.length.toLocaleString()} characters. ${hint ?? "Paste it into a new chat at claude.ai."}`);
  copy.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(area.value); status.textContent = "Copied. Paste it into a new chat at claude.ai."; }
    catch { area.select(); status.textContent = "Press Ctrl+C to copy the selected text."; }
  });
  const row = el("div", "row");
  row.append(copy, status);
  box.append(el("strong", null, title), area, row);
  return box;
}

// Error type (for misses), Looks right, report, and ask-Claude controls shared by feedback and reports.
function questionTools(full, correct, sessionId, selected = []) {
  const tools = el("div", "tools");
  const formArea = el("div");
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
  const ask = el("button", "secondary small", "Ask Claude about this");
  ask.type = "button";
  const askOut = el("div");
  ask.addEventListener("click", async () => {
    ask.disabled = true;
    try {
      const q = selected.map((k) => `selected=${encodeURIComponent(k)}`).join("&");
      const { prompt } = await api(certPath(`/prompts/ask/${encodeURIComponent(full.id)}${q ? `?${q}` : ""}`));
      askOut.replaceChildren(promptWidget("Prompt about this question", prompt,
        "Paste it into a new chat at claude.ai. If Claude says the answer key is wrong, report the question here."));
    } catch (e) { askOut.replaceChildren(el("p", "msg", e.message)); }
    finally { ask.disabled = false; }
  });
  if (["unreviewed", "passive"].includes(full.status)) {
    const ok = el("button", "secondary small", "Looks right");
    ok.type = "button";
    ok.title = "Mark this question Validated: the answer and explanations are correct.";
    ok.addEventListener("click", async () => {
      try {
        await post(certPath(`/questions/${encodeURIComponent(full.id)}/validate`));
        ok.replaceWith(el("span", "muted", "Marked Validated."));
        setStatus(full.id, "validated");
      }
      catch (e) { ok.replaceWith(el("span", "msg", e.message)); }
    });
    tools.append(ok);
  }
  if (!correct && selected.length) tools.append(reportButton(full.id, sessionId, formArea, "Disagree with this answer?", "wrong-answer"));
  tools.append(ask, reportButton(full.id, sessionId, formArea, "Report a problem"));
  const wrap = el("div");
  wrap.append(tools, formArea, askOut);
  return wrap;
}

// The reason picker shared by every "report" control: a reason, an optional note, and a button.
function reportForm(preset, buttonText, onSend) {
  const form = el("div", "row");
  const sel = el("select");
  sel.setAttribute("aria-label", "What's wrong with it?");
  for (const [v, t] of REPORT_REASONS) { const o = el("option", null, t); o.value = v; sel.append(o); }
  if (preset) sel.value = preset;
  const note = el("input");
  note.type = "text";
  note.maxLength = 300;
  note.placeholder = "Optional note (kept for your records)";
  note.setAttribute("aria-label", "Note");
  const go = el("button", "small danger", buttonText);
  go.type = "button";
  go.addEventListener("click", () => onSend(sel.value, note.value, form));
  form.append(sel, note, go);
  return form;
}

// Report a question (outside a running exam): it's Disputed at once, and decided at the end.
function reportButton(questionId, sessionId, formArea, label, preset, onDone) {
  const btn = el("button", "secondary small danger", label);
  btn.type = "button";
  btn.addEventListener("click", () => {
    formArea.replaceChildren(reportForm(preset, "Report", async (reason, note, form) => {
      try {
        await post(certPath(`/questions/${encodeURIComponent(questionId)}/report`),
          { reason, note, ...(sessionId ? { session_id: sessionId } : {}) });
        form.replaceWith(el("p", "muted", sessionId
          ? "Taken out of play. You'll confirm or undo this report on the results page."
          : "Taken out of play. Confirm or undo it under Disputed questions."));
        setStatus(questionId, "disputed");
        onDone?.();
      } catch (e) { form.append(el("span", "msg", e.message)); }
    }));
  });
  return btn;
}

// During an exam: a report is held (the exam isn't interrupted) and decided on the results page.
function renderExamReport(q) {
  const box = $("s-exam-report");
  const inExam = S.mode === "exam" && !S.finished_at;
  box.hidden = !inExam;
  if (!inExam) { box.replaceChildren(); return; }
  if (S.held[q.id]) {
    const undo = el("button", "secondary small", "Take back");
    undo.type = "button";
    undo.addEventListener("click", async () => {
      try {
        await post(`/api/sessions/${S.id}/held-reports/decide`, { question_id: q.id, decision: "withdraw" });
        delete S.held[q.id];
        renderExamReport(q);
      } catch (e) { $("s-msg").textContent = e.message; }
    });
    box.replaceChildren(el("span", "muted", "Reported: you'll see the answer and decide after the exam. "), undo);
    return;
  }
  const btn = el("button", "secondary small danger", "Report a problem");
  btn.type = "button";
  btn.addEventListener("click", () => {
    box.replaceChildren(reportForm(null, "Report", async (reason, note) => {
      try {
        await post(`/api/sessions/${S.id}/held-reports`, { question_id: q.id, reason, note });
        S.held[q.id] = true;
        renderExamReport(q);
      } catch (e) { $("s-msg").textContent = e.message; }
    }));
  });
  box.replaceChildren(btn);
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

function scoreText(sc) {
  return sc.total ? `${sc.correct} / ${sc.total}${sc.percent === null ? "" : ` (${sc.percent}%)`}` : "none";
}

function renderReport(rep, timeUp) {
  const s = rep.session;
  const exam = s.mode === "exam";
  $("r-h").textContent = `${MODE_LABEL[s.mode] ?? s.mode} results`;
  $("r-score").textContent = `${scoreText(rep.scores.all)} correct`;
  if (rep.passed !== null) {
    $("r-score").append(" ", el("span", rep.passed ? "passed" : "failed",
      rep.passed ? `Pass (pass mark ${rep.pass_mark}%)` : `Below the pass mark (${rep.pass_mark}%)`));
  }
  const card = (title, sc, help) => { const c = el("div", "score-card"); c.append(el("span", "muted", title), el("strong", null, scoreText(sc)), el("small", "muted", help)); return c; };
  const grid = el("div", "scores");
  grid.append(card("All questions", rep.scores.all, exam ? "Every exam question; unanswered count as wrong." : "Every question you answered."),
    card("Validated questions only", rep.scores.validated, `Questions you'd answered before, or marked Looks right, before this ${exam ? "exam" : "session"}.`),
    card("New to you", rep.scores.new, "First time you saw them."),
    card("Repeats", rep.scores.repeat, "Seen in earlier sessions."));
  $("r-scores").replaceChildren(grid);
  $("r-note").textContent = [timeUp ? "Time ran out." : "", exam ? `${rep.answered} of ${rep.total} answered.` : "",
    rep.excluded.length ? `${rep.excluded.length} reported question(s) left out of the scores.` : "",
    rep.pass_note ?? "", rep.weights_note ?? ""].filter(Boolean).join(" ");
  renderReportDisputes(rep);
  table($("r-domains"), ["Domain", "Correct", "%"],
    Object.entries(rep.by_domain).map(([d, v]) => [d, `${v.correct}/${v.answered}`, v.percent ?? "-"]));
  table($("r-objectives"), ["Objective", "Correct"],
    Object.entries(rep.by_objective).map(([o, v]) => [`${o} ${names[o] ?? ""}`, `${v.correct}/${v.answered}`]));

  $("r-items").replaceChildren(...rep.items.map((it, i) => {
    const q = it.question;
    const box = el("details", it.excluded ? "item excluded" : "item");
    const verdict = it.excluded ? "Reported, left out of the score" : it.attempt ? (it.correct ? "Correct" : "Incorrect") : "Unanswered";
    const sum = el("summary", null, `${i + 1}. ${verdict} · ${q.id} · ${q.objectives[0]}`);
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
    if (it.attempt) {
      const c = it.attempt.confidence;
      box.append(el("p", "muted", `How sure you were: ${CONF_LABEL[c] ? `${c} ${CONF_LABEL[c]}` : c}`));
    }
    if (["unreviewed", "passive", "validated"].includes(q.status)) {
      box.append(questionTools(q, it.correct || !it.attempt, s.id, it.attempt?.selected ?? []));
    }
    // Misses start expanded where feedback was withheld until now.
    box.open = !it.correct && !it.excluded && (exam || s.mode === "diagnostic");
    return box;
  }));
  S = null;
  show("report");
}

// Reports made during this session, waiting for a decision (exam: held until now; practice: disputed).
function renderReportDisputes(rep) {
  const box = $("r-disputes");
  const s = rep.session;
  if (!rep.disputes.length) { box.replaceChildren(); return; }
  const rows = rep.disputes.map((d) => {
    const q = d.question;
    const item = el("div", "item");
    item.append(el("strong", null, `${q.id} · ${q.objectives[0]} · your reason: ${d.reason}`), el("p", "stem", q.stem));
    const ex = exhibitEl(q);
    if (ex) item.append(ex);
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
    item.append(opts, el("p", null, q.explanation));
    const actions = el("div", "row");
    if (d.decision) {
      actions.append(el("span", "muted", d.decision === "confirmed" ? "Confirmed: retired and left out of the score." : "Withdrawn: it counts as normal."));
    } else {
      const decide = async (decision) => {
        try {
          const next = d.held
            ? await post(`/api/sessions/${s.id}/held-reports/decide`, { question_id: q.id, decision })
            : (await post(certPath(`/questions/${encodeURIComponent(q.id)}/dispute`), { decision }),
               await api(`/api/sessions/${s.id}/report`));
          renderReport(next, false);
        } catch (e) { actions.append(el("span", "msg", e.message)); }
      };
      const yes = el("button", "small danger", "Confirm: retire it");
      yes.type = "button";
      yes.addEventListener("click", () => decide("confirm"));
      const no = el("button", "secondary small", d.held ? "Withdraw: it was fine" : "Undo: put it back");
      no.type = "button";
      no.addEventListener("click", () => decide(d.held ? "withdraw" : "undo"));
      actions.append(yes, no);
    }
    item.append(actions);
    return item;
  });
  box.replaceChildren(el("h3", null, "Questions you reported"),
    el("p", "muted", "Now that you can see the answers, decide each report. A confirmed report retires the question and leaves it out of your score."),
    ...rows);
}

// ---- disputed questions (reports not yet decided) ---------------------------

async function openDisputes() {
  const items = await api(certPath("/disputes"));
  if (!items.length) { $("d-list").replaceChildren(el("p", "muted", "Nothing waiting. Reported questions appear here until you decide.")); }
  else {
    $("d-list").replaceChildren(...items.map((q) => {
      const box = el("div", "item");
      box.append(el("strong", null, `${q.id} · ${q.objectives.map((o, k) => `${o} ${q.objective_names[k]}`).join(" · ")}`),
        el("p", "muted", `Your reason: ${q.disputed_reason}`), el("p", "stem", q.stem));
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
      box.append(opts, el("p", null, q.explanation));
      const actions = el("div", "row");
      const decide = async (decision) => {
        try { await post(certPath(`/questions/${encodeURIComponent(q.id)}/dispute`), { decision }); await openDisputes(); }
        catch (e) { actions.append(el("span", "msg", e.message)); }
      };
      const yes = el("button", "small danger", "Confirm: retire it");
      yes.type = "button";
      yes.addEventListener("click", () => decide("confirm"));
      const no = el("button", "secondary small", "Undo: put it back");
      no.type = "button";
      no.addEventListener("click", () => decide("undo"));
      const ask = el("button", "secondary small", "Ask Claude about this");
      ask.type = "button";
      const askOut = el("div");
      ask.addEventListener("click", async () => {
        const { prompt } = await api(certPath(`/prompts/ask/${encodeURIComponent(q.id)}`));
        askOut.replaceChildren(promptWidget("Prompt about this question", prompt));
      });
      actions.append(yes, no, ask);
      box.append(actions, askOut);
      return box;
    }));
  }
  show("disputes");
}

// ---- Focus: match a pasted objective list (v2 plan 7.2) ---------------------

const FOCUS_MAX_CHARS = 8000;
const CONFIDENCE_LABEL = { exact: "Exact ID", high: "Strong match", medium: "Likely match", low: "Weak match", chosen: "Added by you" };
// lines: the server's per-line results; each match carries `keep` (ticked). all: every objective, for adding by hand.
let F = { lines: [], all: [] };

async function openFocus() {
  F.all = await api(certPath("/objectives"));
  $("f-all").replaceChildren(...F.all.map((o) => { const opt = el("option"); opt.value = `${o.id} ${o.name}`; return opt; }));
  const sample = F.all[0];
  $("f-text").placeholder = `One objective per line, for example:\n${sample ? `${sample.name}\n${sample.id}\n` : ""}` +
    "1.2 Explain common threats: malware, phishing, denial of service";
  $("f-msg").textContent = "";
  updateFocusCount();
  show("focus");
  $("f-text").focus();
}

function updateFocusCount() {
  const n = $("f-text").value.length;
  $("f-count").textContent = `${n.toLocaleString()} of ${FOCUS_MAX_CHARS.toLocaleString()} characters`;
}

async function runFocusMatch() {
  const text = $("f-text").value;
  $("f-msg").textContent = "";
  if (!text.trim()) { $("f-msg").textContent = "Paste at least one objective, one per line."; return; }
  $("f-match").disabled = true;
  try {
    const r = await post(certPath("/focus/match"), { text });
    F.lines = r.lines.map((l) => ({ ...l, matches: l.matches.map((m) => ({ ...m, keep: m.confidence !== "low" })) }));
    renderFocus();
  } catch (e) {
    $("f-msg").textContent = e.message;
  } finally {
    $("f-match").disabled = false;
  }
}

function focusMatchRow(line, m) {
  const row = el("label", "focus-match");
  const box = el("input");
  box.type = "checkbox";
  box.checked = m.keep;
  box.addEventListener("change", () => { m.keep = box.checked; renderFocusSummary(); });
  const how = m.via && m.how === "words" ? ` · matched "${m.via}"` : "";
  row.append(box, el("strong", null, m.objective), el("span", null, m.name),
    el("span", `conf-badge ${m.confidence}`, CONFIDENCE_LABEL[m.confidence] ?? m.confidence),
    el("small", null, `${plural(m.questions, "question")}${how}`));
  const wrap = el("div");
  wrap.append(row);
  if (m.questions === 0) {
    const note = el("div", "focus-note");
    const ask = el("button", "secondary small", "Yes, give me a prompt");
    ask.type = "button";
    const out = el("div");
    ask.addEventListener("click", () => focusPrompt(m.objective, out, ask));
    note.append(el("span", "msg", `${m.note ?? "No questions exist for this objective yet."} Would you like a prompt to generate some? `), ask, out);
    wrap.append(note);
  }
  return wrap;
}

async function focusPrompt(objective, out, button) {
  button.disabled = true;
  try {
    const r = await api(certPath(`/prompts/questions?objective=${encodeURIComponent(objective)}&per_objective=2`));
    out.replaceChildren(promptWidget(`Question prompt for ${objective}`, r.prompt,
      "Paste it into a new chat at claude.ai, then import Claude's reply in the Claude workspace (home page)."));
  } catch (e) { out.replaceChildren(el("p", "msg", e.message)); }
  finally { button.disabled = false; }
}

function focusAdd(line, id, how = "chosen") {
  const o = F.all.find((x) => x.id === id);
  if (!o) return false;
  const have = line.matches.find((m) => m.objective === id);
  if (have) have.keep = true;
  else line.matches.push({ objective: o.id, name: o.name, section: o.section, questions: o.questions, how, confidence: "chosen", via: null, keep: true,
    ...(o.questions === 0 ? { note: "No questions exist for this objective yet." } : {}) });
  line.status = "matched";
  return true;
}

function renderFocus() {
  $("f-results").replaceChildren(...F.lines.map((line) => {
    const box = el("div", "item focus-line");
    const head = el("p", "line-text");
    head.append(el("strong", null, `Line ${line.line}: `), el("span", null, line.text));
    box.append(head);
    if (line.message && line.status !== "matched") box.append(el("p", line.status === "heading" ? "muted" : "msg", line.message));
    for (const m of line.matches) box.append(focusMatchRow(line, m));
    if (line.status === "too-long" || line.status === "heading") return box;

    const add = el("div", "focus-add");
    const sure = line.matches.some((m) => ["exact", "high", "chosen"].includes(m.confidence));
    const alternatives = sure ? [] : line.candidates.filter((c) => !line.matches.some((m) => m.objective === c.objective));
    for (const c of alternatives.slice(0, 3)) {
      const b = el("button", "secondary small", `+ ${c.objective} ${c.name}`);
      b.type = "button";
      b.title = plural(c.questions, "question");
      b.addEventListener("click", () => { focusAdd(line, c.objective); renderFocus(); });
      add.append(b);
    }
    const pick = el("input");
    pick.setAttribute("list", "f-all");
    pick.placeholder = line.matches.length ? "Add another objective (type to search)" : "Pick an objective yourself (type to search)";
    pick.setAttribute("aria-label", `Add an objective to line ${line.line}`);
    pick.addEventListener("change", () => {
      const id = /^([A-Z]{1,3}\d{2}-\d{2})\b/.exec(pick.value.trim())?.[1];
      if (id && focusAdd(line, id)) renderFocus();
      else pick.value = "";
    });
    add.append(pick);
    box.append(add);
    return box;
  }));
  renderFocusSummary();
}

function focusChosen() {
  const out = new Map();
  for (const line of F.lines) for (const m of line.matches) if (m.keep && !out.has(m.objective)) out.set(m.objective, m);
  return [...out.values()];
}

function renderFocusSummary() {
  const chosen = focusChosen();
  const questions = chosen.reduce((n, m) => n + m.questions, 0);
  const unknown = F.lines.filter((l) => l.status === "not-known").length;
  $("f-start-box").hidden = F.lines.length === 0;
  $("f-summary").textContent = `${plural(chosen.length, "objective")} chosen · ${plural(questions, "question")} available` +
    (unknown ? ` · ${plural(unknown, "line")} not in the objective list` : "") + ".";
  $("f-start").disabled = questions === 0;
  $("f-qcount").max = String(Math.max(1, Math.min(200, questions)));
  if (Number($("f-qcount").value) > questions && questions > 0) $("f-qcount").value = String(Math.min(questions, 200));
}

// ---- work with Claude: choose objectives, build prompts, import ------------

const MAX_PROMPT_OBJECTIVES = 30;
const MAX_IMPORT_CHARS = 900000;
let CL = { objectives: [], picked: new Set() };

async function openClaude() {
  CL.objectives = await api(certPath("/objectives"));
  const known = new Set(CL.objectives.map((o) => o.id));
  CL.picked = new Set([...CL.picked].filter((id) => known.has(id)));
  const sel = $("obj-section");
  const prev = sel.value;
  sel.replaceChildren(...sections.map((s) => { const o = el("option", null, s.name); o.value = s.code; return o; }));
  if (sections.some((s) => s.code === prev)) sel.value = prev;
  $("gap-count").textContent = String(CL.objectives.filter((o) => o.questions < 2).length);
  $("weak-count").textContent = String(CL.objectives.filter((o) => o.status === "Weak").length);
  $("claude-msg").textContent = "";
  renderObjectiveList();
  show("claude");
}

function renderObjectiveList() {
  const code = $("obj-section").value;
  $("obj-list").replaceChildren(...CL.objectives.filter((o) => o.section === code).map((o) => {
    const label = el("label");
    const box = el("input");
    box.type = "checkbox";
    box.value = o.id;
    box.checked = CL.picked.has(o.id);
    box.addEventListener("change", () => {
      if (box.checked) CL.picked.add(o.id); else CL.picked.delete(o.id);
      renderPicked();
    });
    const text = el("span");
    const count = `${o.questions} question${o.questions === 1 ? "" : "s"}`;
    text.append(el("span", null, `${o.id} ${o.name}`), el("small", null, `${count} · ${o.status}`));
    label.append(box, text);
    return label;
  }));
  renderPicked();
}

function renderPicked() {
  const n = CL.picked.size;
  $("obj-picked").textContent = n ? `${n} objective${n === 1 ? "" : "s"} chosen: ${[...CL.picked].sort().join(", ")}` +
    (n > MAX_PROMPT_OBJECTIVES ? ` (a prompt takes at most ${MAX_PROMPT_OBJECTIVES})` : "") : "No objectives chosen yet.";
}

function pickWhere(test, label) {
  const ids = CL.objectives.filter(test).map((o) => o.id);
  if (!ids.length) { $("claude-msg").textContent = `No ${label} right now.`; return; }
  for (const id of ids.slice(0, MAX_PROMPT_OBJECTIVES)) CL.picked.add(id);
  $("claude-msg").textContent = ids.length > MAX_PROMPT_OBJECTIVES
    ? `${ids.length} ${label}; added the first ${MAX_PROMPT_OBJECTIVES}. Build a prompt, then come back for the rest.` : "";
  renderObjectiveList();
}

async function buildPrompt(kind, { harder = false } = {}) {
  $("claude-msg").textContent = "";
  const ids = [...CL.picked].sort();
  if (!ids.length) { $("claude-msg").textContent = "Choose at least one objective first."; return; }
  if (ids.length > MAX_PROMPT_OBJECTIVES) { $("claude-msg").textContent = `Choose at most ${MAX_PROMPT_OBJECTIVES} objectives.`; return; }
  const q = ids.map((id) => `objective=${encodeURIComponent(id)}`).join("&");
  try {
    if (kind === "questions") {
      const r = await api(certPath(`/prompts/questions?${q}&per_objective=${$("per-objective").value}${harder ? "&harder=true" : ""}`));
      $("prompt-box").replaceChildren(promptWidget(`${harder ? "Harder-question" : "Question"} prompt (${plural(r.targets.length, "question")})`, r.prompt,
        "Paste it into a new chat at claude.ai, then import Claude's reply in step 3."));
    } else {
      const r = await api(certPath(`/prompts/study?${q}`));
      $("prompt-box").replaceChildren(promptWidget("Study-session prompt", r.prompt,
        "Paste it into a new chat at claude.ai and answer Claude's questions."));
    }
    $("prompt-box").hidden = false;
  } catch (e) { $("claude-msg").textContent = e.message; }
}

// What an import did: questions added, questions rejected with their problems and a repair prompt.
function importResultParts(r) {
  const parts = [];
  if (r.accepted.length) {
    parts.push(el("p", "ok-list", `Added ${r.accepted.length === 1 ? "1 question" : `${r.accepted.length} questions`} as Unreviewed: ` +
      r.accepted.map((a) => `${a.id} (${a.objective})`).join(", ")));
  }
  if (r.rejected.length) {
    parts.push(el("p", "msg", `${r.rejected.length} question${r.rejected.length === 1 ? " was" : "s were"} not added:`));
    for (const x of r.rejected) {
      const item = el("div", "item");
      item.append(el("strong", null, `Question ${x.index + 1}${x.objective ? ` (${x.objective})` : ""}`));
      if (x.stem) item.append(el("p", "muted", x.stem));
      const ul = el("ul", "problems");
      for (const p of x.problems) ul.append(el("li", null, p));
      item.append(ul);
      parts.push(item);
    }
    parts.push(promptWidget("Repair prompt", r.repair_prompt,
      "Paste it into the same Claude chat, then import the corrected questions here."));
  }
  for (const w of r.warnings) parts.push(el("p", "muted", w));
  parts.push(el("p", "muted", `Saved a copy of this reply as ${r.archive}.`));
  return parts;
}

// Fill a textarea from a chosen .json/.txt file (read in the browser; nothing is uploaded).
function readFileInto(input, area, msg) {
  const file = input.files[0];
  if (!file) return;
  if (file.size > MAX_IMPORT_CHARS) { msg.textContent = "That file is too large to import."; input.value = ""; return; }
  const reader = new FileReader();
  reader.onload = () => { area.value = String(reader.result); };
  reader.onerror = () => { msg.textContent = "Couldn't read that file."; };
  reader.readAsText(file);
}

function loadImportFile() {
  readFileInto($("import-file"), $("import-text"), $("claude-msg"));
}

async function runImport() {
  const text = $("import-text").value;
  const out = $("import-result");
  if (!text.trim()) { out.replaceChildren(el("p", "msg", "Paste Claude's reply (or choose its file) first.")); return; }
  if (text.length > MAX_IMPORT_CHARS) { out.replaceChildren(el("p", "msg", "That reply is too long to import at once.")); return; }
  $("import-btn").disabled = true;
  try {
    const r = await post(certPath("/imports"), { text });
    out.replaceChildren(...importResultParts(r));
    if (r.accepted.length) $("import-text").value = "";
    $("import-file").value = "";
    await openClaude();
  } catch (e) {
    out.replaceChildren(el("p", "msg", e.message));
  } finally {
    $("import-btn").disabled = false;
  }
}

// ---- progress over time (v2 plan 8.3) and suggestions (V11) -----------------

// [title, explanation, ask for harder questions]
const REASON = {
  weak: ["Still weak after several tries",
    "These stay Weak despite practice. New questions from fresh angles, aimed at the options you keep picking, usually help.", false],
  "too-easy": ["Too easy now",
    "Your latest answers were all right at 5 Certain. Harder questions (difficulty 3) will teach you more.", true],
  "no-unseen": ["You've seen every question",
    "You've answered every question on these at least once, so repeats start testing your memory of the question rather than the objective.", false],
};
const STATUS_TITLE = { Weak: "Weak", Improving: "Improving", Solid: "Solid", New: "Not practised yet" };
const ERROR_LABEL = Object.fromEntries(ERROR_TYPES);
const when = (iso) => new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
const day = (iso) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

async function openProgress(scrollTo) {
  const codes = sections.filter((s) => s.served > 0).map((s) => s.code);
  if (!codes.length) { $("home-msg").textContent = "No questions yet, so there's no progress to show."; return; }
  const [overview, rows, recs] = await Promise.all([
    api(certPath("/progress/overview")), api(certPath(`/tracker?${sectionQuery(codes)}`)), api(certPath("/recommendations"))]);
  show("progress");  // charts measure their width, so the page must be showing first
  renderTiles(overview.totals);
  renderSuggestions(recs);
  renderTimeline(overview.timeline);
  renderTotals(overview);
  renderCalibration(overview.calibration);
  renderTracker(rows);
  await Promise.all([renderObjectivePicker(rows, recs), renderTooEasy(codes)]);
  if (scrollTo) $(scrollTo).scrollIntoView({ block: "start" });
}

function renderTiles(t) {
  const tile = (label, value, note) => { const d = el("div", "tile"); d.append(el("span", null, label), el("strong", null, value), el("small", null, note)); return d; };
  $("p-tiles").replaceChildren(
    tile("Average objective score", t.score === null ? "none yet" : String(t.score),
      t.practised ? `over ${plural(t.practised, "practised objective")}` : "practise to get a score"),
    tile("Objectives practised", `${t.practised} of ${t.objectives}`, `${Math.round((100 * t.practised) / Math.max(1, t.objectives))}% of the list`),
    tile("Solid", String(t.Solid), `${t.Improving} improving · ${t.Weak} weak`),
    tile("Answers counted", String(t.answers), "answers to reported questions are left out"));
}

function renderSuggestions(recs) {
  const box = $("p-suggest");
  if (!recs.length) { box.replaceChildren(el("p", "muted", "Nothing to suggest right now. Suggestions appear as you practise.")); return; }
  const SHOWN = 8;
  const item = (x) => {
    const li = el("li");
    const bits = [x.status, `score ${x.score}`, plural(x.attempts, "answer"), plural(x.questions, "question")];
    if (x.dominant_error) bits.push(`main error: ${ERROR_LABEL[x.dominant_error] ?? x.dominant_error}`);
    const also = x.reasons.slice(1).map((r) => REASON[r][0].toLowerCase());
    if (also.length) bits.push(`also: ${also.join("; ")}`);
    const go = el("button", "secondary small", "Generate");
    go.type = "button";
    go.title = "Open the Claude workspace with a question prompt for this objective";
    go.addEventListener("click", () => openClaudeWith([x.objective], REASON[x.reasons[0]][2]));
    li.append(idLink(x.objective), el("span", null, x.name), el("small", null, bits.join(" · ")), go);
    return li;
  };
  box.replaceChildren(...Object.keys(REASON).map((reason) => {
    const items = recs.filter((x) => x.reasons[0] === reason);
    if (!items.length) return null;
    const [title, help, harder] = REASON[reason];
    const ids = items.map((x) => x.objective).slice(0, MAX_PROMPT_OBJECTIVES);
    const all = el("button", "small", items.length > MAX_PROMPT_OBJECTIVES ? `Build a prompt for the first ${MAX_PROMPT_OBJECTIVES}`
      : items.length === 1 ? "Build a prompt for it" : `Build a prompt for all ${items.length}`);
    all.type = "button";
    all.addEventListener("click", () => openClaudeWith(ids, harder));
    const head = el("div", "row");
    head.append(el("strong", null, `${title} (${items.length})`), all);
    const list = el("ul", "suggest-list");
    list.append(...items.slice(0, SHOWN).map(item));
    const group = el("div", "suggest-group");
    group.append(head, el("p", "muted", help), list);
    if (items.length > SHOWN) {
      const more = el("details");
      const rest = el("ul", "suggest-list");
      rest.append(...items.slice(SHOWN).map(item));
      more.append(el("summary", null, `Show ${items.length - SHOWN} more`), rest);
      group.append(more);
    }
    return group;
  }).filter(Boolean));
}

async function openClaudeWith(ids, harder) {
  await openClaude();
  CL.picked = new Set(ids);
  $("obj-section").value = ids[0].split("-")[0];
  renderObjectiveList();
  await buildPrompt("questions", { harder });
  $("prompt-box").scrollIntoView({ block: "start" });
}

function renderTimeline(tl) {
  if (!tl.length) {
    $("p-score-chart").replaceChildren(el("p", "muted", "No sessions yet."));
    $("p-status-charts").replaceChildren();
    return;
  }
  const mode = (p) => MODE_LABEL[p.mode] ?? p.mode;
  const point = (p, y, detail) => ({ y, tick: day(p.at), when: `${when(p.at)} · ${mode(p)}`, detail });
  const scoreBox = el("div");
  $("p-score-chart").replaceChildren(scoreBox, Charts.tableView(
    ["After the session of", "Mode", "Average score", "Weak", "Improving", "Solid", "Not practised"],
    tl.map((p) => [when(p.at), mode(p), p.score ?? "", p.Weak, p.Improving, p.Solid, p.New].map(String))));
  Charts.line(scoreBox, {
    points: tl.map((p) => point(p, p.score, [`${p.Solid} solid · ${p.Improving} improving · ${p.Weak} weak`])),
    yMax: 100, name: "Average objective score after each session", xTitle: "Sessions, oldest to newest" });

  // One small chart per status: identity comes from each chart's title, never from color.
  const cells = ["Weak", "Improving", "Solid", "New"].map((st) => {
    const first = tl[0][st];
    const last = tl[tl.length - 1][st];
    const change = last - first;
    const h = el("h4", null, `${STATUS_TITLE[st]}: ${last} `);
    h.append(el("small", null, `(${change >= 0 ? "+" : ""}${change} since the first session)`));
    const box = el("div");
    const cell = el("div");
    cell.append(h, box);
    return [st, cell, box];
  });
  $("p-status-charts").replaceChildren(...cells.map(([, cell]) => cell));
  for (const [st, , box] of cells) {
    Charts.line(box, { points: tl.map((p) => point(p, p[st], [`${STATUS_TITLE[st]}: ${p[st]} objectives`])),
      height: 130, name: `${STATUS_TITLE[st]} objectives after each session` });
  }
}

function renderTotals(o) {
  const bar = (s, name) => ({
    label: `${name} (${s.practised} of ${s.objectives} practised)`, value: s.score, empty: "not practised yet",
    valueText: s.score === null ? null : String(s.score), detail: [`${s.Solid} solid · ${s.Improving} improving · ${s.Weak} weak`] });
  const parts = [
    ["p-sections", o.by_section.map((s) => bar(s, s.name)), o.by_section, "Section", "Score by section"],
    ["p-domains", o.by_domain.map((d) => bar(d, d.id === "untagged" ? d.name : `${d.id} ${d.name}`)), o.by_domain, "Domain", "Score by domain"],
  ];
  for (const [id, rows, raw, kind, name] of parts) {
    const box = el("div");
    $(id).replaceChildren(box, Charts.tableView([kind, "Score", "Practised", "Objectives", "Weak", "Improving", "Solid"],
      raw.map((s, i) => [rows[i].label.replace(/ \(.*\)$/, ""), s.score ?? "", s.practised, s.objectives, s.Weak, s.Improving, s.Solid].map(String))));
    Charts.bars(box, { rows, max: 100, name });
  }
}

function renderCalibration(cal) {
  const box = el("div");
  $("p-calibration").replaceChildren(box, Charts.tableView(["How sure", "Answers", "Right", "% right"],
    cal.map((c) => [`${c.confidence} ${c.label}`, String(c.answered), String(c.correct), c.percent === null ? "" : `${c.percent}%`])));
  Charts.columns(box, {
    cols: cal.map((c) => ({ label: `${c.confidence} ${c.label}`, short: String(c.confidence), sub: plural(c.answered, "answer"), subShort: `n=${c.answered}`,
      value: c.percent, valueText: c.percent === null ? null : `${Math.round(c.percent)}%`, detail: [`${c.correct} of ${c.answered} right`] })),
    max: 100, format: (v) => `${v}%`, name: "Percent right at each confidence level" });
}

function idLink(id) {
  const b = el("button", "id-link", id);
  b.type = "button";
  b.title = "Show this objective's score over time";
  b.addEventListener("click", () => showObjective(id, true).catch((e) => { $("p-obj-chart").replaceChildren(el("p", "msg", e.message)); }));
  return b;
}

async function renderObjectivePicker(rows, recs) {
  const practised = rows.filter((r) => r.attempts > 0);
  if (!practised.length) { $("p-obj").replaceChildren(); $("p-obj-chart").replaceChildren(el("p", "muted", "Nothing practised yet.")); return; }
  $("p-obj").replaceChildren(...sections.map((s) => {
    const mine = practised.filter((r) => r.section === s.code);
    if (!mine.length) return null;
    const g = el("optgroup");
    g.label = s.name;
    g.append(...mine.map((r) => { const o = el("option", null, `${r.objective} ${r.name} (${r.status}, score ${r.score})`); o.value = r.objective; return o; }));
    return g;
  }).filter(Boolean));
  const lowest = [...practised].sort((a, b) => a.score - b.score)[0];
  await showObjective(recs[0]?.objective ?? lowest.objective);
}

async function showObjective(id, scroll = false) {
  if ([...$("p-obj").options].some((o) => o.value === id)) $("p-obj").value = id;
  const h = await api(certPath(`/progress/objectives/${encodeURIComponent(id)}`));
  if (scroll) $("p-obj-h").scrollIntoView({ block: "start" });
  if (!h.points.length) { $("p-obj-chart").replaceChildren(el("p", "muted", `${h.objective} hasn't been practised yet.`)); return; }
  const box = el("div");
  $("p-obj-chart").replaceChildren(box, Charts.tableView(
    ["Answer", "When", "Question", "Result", "How sure", "Answer score", "Objective score", "Status"],
    h.points.map((p, i) => [i + 1, when(p.at), p.question_id, p.correct ? "Right" : "Wrong", `${p.confidence} ${CONF_LABEL[p.confidence]}`,
      p.answer_score, p.score, p.status].map(String))));
  Charts.line(box, {
    points: h.points.map((p, i) => ({ y: p.score, tick: day(p.at), hollow: !p.correct, when: `Answer ${i + 1} · ${when(p.at)}`,
      detail: [`${p.correct ? "Right" : "Wrong"} at ${p.confidence} ${CONF_LABEL[p.confidence]} · ${p.question_id}`, `Status after it: ${p.status}`] })),
    yMax: 100, height: 180, name: `${h.objective} ${h.name}: score after each answer`, xTitle: "Answers, oldest to newest" });
}

function renderTracker(rows) {
  const counts = rows.reduce((m, r) => ((m[r.status] = (m[r.status] || 0) + 1), m), {});
  $("p-summary").textContent = ["Weak", "Improving", "Solid", "New"].map((s) => `${s}: ${counts[s] || 0}`).join(" · ") +
    ". Solid needs 3 correct across 2+ sessions and 2+ angles with the last five at 80% or better." +
    " Correct answers rated 1 Guessing don't count toward mastery (shown as ?). Choose an ID to see its score over time.";
  table($("p-table"), ["ID", "Objective", "Status", "Score", "Tries", "Last five", "Wrong while sure", "Main error", "Revisit"],
    rows.map((r) => [r.attempts ? idLink(r.objective) : r.objective, r.name, el("span", `status-${r.status}`, r.status),
      r.score === null ? "" : String(r.score), String(r.attempts),
      r.last5_marks.map((m) => LAST5_MARK[m]).join(" "), r.sure_wrong_recent ? String(r.sure_wrong_recent) : "",
      r.dominant_error ?? "", r.revisit_due ? "due" : ""]));
}

// ---- certification wizard (v2 plan 3.3) and first start (plan 4) ------------

const W_STEPS = [["name", "Name"], ["facts", "Exam facts"], ["objectives", "Objectives"], ["questions", "First questions"]];
const W_ORDER = W_STEPS.map(([k]) => k);
const FACT_ROWS = [["minutes", "Time limit (minutes)"], ["question_count", "Number of questions"], ["passing_score", "Passing score"]];
// The draft being set up. W.step is how far it has got (server); W.view is the step on screen.
let W = null;
let drafts = [];
const wizPath = (rest = "") => `/api/wizard/${encodeURIComponent(W.id)}${rest}`;
const rowOf = (...kids) => { const r = el("div", "row"); r.append(...kids); return r; };

async function openWizard(draftId = null) {
  W = draftId ? await api(`/api/wizard/${encodeURIComponent(draftId)}`) : null;
  if (W) W.view = W.step;
  $("w-msg").textContent = "";
  show("wizard");
  await renderWizard();
}

async function renderWizard() {
  const view = W ? W.view : "name";
  const reached = W ? W_ORDER.indexOf(W.step) : 0;
  $("w-steps").replaceChildren(...W_STEPS.map(([key, label], i) => {
    const li = el("li", key === view ? "current" : i < reached ? "done" : "");
    // Earlier steps can be revisited until the certification is installed (then its objectives are fixed).
    const open = W && !W.installed && i >= 1 && i <= reached && key !== view;
    const item = el(open ? "button" : "span", null, label);
    if (open) {
      item.type = "button";
      item.addEventListener("click", () => { W.view = key; $("w-msg").textContent = ""; renderWizard(); });
    }
    if (key === view) item.setAttribute("aria-current", "step");
    li.append(item);
    return li;
  }));
  $("w-discard").hidden = !W || W.installed;
  $("w-h").textContent = W ? `Set up ${W.short_name}` : "Set up a certification";
  const body = $("w-body");
  body.replaceChildren();
  await { name: wizardName, facts: wizardFacts, objectives: wizardObjectives, questions: wizardQuestions }[view](body);
}

function wizStep(title, ...children) {
  const s = el("div", "wiz-step");
  s.append(el("h3", null, title), ...children);
  return s;
}

// A button that builds a prompt and shows it, ready to copy.
function promptStep(label, getPrompt, hint) {
  const out = el("div");
  const b = el("button", null, label);
  b.type = "button";
  b.addEventListener("click", async () => {
    b.disabled = true;
    $("w-msg").textContent = "";
    try { out.replaceChildren(promptWidget(label.replace(/^Build the /, "The "), await getPrompt(), hint)); }
    catch (e) { $("w-msg").textContent = e.message; }
    finally { b.disabled = false; }
  });
  const box = el("div");
  box.append(rowOf(b), out);
  return box;
}

// Paste Claude's reply (or choose its file) and send it with onSubmit(text, outputArea, textarea).
function replyBox(label, button, onSubmit) {
  const area = el("textarea");
  area.rows = 6;
  area.placeholder = "Paste Claude's whole reply here";
  area.setAttribute("aria-label", label);
  const file = el("input");
  file.type = "file";
  file.accept = ".json,.txt,application/json,text/plain";
  file.setAttribute("aria-label", `${label}: choose a file instead`);
  file.addEventListener("change", () => readFileInto(file, area, $("w-msg")));
  const go = el("button", null, button);
  go.type = "button";
  const out = el("div");
  out.setAttribute("aria-live", "polite");
  go.addEventListener("click", async () => {
    $("w-msg").textContent = "";
    if (!area.value.trim()) { $("w-msg").textContent = "Paste Claude's reply first."; return; }
    if (area.value.length > MAX_IMPORT_CHARS) { $("w-msg").textContent = "That reply is too long to import at once."; return; }
    go.disabled = true;
    try { await onSubmit(area.value, out, area); }
    catch (e) { out.replaceChildren(el("p", "msg", e.message)); }
    finally { go.disabled = false; }
  });
  const box = el("div");
  box.append(area, rowOf(el("span", "muted", "or choose the file Claude gave you:"), file), rowOf(go), out);
  return box;
}

function problemParts(r) {
  const ul = el("ul", "problems");
  for (const p of r.problems) ul.append(el("li", null, p));
  return [el("p", "msg", "Claude's reply has problems, so nothing was saved:"), ul,
    promptWidget("Repair prompt", r.repair_prompt, "Paste it into the same Claude chat, then paste Claude's corrected reply here.")];
}

function wizardName(body) {
  const grid = el("div", "form-grid");
  const inputs = {};
  for (const [key, label, max, hint] of [["name", "Certification name", 200, "e.g. CompTIA Security+"],
    ["short_name", "Short name (optional)", 60, "shown in the top bar"], ["vendor", "Vendor (optional)", 100, "e.g. CompTIA"],
    ["exam_code", "Exam code (optional)", 40, "e.g. SY0-701"]]) {
    const input = el("input");
    input.type = "text";
    input.id = `w-${key}`;
    input.maxLength = max;
    input.placeholder = hint;
    const lab = el("label", null, label);
    lab.htmlFor = input.id;
    inputs[key] = input;
    grid.append(lab, input);
  }
  const go = el("button", null, "Save and continue");
  go.type = "button";
  go.addEventListener("click", async () => {
    $("w-msg").textContent = "";
    if (!inputs.name.value.trim()) { $("w-msg").textContent = "Give the certification a name."; inputs.name.focus(); return; }
    go.disabled = true;
    try {
      W = await post("/api/wizard", Object.fromEntries(Object.entries(inputs).map(([k, i]) => [k, i.value])));
      W.view = "facts";
      await renderWizard();
    } catch (e) { $("w-msg").textContent = e.message; go.disabled = false; }
  });
  const pack = el("button", "id-link", "Import a certification pack instead");
  pack.type = "button";
  pack.addEventListener("click", openPackImport);
  const instead = el("p", "muted", "Already have this certification as a pack (exported from this app)? ");
  instead.append(pack);
  body.append(wizStep("1. Name the certification",
    el("p", "muted", "Use the name the vendor uses. Claude checks it and fills in the official details in the next step."),
    grid, rowOf(go)), instead);
  inputs.name.focus();
}

function wizardFacts(body) {
  const ask = wizStep("2a. Ask Claude for the exam facts",
    el("p", "muted", "Claude gathers the official facts: time limit, number of questions, passing score, question formats, " +
      "and the exam's domains with their weights. It says how sure it is of each one, so nothing is guessed silently. " +
      "A chat where Claude can search the web works best."),
    promptStep("Build the exam-facts prompt", async () => (await api(wizPath("/prompts/facts"))).prompt,
      "Paste it into a new chat at claude.ai, then paste Claude's reply below."));
  const reply = wizStep("2b. Paste Claude's reply", replyBox("Claude's exam-facts reply", "Check Claude's reply", async (text, out) => {
    const r = await post(wizPath("/facts"), { text });
    if (!r.ok) { out.replaceChildren(...problemParts(r)); return; }
    W = { ...r.draft, view: "facts" };
    await renderWizard();
  }));
  if (!W.facts) { body.append(ask, reply); return; }
  const redo = el("details");
  redo.append(el("summary", null, "Ask Claude again"), ask, reply);
  body.append(factsPreview(), redo);
}

function factsPreview() {
  const f = W.facts;
  const inputs = {};
  const factRows = FACT_ROWS.map(([key, label]) => {
    const fact = f.exam[key];
    const value = el("input");
    value.type = "text";
    value.value = fact.value ?? "";
    value.setAttribute("aria-label", `${label}: value`);
    const sure = el("select");
    for (const c of ["official", "estimate", "unknown"]) { const o = el("option", null, c); o.value = c; sure.append(o); }
    sure.value = fact.confidence;
    sure.setAttribute("aria-label", `${label}: how sure`);
    inputs[key] = [value, sure];
    return [label, value, sure, fact.note || ""];
  });
  const facts = el("table", "wiz-table");
  table(facts, ["Fact", "Value", "How sure", "Where it comes from"], factRows);
  const weights = {};
  const domains = el("table", "wiz-table");
  table(domains, ["Domain", "Name", "Weight"], f.domains.map((d) => {
    const w = el("input");
    w.type = "number";
    w.min = "0.1";
    w.step = "any";
    w.value = String(d.weight);
    w.setAttribute("aria-label", `Weight of ${d.id}`);
    weights[d.id] = w;
    return [d.id, d.name, w];
  }));
  const sources = el("ul");
  for (const s of f.sources) {
    const a = el("a", null, s.title);
    a.href = s.url;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    const li = el("li");
    li.append(a, el("small", "muted", ` ${s.url}`));
    sources.append(li);
  }
  const formats = f.exam.question_formats.map((x) => `${x.format}${x.served ? "" : " (this app can't serve it)"}`).join(", ");
  const go = el("button", null, "Save and continue");
  go.type = "button";
  go.addEventListener("click", async () => {
    $("w-msg").textContent = "";
    const edits = {};
    for (const [key, label] of FACT_ROWS) {
      const [value, sure] = inputs[key];
      const raw = value.value.trim();
      const n = Number(raw);
      if (key !== "passing_score" && raw && !Number.isInteger(n)) { $("w-msg").textContent = `${label} must be a whole number (or empty).`; value.focus(); return; }
      edits[key] = { value: raw === "" ? null : Number.isFinite(n) ? n : raw, confidence: sure.value };
    }
    edits.weights = Object.fromEntries(Object.entries(weights).map(([id, w]) => [id, Number(w.value)]));
    go.disabled = true;
    try {
      W = { ...(await post(wizPath("/facts/edit"), edits)), view: "objectives" };
      await renderWizard();
    } catch (e) { $("w-msg").textContent = e.message; go.disabled = false; }
  });
  const wrap = (t) => { const d = el("div", "table-wrap"); d.append(t); return d; };
  return wizStep(`Exam facts for ${W.name}`,
    el("p", "muted", "Check these against the vendor's pages, and correct anything that's off. \"How sure\" matters: " +
      "the exam simulation only shows pass or fail when the passing score is a known percentage."),
    wrap(facts), el("p", null, `Question formats: ${formats || "not given"}.`),
    el("h3", null, `Domains (weights: ${f.weights.confidence}${f.weights.note ? `, ${f.weights.note}` : ""})`), wrap(domains),
    el("h3", null, "Sources"), f.sources.length ? sources : el("p", "muted", "None given."), rowOf(go));
}

function wizardObjectives(body) {
  const list = el("textarea");
  list.rows = 8;
  list.maxLength = 30000;
  list.value = W.official_list || "";
  list.placeholder = "Paste the vendor's official exam objectives here (exam topics, blueprint or syllabus), all of it";
  list.setAttribute("aria-label", "The official objective list");
  const build = wizStep("3a. Paste the official objective list",
    el("p", "muted", "Copy the vendor's published exam objectives (often called exam topics, blueprint or syllabus) and " +
      "paste them here. The app puts them in a prompt; Claude turns them into objectives, one testable idea each, " +
      "each with the fact that tells it apart from look-alikes."),
    list, promptStep("Build the objective-builder prompt", async () => (await post(wizPath("/prompts/objectives"), { text: list.value })).prompt,
      "Paste it into a chat at claude.ai (the one you used for the exam facts is fine), then paste Claude's reply below."));
  const reply = wizStep("3b. Paste Claude's reply", replyBox("Claude's objectives reply", "Check Claude's reply", async (text, out) => {
    const r = await post(wizPath("/objectives"), { text });
    if (!r.ok) { out.replaceChildren(...problemParts(r)); return; }
    W = { ...r.draft, view: "objectives" };
    await renderWizard();
  }));
  if (!W.sections) { body.append(build, reply); return; }
  const redo = el("details");
  redo.append(el("summary", null, "Ask Claude again"), build, reply);
  body.append(objectivesPreview(), redo);
}

function objectivesPreview() {
  const total = W.sections.reduce((n, s) => n + s.objectives.length, 0);
  const domainName = Object.fromEntries((W.facts?.domains ?? []).map((d) => [d.id, d.name]));
  const box = wizStep(`Objectives: ${plural(total, "objective")} in ${plural(W.sections.length, "section")}`,
    el("p", "muted", "Open each section to check it. If something's off, ask Claude to fix it in the same chat and paste " +
      "the new reply below. Objective IDs can't change once the certification is created."));
  for (const s of W.sections) {
    const d = el("details");
    d.append(el("summary", null, `${s.code} ${s.name} · ${plural(s.objectives.length, "objective")}` +
      (s.domain ? ` · domain ${s.domain} ${domainName[s.domain] ?? ""}` : "")));
    const t = el("table");
    table(t, ["ID", "Objective", "Tells it apart", "Ref"], s.objectives.map((o) => [o.id, o.objective, o.discriminator, o.ref]));
    const wrap = el("div", "table-wrap");
    wrap.append(t);
    d.append(wrap);
    box.append(d);
  }
  const go = el("button", null, "Create the certification");
  go.type = "button";
  go.addEventListener("click", async () => {
    $("w-msg").textContent = "";
    go.disabled = true;
    try {
      await post(wizPath("/install"));
      W = { ...(await api(wizPath())), view: "questions" };
      certs = [];
      await renderWizard();
    } catch (e) { $("w-msg").textContent = e.message; go.disabled = false; }
  });
  box.append(rowOf(go));
  return box;
}

async function wizardQuestions(body) {
  const certUrl = `/api/certs/${encodeURIComponent(W.id)}`;
  const rows = await api(`${certUrl}/objectives`);
  const covered = rows.filter((o) => o.questions >= 2).length;
  const bar = el("progress");
  bar.max = Math.max(1, rows.length);
  bar.value = covered;
  bar.setAttribute("aria-label", "Objectives with at least two questions");
  const zero = rows.filter((o) => o.questions === 0);
  const batch = zero.length ? { list: zero.slice(0, 15), per: 2 } : { list: rows.filter((o) => o.questions === 1).slice(0, 30), per: 1 };
  const parts = [bar, el("p", null, `${covered} of ${plural(rows.length, "objective")} have at least two questions.`)];
  if (batch.list.length) {
    const first = batch.list[0].id;
    const last = batch.list[batch.list.length - 1].id;
    const query = batch.list.map((o) => `objective=${encodeURIComponent(o.id)}`).join("&");
    parts.push(el("p", "muted", `Next batch: ${plural(batch.list.length, "objective")} (${first}${first === last ? "" : ` to ${last}`}), ` +
      `${plural(batch.list.length * batch.per, "question")}.`),
    promptStep("Build the next question prompt", async () => (await api(`${certUrl}/prompts/questions?${query}&per_objective=${batch.per}`)).prompt,
      "Paste it into a new chat at claude.ai, then paste Claude's reply below."));
  } else {
    parts.push(el("p", "ok-list", "Every objective has at least two questions."));
  }
  body.append(wizStep("4. Write the first questions",
    el("p", "muted", "The app asks Claude for questions in batches until every objective has at least two. You can stop " +
      "whenever you like and carry on later, here or in the Claude workspace."), ...parts));
  if (W.lastImport) body.append(wizStep("Last import", ...W.lastImport));
  body.append(wizStep("Paste Claude's questions", replyBox("Claude's questions reply", "Import", async (text) => {
    W.lastImport = importResultParts(await post(`${certUrl}/imports`, { text }));
    await renderWizard();
  })));
  const done = el("button", null, covered === rows.length ? "Finish and start studying" : "Finish for now and start studying");
  done.type = "button";
  done.addEventListener("click", finishWizard);
  body.append(rowOf(done));
}

async function finishWizard() {
  try {
    await post(wizPath("/finish"));
    const name = W.short_name;
    store.set("certprep.cert", W.id);
    store.set("certprep.welcomed", true);
    W = null;
    certs = [];
    await loadHome();
    const note = $("draft-note");
    note.replaceChildren(el("p", "ok-list", `${name} is ready. Choose its sections below and start practising.`));
    note.hidden = false;
  } catch (e) { $("w-msg").textContent = e.message; }
}

async function discardWizard() {
  if (!W || !confirm(`Discard the set-up of ${W.name}? Nothing has been installed yet, so this removes the work done in the wizard.`)) return;
  try {
    await post(wizPath("/discard"), { confirm: "DISCARD" });
    W = null;
    await loadHome();
  } catch (e) { $("w-msg").textContent = e.message; }
}

function renderDraftNote() {
  const note = $("draft-note");
  note.hidden = drafts.length === 0;
  note.replaceChildren(...drafts.map((d) => {
    const b = el("button", "id-link", `Continue setting up ${d.name}`);
    b.type = "button";
    b.addEventListener("click", () => openWizard(d.id).catch((e) => { $("home-msg").textContent = e.message; }));
    const step = d.installed ? "installed; first questions next" : `next: ${W_STEPS.find(([k]) => k === d.step)?.[1] ?? d.step}`;
    const p = el("p");
    p.append(b, el("span", "muted", ` · ${step}`));
    return p;
  }));
}

// First start (plan 4): ask which certification, unless the learner has already begun somewhere.
function maybeWelcome() {
  if (store.get("certprep.welcomed", false) || drafts.length || certs.some((c) => c.answers > 0)) return;
  $("welcome-choices").replaceChildren(...certs.map((c) => {
    const b = el("button", null, c.short_name);
    b.type = "button";
    b.append(el("small", null, `${c.name}: ready to use`));
    b.addEventListener("click", () => {
      store.set("certprep.cert", c.id);
      $("welcome").close();
      loadHome();
    });
    return b;
  }));
  $("welcome").showModal();
}

// ---- help (v2 plan 4), question-bank health (5.2), packs (9) ----------------

let helpReturn = "home";

function openHelp(topic) {
  const current = [...document.querySelectorAll(".view")].find((v) => !v.hidden)?.id.replace(/^v-/, "") ?? "home";
  if (current !== "help") helpReturn = current;
  show("help");
  if (topic) document.getElementById(`help-${topic}`)?.scrollIntoView({ block: "start" });
}

const BAND_LABEL = {
  answer_longest: ["The answer is the longest option", "single-answer questions"],
  answer_shortest: ["The answer is the shortest option", "single-answer questions"],
  multi_answers_are_longest: ["The answers are the longest options", "multi-select questions"],
  absolute_only_in_distractors: ["Only wrong options say always, never, only...", "single-answer questions"],
  answer_echoes_stem_most: ["The answer repeats the question's wording most", "single-answer questions"],
};
const pct = (x) => `${Math.round(x * 100)}%`;

async function openHealth() {
  const h = await api(certPath("/health"));
  const names = Object.fromEntries(sections.map((s) => [s.code, s.name]));
  const covered = h.sections.filter((s) => s.ok).length;
  $("h-summary").textContent = `${covered} of ${plural(h.sections.length, "section")} fully covered: every objective has at ` +
    `least ${h.minimum} questions, from two or more angles.`;
  table($("h-sections"), ["Section", "Objectives", "Questions", "Per objective", `Fewer than ${h.minimum}`, "One angle only", "Status"],
    h.sections.map((s) => [names[s.code] ?? s.code, String(s.objectives), String(s.active), s.active ? `${s.fewest} to ${s.most}` : "",
      String(s.below_minimum.length), String(s.single_angle.length),
      el("span", s.ok ? "verdict-ok" : "verdict-bad", s.ok ? "OK" : s.active ? "Needs questions" : "No questions yet")]));
  const short = h.sections.flatMap((s) => s.below_minimum);
  const oneAngle = h.sections.flatMap((s) => s.single_angle);
  const stray = h.sections.flatMap((s) => s.unknown_ids);
  const gaps = [];
  if (short.length) {
    const b = el("button", null, `Build a prompt for ${short.length > MAX_PROMPT_OBJECTIVES ? `the first ${MAX_PROMPT_OBJECTIVES} of ` : ""}` +
      `${plural(short.length, "objective")} with fewer than ${h.minimum} questions`);
    b.type = "button";
    b.addEventListener("click", () => openClaudeWith(short.slice(0, MAX_PROMPT_OBJECTIVES), false));
    gaps.push(rowOf(b));
  } else {
    gaps.push(el("p", "ok-list", `Every objective has at least ${h.minimum} questions.`));
  }
  if (oneAngle.length) gaps.push(el("p", "muted", `Asked from one angle only: ${oneAngle.slice(0, 20).join(", ")}${oneAngle.length > 20 ? "..." : ""}. ` +
    "A new question on these takes a different approach automatically."));
  if (stray.length) gaps.push(el("p", "msg", `Questions point at objectives that aren't in the objective files: ${stray.join(", ")}.`));
  $("h-gaps").replaceChildren(...gaps);
  table($("h-bands"), ["Check", "Measured", "Allowed", "Status"], h.bands.map((b) => {
    const [label, kind] = BAND_LABEL[b.key] ?? [b.key, "questions"];
    return [label, b.share === null ? `no ${kind} yet` : `${pct(b.share)} (${b.count} of ${b.of} ${kind})`, `${pct(b.low)} to ${pct(b.high)}`,
      b.share === null ? "" : el("span", b.ok ? "verdict-ok" : "verdict-bad", b.ok ? "OK" : "Outside the range")];
  }));
  const a = h.audit;
  const roles = Object.entries(a.roles).map(([r, n]) => `${ROLE_LABEL[r]?.toLowerCase() ?? r} ${n}`).join(", ");
  const levels = Object.entries(a.difficulty).map(([d, n]) => `level ${d}: ${n}`).join(", ");
  $("h-mix").textContent = a.questions ? `${plural(a.questions, "active question")}: ${a.single} single answer, ${a.multi} multi-select, ` +
    `${a.exhibits} with an exhibit. Option roles: ${roles}. Difficulty: ${levels}.` : "No active questions yet.";
  show("health");
}

function updatePackLink() {
  $("pack-link").href = certPath(`/pack${$("pack-retired").checked ? "?retired=true" : ""}`);
}

let PK = null;  // the pack file being imported

function openPackImport() {
  PK = null;
  $("pk-file").value = "";
  $("pk-msg").textContent = "";
  $("pk-result").hidden = true;
  show("pack");
}

// The pack goes up as the request body itself (application/zip), not as JSON.
async function sendPack(params) {
  const r = await fetch(`/api/packs/import?${new URLSearchParams(params)}`, {
    method: "POST", headers: { "Content-Type": "application/zip", "X-CSRF-Token": CSRF_TOKEN }, body: PK });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : `HTTP ${r.status}`);
  return body;
}

async function checkPack() {
  const file = $("pk-file").files[0];
  $("pk-msg").textContent = "";
  $("pk-result").hidden = true;
  if (!file) return;
  if (file.size > 20_000_000) { $("pk-msg").textContent = "That file is larger than 20 MB, the limit for a pack."; return; }
  PK = file;
  try {
    const r = await sendPack({ check: "true" });
    const p = r.pack;
    table($("pk-table"), ["In this pack", ""], [["Certification", p.name], ["Vendor and exam", [p.vendor, p.exam_code].filter(Boolean).join(" ") || "not given"],
      ["Sections", String(p.sections)], ["Objectives", String(p.objectives)],
      ["Questions", `${p.questions}${p.retired ? ` (plus ${p.retired} retired)` : ""}`], ["Exported", p.created ? when(p.created) : "unknown"]]);
    $("pk-id").value = r.suggested_id;
    $("pk-short").value = r.suggested_short_name;
    $("pk-result").hidden = false;
  } catch (e) { $("pk-msg").textContent = e.message; }
}

async function importPack() {
  const id = $("pk-id").value.trim();
  if (!/^[a-z0-9][a-z0-9-]{1,31}$/.test(id)) {
    $("pk-msg").textContent = "The id must be 2 to 32 lowercase letters, digits or dashes, starting with a letter or digit.";
    return;
  }
  const short = $("pk-short").value.trim();
  $("pk-import").disabled = true;
  try {
    const r = await sendPack({ check: "false", id, ...(short ? { short_name: short } : {}) });
    store.set("certprep.cert", r.cert);
    store.set("certprep.welcomed", true);
    certs = [];
    await loadHome();
    $("draft-note").replaceChildren(el("p", "ok-list", `${cert.short_name} is installed. Choose its sections below and start practising.`));
    $("draft-note").hidden = false;
  } catch (e) { $("pk-msg").textContent = e.message; }
  finally { $("pk-import").disabled = false; }
}

// ---- progress backups ------------------------------------------------------

const BACKUP_KIND = { manual: "Made by you", "before-restore": "Before a restore", upgrade: "Before an app upgrade", reset: "Before a reset" };

async function openBackups() {
  $("b-msg").textContent = "";
  await renderBackups();
  show("backups");
}

async function renderBackups() {
  const list = await api("/api/progress/backups");
  if (!list.length) { $("b-table").replaceChildren(); $("b-msg").textContent = "No backups yet."; return; }
  table($("b-table"), ["Made", "Kind", "Sessions", "Answers", "Latest answer", ""], list.map((b) => {
    const actions = el("span", "pool-actions");
    if (b.restorable) {
      const go = el("button", "secondary small", "Restore");
      go.type = "button";
      go.addEventListener("click", () => restoreBackup(b));
      actions.append(go);
    } else {
      actions.append(el("span", "muted", b.problem ?? "Made by a newer version of the app"));
    }
    const dl = el("a", null, "Download");
    dl.href = `/api/progress/backups/${encodeURIComponent(b.name)}`;
    dl.download = b.name;
    actions.append(dl);
    return [when(b.created_at), BACKUP_KIND[b.kind] ?? b.kind, String(b.sessions ?? ""), String(b.answers ?? ""),
      b.last_answer ? when(b.last_answer) : "", actions];
  }));
}

async function backupNow() {
  try {
    await post("/api/progress/backups");
    await renderBackups();
    $("b-msg").textContent = "Backed up.";
  } catch (e) { $("b-msg").textContent = e.message; }
}

async function restoreBackup(b) {
  if (!confirm(`Replace all your progress (every certification) with the backup made ${when(b.created_at)}? ` +
    `It holds ${plural(b.sessions, "session")} and ${plural(b.answers, "answer")}. Your current progress is backed up first.`)) return;
  try {
    const r = await post("/api/progress/restore", { name: b.name, confirm: "RESTORE" });
    S = null;
    await renderBackups();
    $("b-msg").textContent = `Restored ${plural(r.sessions, "session")} and ${plural(r.answers, "answer")}.` +
      (r.safety_backup ? " What you had before is saved as the newest \"Before a restore\" backup." : "");
  } catch (e) { $("b-msg").textContent = e.message; }
}

// ---- export, reset --------------------------------------------------------

// Questions answered correctly at 5 Certain every recent time. "Keep" is remembered in this browser only.
async function renderTooEasy(codes) {
  const keepKey = `certprep.keepEasy.${cert.id}`;
  const kept = new Set(store.get(keepKey, []));
  const items = (await api(certPath(`/too-easy?${sectionQuery(codes)}`))).filter((q) => !kept.has(q.id));
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
    keep.addEventListener("click", () => { kept.add(q.id); store.set(keepKey, [...kept]); box.remove(); });
    const formArea = el("div");
    const actions = el("div", "row");
    actions.append(keep, reportButton(q.id, null, formArea, "Report as too easy", "too-easy", () => setTimeout(() => box.remove(), 600)));
    box.append(opts, actions, formArea);
    return box;
  }));
}

async function exportSummary() {
  const { text } = await api(certPath("/export"));
  $("export-text").value = text;
  $("export-box").hidden = false;
}

async function resetProgress() {
  if (!confirm(`Delete all sessions and answers for ${cert.short_name}? Question pools are kept, and a backup of your progress is saved first.`)) return;
  await post(certPath("/progress/reset"), { confirm: "RESET" });
  $("home-msg").textContent = "";
  $("export-box").hidden = true;
  alert("Progress reset.");
}

// ---- wiring -------------------------------------------------------------

for (const b of document.querySelectorAll("[data-mode]")) b.addEventListener("click", () => startSession(b.dataset.mode));
$("cert-select").addEventListener("change", () => {
  store.set("certprep.cert", $("cert-select").value);
  $("export-box").hidden = true;
  loadHome();
});
$("sel-all").addEventListener("click", () => {
  for (const i of document.querySelectorAll("#section-list input:not(:disabled)")) i.checked = true;
  store.set(sectionsKey(), selectedSections());
});
$("sel-none").addEventListener("click", () => {
  for (const i of document.querySelectorAll("#section-list input")) i.checked = false;
  store.set(sectionsKey(), []);
});
$("s-form").addEventListener("submit", submitAnswer);
$("s-form").addEventListener("change", () => { $("s-msg").textContent = ""; });
const revealOptions = () => {
  const q = S.questions[S.i];
  S.notes[q.id] = $("s-recall-note").value;
  S.shown[q.id] = true;
  renderQuestion();
};
$("s-reveal").addEventListener("click", revealOptions);
$("s-recall-note").addEventListener("keydown", (e) => { if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); revealOptions(); } });
$("recall-first").checked = store.get("certprep.recall", false);
$("recall-first").addEventListener("change", () => store.set("certprep.recall", $("recall-first").checked));
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
// Keys in a session: letters pick options, 1-5 set confidence, Enter submits or moves on.
// Typing in a text box, or Enter on a focused button or link, is left alone.
document.addEventListener("keydown", (e) => {
  if ($("v-session").hidden || e.ctrlKey || e.altKey || e.metaKey) return;
  const t = e.target;
  if (t.matches("textarea, select, input:not([type=radio]):not([type=checkbox])")) return;
  const key = e.key.toUpperCase();
  if (/^[A-F]$/.test(key)) {
    const opt = document.querySelector(`#s-options input[value="${key}"]:not(:disabled)`);
    if (opt) { e.preventDefault(); opt.click(); }
  } else if (/^[1-5]$/.test(key)) {
    const conf = document.querySelector(`#s-conf input[value="${key}"]:not(:disabled)`);
    if (conf) { e.preventDefault(); conf.click(); }
  } else if (key === "ENTER" && !t.matches("button, a")) {
    e.preventDefault();
    if (!$("s-submit").hidden && !$("s-submit").disabled) $("s-form").requestSubmit();
    else if (!$("s-next").hidden) $("s-next").click();
  }
});
$("disputes-btn").addEventListener("click", () => openDisputes().catch((e) => { $("home-msg").textContent = e.message; }));
$("focus-btn").addEventListener("click", () => openFocus().catch((e) => { $("home-msg").textContent = e.message; }));
$("add-cert").addEventListener("click", () => {
  if (S && !confirm("Leave this session?")) return;
  clearInterval(timerHandle);
  S = null;
  openWizard().catch((e) => { $("home-msg").textContent = e.message; });
});
$("w-discard").addEventListener("click", discardWizard);
$("welcome-other").addEventListener("click", () => {
  $("welcome").close();
  openWizard().catch((e) => { $("home-msg").textContent = e.message; });
});
$("welcome").addEventListener("close", () => store.set("certprep.welcomed", true));  // any way out counts as answered
$("welcome-pack").addEventListener("click", () => { $("welcome").close(); openPackImport(); });
$("help-btn").addEventListener("click", () => openHelp());
$("help-back").addEventListener("click", () => show(helpReturn));
document.addEventListener("click", (e) => {
  const link = e.target.closest?.(".help-link");
  if (link) { e.preventDefault(); openHelp(link.dataset.help); }
});
$("health-btn").addEventListener("click", () => openHealth().catch((e) => { $("home-msg").textContent = e.message; }));
$("pack-retired").addEventListener("change", updatePackLink);
$("pk-file").addEventListener("change", checkPack);
$("pk-import").addEventListener("click", importPack);
$("f-text").addEventListener("input", updateFocusCount);
$("f-text").addEventListener("keydown", (e) => { if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); runFocusMatch(); } });
$("f-match").addEventListener("click", runFocusMatch);
$("f-start").addEventListener("click", () => {
  const ids = focusChosen().filter((m) => m.questions > 0).map((m) => m.objective);
  if (!ids.length) { $("f-msg").textContent = "Keep at least one objective that has questions."; return; }
  startSession("focus", ids);
});
const failHome = (e) => { $("home-msg").textContent = e.message; };
$("progress-btn").addEventListener("click", () => openProgress().catch(failHome));
$("suggest-link").addEventListener("click", () => openProgress("p-suggest-h").catch(failHome));
$("p-obj").addEventListener("change", () => showObjective($("p-obj").value).catch((e) => { $("p-obj-chart").replaceChildren(el("p", "msg", e.message)); }));
$("backups-btn").addEventListener("click", () => openBackups().catch(failHome));
$("backup-now").addEventListener("click", backupNow);
$("export-btn").addEventListener("click", exportSummary);
$("copy-btn").addEventListener("click", () => navigator.clipboard?.writeText($("export-text").value));
$("reset-btn").addEventListener("click", resetProgress);
$("claude-btn").addEventListener("click", () => openClaude().catch((e) => { $("home-msg").textContent = e.message; }));
$("obj-section").addEventListener("change", renderObjectiveList);
$("pick-gaps").addEventListener("click", () => pickWhere((o) => o.questions < 2, "objectives with fewer than 2 questions"));
$("pick-weak").addEventListener("click", () => pickWhere((o) => o.status === "Weak", "weak objectives"));
$("pick-clear").addEventListener("click", () => { CL.picked.clear(); $("claude-msg").textContent = ""; renderObjectiveList(); });
$("build-questions").addEventListener("click", () => buildPrompt("questions"));
$("build-study").addEventListener("click", () => buildPrompt("study"));
$("import-file").addEventListener("change", loadImportFile);
$("import-btn").addEventListener("click", runImport);
$("home-link").addEventListener("click", (e) => { e.preventDefault(); if (!S || confirm("Leave this session?")) { clearInterval(timerHandle); S = null; loadHome(); } });
for (const b of document.querySelectorAll(".back-btn")) b.addEventListener("click", loadHome);

loadHome().then(maybeWelcome).catch((e) => { $("home-msg").textContent = e.message; });
