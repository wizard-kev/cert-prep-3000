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
const MODE_LABEL = { diagnostic: "Diagnostic", drill: "Targeted drill", exam: "Exam simulation", review: "Review misses" };
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
  const withQuestions = sections.filter((s) => s.draft + s.verified > 0);
  const saved = new Set(store.get(sectionsKey(), withQuestions.slice(0, 1).map((s) => s.code)));
  const empty = sections.filter((s) => s.draft + s.verified === 0);
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
    text.append(el("span", null, s.name), el("small", null, `${s.verified} verified · ${s.draft} draft`));
    label.append(box, text);
    return label;
  }));

  $("pool-actions").replaceChildren(...sections.filter((s) => s.draft > 0).map((s) => {
    const b = el("button", "secondary small", `Review drafts: ${s.code} (${s.draft})`);
    b.type = "button";
    b.addEventListener("click", () => openQueue(s));
    return b;
  }));
  if (!$("pool-actions").children.length) $("pool-actions").append(el("span", "muted", "No drafts waiting for review."));

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
  if (mode === "drill") body.count = Number($("drill-count").value);
  if (mode === "exam") { body.count = Number($("exam-count").value); body.minutes = Number($("exam-minutes").value); }
  try {
    const s = await post(certPath("/sessions"), body);
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

// Error type (for misses), report, and ask-Claude controls shared by feedback and reports.
function questionTools(full, correct, sessionId, selected = []) {
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
  tools.append(ask, reportControl(full.id));
  const wrap = el("div");
  wrap.append(tools, askOut);
  return wrap;
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
        await post(certPath(`/questions/${encodeURIComponent(questionId)}/report`), { reason: sel.value, note: note.value });
        wrap.replaceChildren(el("span", "muted", "Reported and retired. It will not be served again."));
        onDone?.();
      } catch (e) { alert(e.message); }
    });
    wrap.replaceChildren(sel, note, go);
  });
  wrap.append(btn);
  return wrap;
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
    if (!q.retired_reason) box.append(questionTools(q, it.correct || !it.attempt, s.id, it.attempt?.selected ?? []));
    // Misses start expanded where feedback was withheld until now.
    box.open = !it.correct && (s.mode === "exam" || s.mode === "diagnostic");
    return box;
  }));
  S = null;
  show("report");
}

// ---- draft review queue -------------------------------------------------

let Q = null;

async function openQueue(section) {
  Q = { section, items: await api(certPath(`/review-queue?${sectionQuery([section.code])}`)), i: 0, verified: 0, reported: 0 };
  show("queue");
  renderQueueCard();
}

function renderQueueCard() {
  const card = $("q-card");
  $("q-h").textContent = `Review drafts: ${Q.section.name}`;
  $("q-progress").textContent = `${Q.items.length - Q.i} left · ${Q.verified} verified · ${Q.reported} reported this visit. ` +
    "Check the keyed answer, every rationale, and the facts against your study material and the objective file.";
  if (Q.i >= Q.items.length) {
    card.replaceChildren(el("p", null, "No drafts left in this section."));
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
    try { await post(certPath(`/questions/${encodeURIComponent(q.id)}/verify`)); Q.verified++; Q.i++; renderQueueCard(); }
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

async function buildPrompt(kind) {
  $("claude-msg").textContent = "";
  const ids = [...CL.picked].sort();
  if (!ids.length) { $("claude-msg").textContent = "Choose at least one objective first."; return; }
  if (ids.length > MAX_PROMPT_OBJECTIVES) { $("claude-msg").textContent = `Choose at most ${MAX_PROMPT_OBJECTIVES} objectives.`; return; }
  const q = ids.map((id) => `objective=${encodeURIComponent(id)}`).join("&");
  try {
    if (kind === "questions") {
      const r = await api(certPath(`/prompts/questions?${q}&per_objective=${$("per-objective").value}`));
      $("prompt-box").replaceChildren(promptWidget(`Question prompt (${r.targets.length} question${r.targets.length === 1 ? "" : "s"})`, r.prompt,
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
      parts.push(el("p", "ok-list", `Added ${r.accepted.length === 1 ? "1 question as a draft" : `${r.accepted.length} questions as drafts`}: ` +
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

// ---- tracker, export, reset ----------------------------------------------

async function openProgress() {
  const codes = sections.filter((s) => s.draft + s.verified > 0).map((s) => s.code);
  if (!codes.length) { $("home-msg").textContent = "No questions yet, so there's no progress to show."; return; }
  const rows = await api(certPath(`/tracker?${sectionQuery(codes)}`));
  const counts = rows.reduce((m, r) => ((m[r.status] = (m[r.status] || 0) + 1), m), {});
  $("p-summary").textContent = ["Weak", "Improving", "Solid", "New"].map((s) => `${s}: ${counts[s] || 0}`).join(" · ") +
    ". Solid needs 3 correct across 2+ sessions and 2+ angles with the last five at 80% or better." +
    " Correct answers marked Guess don't count toward mastery (shown as ?).";
  table($("p-table"), ["ID", "Objective", "Status", "Tries", "Last five", "Sure-wrong", "Main error", "Revisit"],
    rows.map((r) => [r.objective, r.name, el("span", `status-${r.status}`, r.status), String(r.attempts),
      r.last5_marks.map((m) => LAST5_MARK[m]).join(" "), r.sure_wrong_recent ? String(r.sure_wrong_recent) : "",
      r.dominant_error ?? "", r.revisit_due ? "due" : ""]));
  await renderTooEasy(codes);
  show("progress");
}

// Questions answered correctly and "sure" every recent time. "Keep" is remembered in this browser only.
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
    const actions = el("div", "row");
    actions.append(keep, reportControl(q.id, () => setTimeout(() => box.remove(), 600), "too-easy"));
    box.append(opts, actions);
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
$("progress-btn").addEventListener("click", openProgress);
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
