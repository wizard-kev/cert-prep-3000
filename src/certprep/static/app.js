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
  if (!(await loadCert())) {
    $("section-list").replaceChildren();
    $("section-empty").textContent = "No certifications are installed yet.";
    show("home");
    return;
  }
  sections = await api(certPath("/sections"));
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
      el("small", null, `${s.served} questions · ${checked} answered or validated · ${s.unreviewed} unreviewed`));
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

async function startSession(mode) {
  $("home-msg").textContent = "";
  const secs = selectedSections();
  if (!secs.length) { $("home-msg").textContent = "Select at least one section."; return; }
  const body = { mode, sections: secs };
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

function loadImportFile() {
  const file = $("import-file").files[0];
  if (!file) return;
  if (file.size > MAX_IMPORT_CHARS) { $("claude-msg").textContent = "That file is too large to import."; $("import-file").value = ""; return; }
  const reader = new FileReader();
  reader.onload = () => { $("import-text").value = String(reader.result); };
  reader.onerror = () => { $("claude-msg").textContent = "Couldn't read that file."; };
  reader.readAsText(file);
}

async function runImport() {
  const text = $("import-text").value;
  const out = $("import-result");
  if (!text.trim()) { out.replaceChildren(el("p", "msg", "Paste Claude's reply (or choose its file) first.")); return; }
  if (text.length > MAX_IMPORT_CHARS) { out.replaceChildren(el("p", "msg", "That reply is too long to import at once.")); return; }
  $("import-btn").disabled = true;
  try {
    const r = await post(certPath("/imports"), { text });
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
    out.replaceChildren(...parts);
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

loadHome();
