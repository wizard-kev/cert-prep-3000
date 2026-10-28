# Kevin's Super Cert Prep 3000: v2 Scope and Plan

**Status:** complete. Signed off 2026-10-27; all phases landed by 2026-10-28 and tagged `v2` (see section 15).
**Baseline:** git tag `v1` (commit 5de21fe) and `C:\Claude\CCST Snapshots\CCST_v1_snapshot_2026-10-27.zip`. v1 is the CCST-only app; this document supersedes `CCST_Project_Scope_and_Plan.md` wherever they differ. The v1 plan stays as the record of how the CCST pool was built.

---

## 1. Goal

A local study app that works for **any certification**. The user brings their own certification; pre-built Claude prompts do the heavy lifting of turning official exam information into the app's formats; the app then serves targeted questions, simulates the exam, and tracks comprehension per objective across sessions. CCST Cybersecurity (100-160) ships pre-built. Everything must be intuitive for a non-technical user, with instructions and descriptions built into the app.

## 2. Decisions

| # | Decision | Source |
|---|---|---|
| V1 | The app supports any certification. CCST ships pre-built; other certifications are set up through a guided wizard or imported as a certification pack. | User |
| V2 | No AI model runs inside the app and the app makes no network calls. It builds prompts that the user copies into a Claude web chat; Claude's output is imported back as a file or pasted text. The app holds no API keys. | User |
| V3 | Local model infrastructure (Ollama provider, generation and explanation jobs) and Docker are removed. The app installs natively (Python virtual environment plus a start shortcut). | User |
| V4 | Questions are validated passively: answered without dispute = **Passively-Validated**. Questions that pass the import checks are assumed valid until disputed. The separate review queue is removed. | User |
| V5 | Three modes: **Practice** (adaptive, includes re-serving missed questions), **Focus** (pasted objective list), **Exam** (simulation). Diagnostic and Review modes are retired. | User |
| V6 | Confidence is a 1-5 scale (stars or slider), recorded per answer and used for per-objective progress over time. | User |
| V7 | Progress persists across sessions and survives upgrades; it can be backed up and restored from the app. Essential priority. | User |
| V8 | A dispute raised during an exam is held until the end-of-exam report, where the user confirms or withdraws it. | User (recommendation accepted) |
| V9 | App name: **Kevin's Super Cert Prep 3000**. All explicit CCST references outside the CCST certification data are generalized. | User |
| V10 | Certifications can be exported and imported as packs. | User |
| V11 | Struggling objectives produce a recommendation to generate more questions, with a ready-made prompt. | User |

**Carried from v1 (unchanged):** objective IDs are frozen within a certification (retire, never rename); questions are retired, never edited in place; never use real exam questions (brain dumps); all content is rendered as plain text (`textContent`); the authoring rules for cue-free questions (four option roles, no surface cues, exhibits, angle rotation) and the import cue checks stay in force for every certification.

## 3. Certification model

### 3.1 Layout

```
data/
  certs/
    ccst-cyber/                 # one folder per certification; folder name = certification id
      cert.json                 # exam facts and structure (3.2)
      objectives/S01.md ...     # one objective file per section
      questions/S01.json ...    # question pool per section
      imports/                  # archived copies of every imported Claude file
  progress.db                   # all learner progress, every certification (section 8)
  backups/                      # automatic and manual progress backups
```

- The certification id is a slug matching `^[a-z0-9][a-z0-9-]{1,31}$` and must be one of the folders found at startup. Section codes come from `cert.json` and match `^[A-Z]{1,3}\d{2}$`.
- Objective IDs are `<section code>-<NN>`; question IDs are `Q-<section code>-<NNNN>`, unique within a certification. Every stored record carries the certification id.
- **CCST keeps its existing IDs** (sections C01-C13, objectives `C01-01`, questions `Q-C01-0195`), so the 917 active questions and all recorded answers carry over unchanged.

### 3.2 `cert.json`

Exam facts used to replicate the test environment, each with a source and a confidence label (official / estimate / unknown), as the v1 plan did for CCST:

- name, vendor, exam code, exam version and objective-list date;
- question count, time limit (minutes), passing score (and its scale, e.g. 700/1000 or 70%);
- question formats used on the real exam (multiple choice, multiple response, ordering, matching/drag-and-drop, simulations) and which of them the app can serve (section 7.4);
- domains with official weights; sections (chapters or domains) with title, section code, and domain mapping;
- sources (official URLs) and the date the facts were gathered.

### 3.3 Setting up a certification

The **certification wizard** walks the user step by step; it can be saved and resumed:

1. **Name the certification** (name, vendor, exam code).
2. **Exam facts:** the app builds a prompt asking Claude to gather the official exam facts (3.2), cite sources, and mark anything it can't confirm. The user pastes or uploads Claude's JSON; the app validates it and shows a preview to confirm or edit.
3. **Objectives:** the user pastes the vendor's published objective list into a second prompt. Claude returns objective files in the app's format (ID, objective, core idea, discriminator, official reference number such as `4.2`). The app validates and previews them.
4. **First questions:** the app builds question-generation prompts in batches until every objective has at least two questions, with a progress bar.
5. **Done:** start a Practice session.

## 4. Startup and onboarding

- **First start:** a dialog asks "Which certification are you studying?" with three choices: **CCST Cybersecurity** (loads the pre-built certification), **Something else** (starts the wizard), **Import a certification pack**.
- A certification selector in the top bar switches between installed certifications.
- Every screen has a short "What is this?" description; empty screens say what to do next (for example "No questions for this objective yet: generate some").
- A help page and a glossary explain statuses (Unreviewed, Passively-Validated, Validated, Disputed, Retired), objective levels (New, Weak, Improving, Solid), the confidence scale, and how scores are calculated.

## 5. Prompt builder (replaces the local model)

### 5.1 Prompt types

| Prompt | Built from | Claude returns |
|---|---|---|
| Exam facts | Certification name and exam code | `cert.json` content |
| Objective builder | Pasted official objective list | Objective files |
| Question generation | Chosen objectives (coverage gaps, struggling objectives, Focus bullets, or a manual pick), their rows, the authoring rules, angles already used, and the learner's common wrong choices | Question JSON file |
| Repair | Rejected questions plus the reasons | Corrected question JSON |
| Study dialogue | Chosen objectives plus the learner's progress (weak objectives, wrong options chosen, error types) | A guided tutoring conversation |
| Ask about this question | One question, its answer, rationales, and objective rows | A focused explanation |

Every prompt states Claude's role and context, the exact output format with an example, the rules the import will enforce, and a prompt-format version that the import checks. Prompts are built only from stored data and text the user pasted on purpose; the app never sends them anywhere (the user copies them).

### 5.2 Import

- **Input:** upload a `.json` file or paste text, up to 1 MB.
- **Checks:**
  - strict JSON parse and schema validation (unknown fields rejected);
  - objective IDs must belong to the active certification;
  - the per-question cue checks and near-duplicate check from v1.
- **Results:** a table of accepted and rejected questions with the reason for each. One click copies a **repair prompt** for the rejected questions.
- **After import:** accepted questions enter as **Unreviewed**, and the source file is archived in `imports/`.
- **Pool balance:** shown on a question-bank health page (answer-length bands, coverage per objective, angles), replacing the CLI-only `audit` and `coverage`. The CLI stays for power users.

## 6. Question lifecycle and validation (replaces v1 D7)

| Status | Meaning | Served in |
|---|---|---|
| Unreviewed | Passed the import checks; not yet answered | Practice, Focus, Exam |
| Passively-Validated | Answered at least once, in any mode, and not disputed | Practice, Focus, Exam |
| Validated | Explicitly confirmed by the user ("Looks right"); v1 `verified` questions map here | Practice, Focus, Exam |
| Disputed | Reported by the user, awaiting confirmation; excluded from selection and scoring | None |
| Retired | Dispute confirmed, superseded, or flawed | None |

- **Disputing** ("Report a problem", with a reason) is available in every mode.
  - **Practice and Focus:** the question becomes Disputed immediately. The session summary lists disputed questions to confirm (they are retired) or undo.
  - **Exam:** the dispute is held. The end-of-exam report shows the question with its answer, and the user confirms or withdraws (V8).
- **"Mark for review"** (exam navigation) is separate from "Report a problem".
- **Migration from v1:** draft questions that have been answered become Passively-Validated; unanswered drafts become Unreviewed; retired questions stay retired with their reasons.

## 7. Modes

### 7.1 Practice
Adaptive selection weighted toward Weak objectives, then Improving and due Solid ones. Objectives never attempted are guaranteed regular appearances (they were previously introduced by the diagnostic), and recently missed questions are re-served on a spaced schedule (replacing Review mode). Immediate feedback after each answer.

### 7.2 Focus (pasted objectives)
1. The user pastes an objective list (bullets; designed for 5 or more, no hard minimum).
2. The app splits it into bullets and matches each against the active certification's objectives using plain text matching. It matches on official reference numbers or objective IDs when present, otherwise on word overlap with the objective name and core idea. No AI model is involved.
3. A **match preview** shows each bullet's best match and confidence, and lets the user accept or change the match before starting.
4. Bullets that don't match get the message "This objective is not in the objective list for (certification)."
5. A matched objective with no questions gets "No questions exist for this objective yet." The user is offered a ready-made generation prompt for that bullet.
6. The session serves questions only from the confirmed objectives.

Security requirements for this mode are in section 10 (SR-2, SR-3, SR-7).

### 7.3 Exam
- **Settings:** question count, time limit, domain weights and passing score come from `cert.json`.
- **Selection:** prefers questions the user hasn't seen.
- **Feedback:** deferred until the end. "Mark for review" and held disputes are available during the exam.
- **Report:**
  - **Score (all questions):** correct out of all exam questions, excluding confirmed disputes. This includes Unreviewed, Passively-Validated and Validated questions.
  - **Score (validated questions only):** the same, counting only questions that were Passively-Validated or Validated when the exam started.
  - Pass or fail against the certification's passing score, per-domain results, and a new-versus-repeat breakdown.

### 7.4 Question formats
v2 serves multiple choice (single answer) and multiple response (choose N). `cert.json` records the real exam's other formats. Ordering and matching are optional later work (phase P10), to be built if a certification the user studies relies on them.

## 8. Progress tracking (essential, V6, V7)

### 8.1 Storage and safety
- **Storage:** all progress lives in `data/progress.db` (SQLite), keyed by certification. It persists across sessions and app restarts. Unfinished sessions can be resumed.
- **Migration:** the v1 `tracker.db` (17 sessions, 318 answers) is migrated to `progress.db`. Confidence maps guess → 1, unsure → 2, sure → 5. Diagnostic and drill sessions keep their history under their original mode names.
- **Automatic backup** before every migration or app upgrade, keeping the last 10.
- **Manual backup:** "Back up progress" and "Restore progress" on the settings page.
- Progress is never stored in git; certification packs never include it unless the user exports it separately.

### 8.2 Confidence scale (1-5)
| Rating | Label |
|---|---|
| 1 | Guessing |
| 2 | Unsure |
| 3 | Leaning |
| 4 | Confident |
| 5 | Certain |

- Answers are entered by clicking or with the keyboard: letters for options, 1-5 for confidence.
- **Mastery credit:** a correct answer at confidence 1 counts as a guess, not mastery (the v1 guess rule).
- **Overconfidence:** a wrong answer at confidence 4-5 keeps the objective Weak (the v1 "sure but wrong" rule).

### 8.3 Progress over time
- **Objective score (0-100):** a recency-weighted average of answer scores. Correct answers score higher at higher confidence, and wrong answers score lower at higher confidence (an overconfidence penalty). The exact formula is fixed in phase P6 and explained on the help page.
- **Charts:**
  - each objective's score over time;
  - section and domain totals;
  - a calibration chart (accuracy at each confidence level);
  - New/Weak/Improving/Solid counts over time.
- **Recommendations (V11):** a "Generate more questions" card appears for objectives that are:
  - Weak after several attempts;
  - out of unseen questions;
  - consistently answered correctly at confidence 5 (too easy).
  One click builds the prompt, including the wrong options the learner tends to pick, so the new questions target those misconceptions.

## 9. Certification packs (V10)

- **Export:** a `.zip` containing `cert.json`, objective files, active questions (retired ones optional) and a manifest with file hashes and a pack-format version. Progress is not included.
- **Import:** see SR-5. The pack is imported under a new certification id; an existing certification is never overwritten without confirmation.
- **Copyright:** packs built from published vendor objective lists are fine for personal use. CCST's objective files were derived from a study guide, so its pack should not be shared publicly.

## 10. Security requirements (v2)

| # | Requirement |
|---|---|
| SR-1 | The server listens on 127.0.0.1 only. Requests must carry an allowed `Host` header (`127.0.0.1`/`localhost` with the app's port) to block DNS rebinding. Every state-changing request needs a matching `Origin` and a per-launch CSRF token, so other websites can't drive the app. |
| SR-2 | All user-supplied text (Focus pastes, wizard pastes, imported files) is data only. Limits: Focus 8,000 characters, 60 bullets, 300 characters per bullet; imports 1 MB. Text is decoded strictly as UTF-8, normalized with Unicode NFKC, and stripped of control characters. It is never used in file paths, SQL strings (parameterized queries only), regular expressions, shell commands, or `eval`. |
| SR-3 | Files are reached only through indexes the server builds from the allowlisted folders (`data/certs/<id>/objectives`, `.../questions`). Certification ids and section codes are regex-checked and must exist in that index. Stored file names are generated by the server; names supplied by the user are never used on disk. |
| SR-4 | The UI renders content with `textContent` only, never `innerHTML` with data. A Content-Security-Policy header limits scripts and styles to the app itself. |
| SR-5 | **Uploads:** only `.json`, `.md`, `.txt`, and `.zip` (packs) are accepted, with size caps. **Packs:** at most 20 MB and 2,000 entries. Only expected paths are allowed: no absolute paths, `..`, links, or duplicate names. Each file has a size cap and a compression-ratio limit to stop zip bombs. Every file is fully validated before anything is written. |
| SR-6 | The app holds no secrets and makes no outbound network calls. |
| SR-7 | Focus results reveal only matched objective IDs, objective names, and questions, never raw file contents or paths. |
| SR-8 | Imported content is validated against the schema. Unknown fields are rejected, and every ID must belong to the target certification. |

Security tests (unit tests plus fuzzed inputs for SR-2, SR-3, SR-5, and SR-7) are part of each phase's exit criteria.

## 11. Removals

- Ollama provider and the provider abstraction.
- The generation and explanation endpoints, job queue, model lock, and cooldowns.
- The Claude API stub.
- Docker files: `Dockerfile`, `docker-compose*.yml`, `.dockerignore`.
- Installer logic for Docker and models, and the offline model bundle (`make-bundle.ps1`).
- The CLI `generate` command.
- Diagnostic and Review modes.
- The review queue and its Verify flow.

## 12. Install and run

- **Install:** a native installer checks for Python (3.12 or newer), creates the virtual environment, installs pinned requirements, and adds a desktop and Start-menu shortcut named "Kevin's Super Cert Prep 3000". The shortcut starts the server and opens the browser.
- **Uninstall:** keeps progress unless the user asks to remove it.
- **Rename:** the Python package is renamed from `ccst` to `certprep`. Renaming the project folder (`CCST Testing Program`) is optional and left to the user, since tools reference that path.

## 13. Build plan

Each phase ends with the tests passing, a commit, and a short note in this document. The `v1` tag remains the fallback.

| Phase | Work | Exit criteria |
|---|---|---|
| P1 | Remove the local model and Docker (section 11); native run and installer | No Ollama or Docker references remain; the app runs natively; tests pass |
| P2 | Certification data model; move CCST into `data/certs/ccst-cyber`; rename the app and package; `progress.db` migration with automatic backup | CCST works as before; question and objective IDs unchanged; all 318 recorded answers still counted; backup created |
| P3 | Security baseline (SR-1 to SR-4) before any new input surfaces | Host, Origin, CSRF, and CSP checks tested |
| P4 | Prompt builder (question generation, repair, study dialogue, ask-about-question) and in-app import | A Claude-made file imports end to end (first use: a replacement for reported Q-C09-0100) |
| P5 | Question statuses and dispute flow; Practice and Exam modes; 1-5 confidence; scoring (7.3) | v1 statuses migrated; both exam scores correct in tests |
| P6 | Progress over time: objective scores, charts, backup and restore, struggle recommendations | History charts show v1 answers; restore round-trip tested |
| P7 | Focus mode with match preview | Matching and the messages tested; SR-2, SR-3, and SR-7 fuzz tests pass |
| P8 | Certification wizard, exam-facts and objective-builder prompts, first-start dialog | A second certification can be set up end to end through the UI only |
| P9 | Certification pack export and import; help page, glossary, and in-app guidance; usability pass | A CCST pack round-trips; SR-5 tests pass |
| P10 | Optional: ordering and matching question formats | Only if a target certification needs them |
| P11 | Finish v2 (added 2026-10-28): resume unfinished sessions (8.1), a check of the real app on the real data, docs, `v2` tag | Resume tested; real data unchanged by the check; tests pass |

## 14. Open points and risks

- **Matching quality (Focus):** official wording can differ from objective-file wording. Mitigation: the match preview, plus official reference numbers in objective files.
- **Claude output conformance:** first drafts often fail the cue checks. Mitigation: the repair-prompt loop, and prompts that state the checks explicitly.
- **Exam facts accuracy:** vendors don't always publish weights or passing scores. Mitigation: per-fact confidence labels and user review in the wizard.
- **Passive validation is weak evidence:** a wrong answer key is most convincing right after the learner gets the question wrong. Mitigation: a one-click "Disagree with this answer?" on the feedback after every wrong answer.

## 15. Progress log

- **Plan signed off (2026-10-27).**
- **P1 done (2026-10-27):** local model and Docker removed.
  - **Removed:** the provider package (Ollama, Claude API stub); the generate, explain, status and job endpoints with their model lock and cooldowns; the UI model badge, Explain button and Generate box; the CLI `generate` command; the Dockerfile, compose files and `.dockerignore`; the offline model bundle script; and the model-selection installer test.
  - **Question provenance:** `provider` is now a validated free-text field, since the pool still records two retired questions written by the old local model.
  - **New launcher:** `src/ccst/launch.py` runs the app on 127.0.0.1 only. It refuses a port held by another program, reuses an instance that's already running, and opens the browser once the app answers. `run.ps1` wraps it.
  - **New native installer** (`install/install.ps1`, `lib.ps1`, `uninstall.ps1`):
    - finds Python 3.12+ (skipping the Microsoft Store placeholder);
    - builds or repairs `.venv`;
    - removes obsolete model settings from `.env`;
    - checks the port;
    - creates desktop and Start-menu shortcuts that run `run.ps1 -PauseOnError`.
  - **Uninstaller:** stops this project's app processes, removes the shortcuts and `.venv`, and keeps progress unless asked.
  - **Dependencies:** `httpx` moved to the dev requirements (only the test client uses it).
  - **Tests:** 71 pytest (4 new launcher tests) and 17 PowerShell checks (`tests/test_install_lib.ps1`) pass.
  - **Verified by hand:**
    - the installer ran on this PC (shortcuts skipped);
    - `run.ps1` served the app on 127.0.0.1:8000;
    - the removed endpoints return 404;
    - a second launch reused the running app;
    - the uninstaller's process detection found and stopped both Python processes;
    - in a UI check against a scratch copy of the data, the feedback panel no longer offers Explain.
  - The v1 authoring rules that the old model prompt carried live on in `CLAUDE.md` and in `git show v1:src/ccst/generator.py`, for the P4 prompt builder.
- **P2 done (2026-10-27):** certification data model, CCST moved into it, app renamed, progress migrated.
  - **Package:** `src/ccst` renamed to `src/certprep` (history kept with `git mv`). Settings are `CERTPREP_PORT`, `CERTPREP_DATA_DIR` and `CERTPREP_CERTS_DIR`; the installer renames `CCST_*` keys in `.env`.
  - **Layout:** `data/certs/ccst-cyber/` holds:
    - `cert.json`: exam facts from the v1 plan with confidence labels (50 minutes official; 40 questions estimate; passing score unknown); the five domains with the estimated 4:5:6:4:4 weights; 13 sections C01-C13 with their domains; the Cisco sources.
    - `objectives/C01.md`-`C13.md`, moved from `Objective Documents/`.
    - `questions/C01.json`-`C13.json`, moved from `data/questions/`. Each question's `chapter` became `section`, and `source_ref` now points at `objectives/<CODE>.md`. A one-off conversion verified that only those two fields changed across all 1,942 questions.
    - `imports/`, moved from `data/authored/`.
  - **IDs:** question and objective IDs are unchanged.
  - **New `certs.py`:** a registry built from disk. Folder ids and section codes are pattern-checked and must exist before any path is built. `cert.json` is validated strictly: unknown fields, duplicate sections, unknown domains and non-https sources are all rejected.
  - **Cert-aware code:** objectives, pool, generator, sessions, audit and CLI now take a certification and section codes. Exam defaults (count, minutes) and domain weights come from `cert.json`.
  - **API:** routes are under `/api/certs/{cert}/...`; session routes stay at `/api/sessions/{id}`.
  - **UI:**
    - the new app name, with the certification shown in the header (a selector when more than one is installed);
    - sections labelled with their names;
    - saved browser preferences carried over from the old `ccst.*` keys.
  - **Progress:**
    - `data/progress.db` gets a certification id on every session and answer, a schema version, automatic backups (10 kept per reason), a guard against databases from newer versions, and a backup before every reset.
    - Reset is now per certification.
    - On first start, the v1 `data/tracker.db` was migrated; the original moved unchanged to `data/backups/tracker-v1-20261027T170949-913714Z.db`.
  - **Verification:**
    - **Baseline:** before any code changed, objective stats, session reports, the export summary and the too-easy list were dumped from a copy using the v1 code.
    - **Rehearsal and real migration:** the migration was rehearsed on a copy, then run on the real data. In both, all 18 sessions and 318 answers migrated; all 212 objectives' stats, every session report and the too-easy list were identical; and the export summary differed only in the intended label changes. 315 of the 318 answers count toward objective status in both versions, because 3 are to reported questions.
    - **Tests:** 99 pytest and the installer library checks pass. New tests cover the registry and allowlists, `cert.json` validation, the migration (run-once, original kept), the schema guard, backup pruning, per-certification reset, and traversal attempts on certification ids and sections.
    - **Pool checks:** `audit` passes on the 917 active questions. `coverage` fails only for C09-23, the gap from Q-C09-0100, which the user reported on 2026-10-22.
    - **UI** (tested on a copy): home, drill, feedback, report, results, tracker, export and review queue all work with no console errors. The real launcher served the real data.
- **P3 done (2026-10-27):** security baseline. `src/certprep/security.py` adds ASGI middleware that runs before every route, so routes added later are covered automatically.
  - **SR-1 (Host):** only `127.0.0.1` or `localhost` (any port) are served, which defeats DNS rebinding. Anything else gets 403, including other names that resolve locally and `[::1]`.
  - **SR-1 (changes):** every POST needs:
    - an `Origin` exactly equal to `http://<Host>`;
    - no cross-site or same-site `Sec-Fetch-Site`;
    - the per-launch CSRF token in `X-CSRF-Token`.
  - **The token:** `/` serves the page with the token filled into a meta tag (`Cache-Control: no-store`), and `app.js` sends it back with every request. A page left open from an earlier launch gets a plain "reload the page" message.
  - **SR-2 (bodies):** request bodies must be JSON (415 otherwise), have a Content-Length (411 for chunked), and be at most 1 MB (413).
  - **SR-2 (free text):** `clean_text` applies Unicode NFKC, strips control and invisible characters (zero-width, bidirectional overrides), collapses whitespace, and checks the length after normalizing. The report note uses it now; P4 and P7 inputs will too.
  - **SR-4 (headers):** every response, including errors, refusals and static files, carries a strict CSP (`default-src 'none'`, scripts and styles from the app only, no inline code, no eval, `frame-ancestors 'none'`), plus `nosniff`, `X-Frame-Options: DENY`, `no-referrer`, COOP/CORP and a restrictive Permissions-Policy. API responses are `no-store`.
  - **Smaller changes:** the OpenAPI schema and docs are no longer served. The launcher turns off uvicorn's forwarded-header trust and its `Server` header.
  - **SR-3:** done in P2.
  - **Tests:** 45 new (`tests/test_security.py`), 144 pytest in total, all passing. They cover:
    - allowed and refused hosts;
    - ten ways a change request can lack proof of origin;
    - a sweep confirming every POST route is protected;
    - body type, size and chunking;
    - headers on every kind of response;
    - the page token;
    - a static scan that fails if the UI ever builds HTML from strings or the page gains inline script, style or event handlers;
    - text cleaning.
  - **Verified by hand:** a full drill in the browser under the CSP, with no violations. Stale-token and no-token requests were refused, and the real launcher refused a rebinding Host and a token-less reset.
- **P4 done (2026-10-27):** prompt builder and in-app import.
  - **`prompts.py`:** four prompts.
    - **Question generation:** Claude's role; one numbered target per question, each with an objective, an angle and a type; the objective rows; neighbouring objectives for look-alike distractors; the learner's recent wrong choices when there is history; `RULES`, which mirror the import checks; and the exact reply format (`certprep-questions` v1) with a template. Up to 30 objectives, 1-3 questions each, at most 30 questions.
    - **Repair:** the rejected questions with their problems, asking for fixes that don't break another rule.
    - **Study session:** a tutor role, how to run the dialogue, the objectives, and the learner's progress and mistakes.
    - **Ask about this question:** replaces the old Explain button. It includes the learner's answer and asks Claude to say plainly if the key looks wrong, so the question can be reported.
  - **Angles:** `generator.targets_for` gives each objective the angles it has used least and never repeats its newest one. Retired questions count as used, so a replacement for a reported question takes a different approach.
  - **`importer.py`:**
    - **Parsing:** accepts a reply with or without a ```json fence and checks the wrapper (format, version, certification, 1-50 questions).
    - **Per question:** unknown fields are rejected, `clean_text` runs on every text field, and questions are grouped by the section of their primary objective and pass through the existing checks.
    - **Early rejects:** a question rejected for its fields still gets a dry run of the full checks, so one repair round fixes everything.
    - **After import:** the result adds a repair prompt and a pool answer-pattern warning when an import tips a section outside the audit bands. The cleaned reply is archived as `imports/claude-<time>-<hash>.json`.
  - **UI:**
    - a "Work with Claude" page with numbered steps;
    - objective picks ("fewer than 2 questions", "my weak objectives", or browsing by section);
    - question and study prompts with Copy buttons;
    - import by paste or file, with accepted and rejected results and the repair prompt;
    - "Ask Claude about this" on every question's feedback and report.
  - **Cache fix:** static files are now sent `Cache-Control: no-cache` (revalidated with ETag). Testing showed a browser mixing a cached old `app.js` with the new page after an update.
  - **Exit test, run on the real data through the real UI:**
    - "Fewer than 2 questions" found the one gap, C09-23 (Q-C09-0100, reported 2026-10-22), and built a prompt that assigned the classify-element angle, which C09-23 had never used.
    - A reply written to that prompt imported as **Q-C09-0154** (draft, claude/claude-chat), archived as `claude-20261027T173734Z-3dcc7933.json`. The reply was written in this Claude Code session standing in for claude.ai.
    - `coverage` passes for all 13 sections again; `audit` passes on 918 active questions.
  - **Tests:** 173 pytest pass, including 29 new prompt and import tests.
- **P5 done (2026-10-27):** question statuses and disputes, Practice and Exam modes, 1-5 confidence, scoring.
  - **Statuses (section 6):** `unreviewed`, `passive` (Passively-Validated), `validated`, `disputed`, `retired`.
    - The first three are served in every mode.
    - Answering marks an Unreviewed question Passively-Validated and records when it was first seen.
    - "Looks right" marks it Validated.
    - On startup the app brings statuses in line with the answer history. Legacy `draft`/`verified` values load as `unreviewed`/`validated`.
  - **Disputes:**
    - **Practice:** "Report a problem" (and "Disagree with this answer?" after a miss) makes a question Disputed at once. The results page and a new "Disputed questions" page offer Confirm (retire with `Reported by user`) or Undo (restore the previous status).
    - **Exam:** reports are held in `held_disputes`. They can be taken back during the exam and are confirmed or withdrawn on the results page, after the answer is shown.
    - Reporting on the normal route during an unfinished exam is refused.
  - **Confidence:** a 1-5 scale (Guessing, Unsure, Leaning, Confident, Certain) with no default.
    - Mastery rules are unchanged: 1 is not credited, a wrong answer at 4+ forces Weak, and "too easy" needs 5.
    - v1 values map guess -> 1, unsure -> 2, sure -> 5.
  - **Modes:**
    - **Practice** replaces Diagnostic, Drill and Review. It serves due misses first (1, 3 and 7 days after each miss, up to 30% of the session), then at least 20% untried objectives, then a weighted pick that favours Weak objectives. One question per objective.
    - **Exam** prefers unseen questions within each domain's share.
    - Old sessions keep their mode names in history.
  - **Scores:**
    - Every report shows all questions, validated-only (Passively-Validated or Validated when the session started), new and repeat.
    - Confirmed and pending disputes are left out.
    - Pass or fail appears only when `cert.json` gives the passing score as a percentage (CCST's is unknown, so the report says why there is none).
  - **Progress schema 2:** confidence is stored as an integer with a 1-5 check. Older databases are upgraded after a `progress-upgrade-*` backup.
  - **UI:**
    - The draft review queue is removed.
    - New: the confidence scale, keyboard shortcuts (letters for options, 1-5 for confidence, Enter to submit or move on), status tags that update in place, score cards and the disputes page.
    - Red "danger" buttons now have a transparent background, so they stay legible.
  - **Real-data upgrade:** the `certprep-dev` server (auto-reload, real data) applied the upgrade as soon as the code was saved, before the planned rehearsal. It was then verified after the fact:
    - **Progress:** the P4 code on the `progress-upgrade-20261027T174804-789754Z.db` backup and the P5 code on a copy of the upgraded database gave the same 18 sessions and 318 answers (confidence mapped), and identical stats for all 212 objectives apart from the confidence breakdown's labels. Two old sessions score higher because the 3 questions reported in v1 are now left out of their scores, as designed.
    - **Pools:** against the P4 commit, 711 unanswered drafts became Unreviewed, 207 answered drafts became Passively-Validated, and 305 answered questions gained a first-seen time. Nothing else changed.
    - `coverage` passes for all 13 sections; `audit` passes on 918 active questions.
  - **Tests:** 187 pytest pass. `test_phase3.py` was rewritten for the new statuses, disputes, held reports, both selection modes, scores and the pass mark; the progress tests add the schema 1 -> 2 upgrade.
  - **Verified by hand** (scratch copy of the real data, in the browser):
    - practice driven by keyboard;
    - "Looks right";
    - a practice report with Undo on the results page;
    - an exam with a held report taken back, held again, then confirmed after the exam;
    - a report confirmed from the Disputed questions page;
    - the tracker.
    No console errors.
- **P6 done (2026-10-27):** progress over time, charts, backup and restore, suggestions.
  - **Objective score (8.3), the formula fixed here:**
    - Each answer scores 0-100: right is 50 at 1 Guessing rising to 100 at 5 Certain; wrong is 25 at 1 falling to 0 at 5 (the overconfidence penalty).
    - An objective's score is the recency-weighted average of its answers: each older answer counts 0.75 times as much as the next (`SCORE_DECAY`).
    - It is explained on the Progress page now and goes on the help page in P9. Status rules are unchanged.
    - `ObjectiveStats.add` folds in one answer at a time; the batch function now uses it and gives the same results.
  - **`history.py`:**
    - totals;
    - scores and status counts by section and by domain;
    - calibration (answers and % right at each confidence level);
    - status counts and average score after each session;
    - one objective's score after each answer.
    Answers to reported questions are left out, as everywhere else.
  - **Suggestions (V11):** an objective is suggested when it is Weak after 3+ answers, too easy (its latest 3 answers right at Certain), or out of unseen questions. They are grouped and ranked in that order.
    - One click opens the Claude workspace with the objectives picked and the question prompt built; the prompt already includes the learner's recent wrong choices.
    - Too-easy objectives get a new `harder` prompt option that asks for difficulty 3 throughout.
    - Home shows a link with the number of suggestions.
  - **Backups (8.1):**
    - A Backups page lists `data/backups` (server-built index, names pattern-checked), with Back up now, Restore and Download.
    - Restore reads the backup into memory, saves the current progress as `progress-before-restore-*` (so a restore can be undone), writes the backup, upgrades an older schema, and re-syncs question statuses.
    - It refuses newer, damaged or unlisted backups, and needs `confirm: "RESTORE"`.
  - **Charts:**
    - `static/charts.js` draws SVG through DOM calls only (CSP-safe): line, horizontal bars and columns, each with a crosshair or per-mark tooltip, arrow-key reading, and a "Show as a table" view.
    - All charts are single-series in the dataviz reference blue, which the palette validator passes on both card colors.
    - The status palette failed the colour-blindness check (red vs green ΔE 4.1 for deuteranopia), so status counts over time are four small charts named by their titles instead of four colored lines.
  - **Progress page:**
    - summary tiles;
    - suggestions;
    - average score and status counts after each session;
    - score by section and by domain;
    - calibration;
    - one objective over time (picker, or click an ID in the tracker);
    - the tracker, now with a Score column;
    - too-easy questions.
  - **Fixed along the way:**
    - `[hidden]` did not hide elements whose class sets `display` (the empty disputes row on home, the exam navigator in practice), a P5 bug. `style.css` now makes `[hidden]` always win, and a test checks it.
    - Selects are capped at the page width (a long objective list widened the page on phones).
  - **History shows the v1 answers:** on a copy of the real data the timeline runs from the first v1 session (2026-10-07) to the latest. It shows 315 counted answers, 212 of 459 objectives practised, an average score of 78, and 44 suggestions (6 weak, 10 too easy, 28 every question seen).
  - **Tests:** 205 pytest pass, 18 of them new: 16 in `test_history.py`, plus 2 UI checks in the security tests (the `charts.js` scan and the `[hidden]` rule). The `test_history.py` tests cover:
    - the score formula and recency;
    - incremental and batch stats agreeing;
    - per-session snapshots, calibration, totals;
    - reported answers left out;
    - the objective history API and bad IDs;
    - suggestion reasons and order;
    - the harder prompt;
    - backup listing (junk and damaged files);
    - restore round trip and undo;
    - restore of a schema-1 backup;
    - refusal of newer, damaged and unlisted backups;
    - a restore whose source is pruned by its own safety backup;
    - download;
    - status sync after a restore;
    - the token on backup routes.
    The security scan now covers `charts.js`.
  - **Verified by hand** (scratch copy of the real data, in the browser):
    - every chart rendered;
    - tooltips, crosshair and arrow keys worked, with no CSP violations;
    - a suggestion group built a 10-objective harder prompt;
    - a restore round trip through the UI: after a reset and a restore, the overview was identical to before;
    - the download was a valid SQLite file;
    - at 375px nothing overflows or overlaps;
    - practice and exam still show and hide the right controls.
    - Some screenshots came back blank because the browser pane was hidden; those layouts were checked by measuring the rendered elements instead.
- **P7 done (2026-10-27):** Focus mode with match preview.
  - **`focus.py`:**
    - **Splitting:** the pasted text goes through `clean_text` (NFKC, control and invisible characters removed) and is capped at 8,000 characters and 60 lines; lines over 300 characters are reported, not matched. List markers are removed (`-`, `*`, `•`, `1.`, `a)`, `[ ]`, `#`), and several bullets on one line are split. A dotted reference like `1.2` is kept, not mistaken for a list number.
    - **Matching, in order:**
      1. Objective IDs exactly; an unknown ID is "not known".
      2. A domain heading (`1.0 ...`) is skipped with a note.
      3. A reference number matches every objective whose new optional `Ref` column equals it or sits under it (4.2 → 4.2, 4.2.1). CCST's files have no Ref column yet; the phase 8 objective builder adds one.
      4. Otherwise words: rarer words count more, with crude stemming, near-prefixes (encrypt/encryption, not power/PowerShell) and acronyms the objective files write in capitals (man in the middle → MitM, Multi-factor authentication → MFA). A "heading: a, b (c, d)" line is matched topic by topic; values in parentheses need a strong match.
    - **Scoring:** how much of the line the objective explains × how much of the objective's name the line covers. Labels: strong ≥ 0.6, likely ≥ 0.4, weak ≥ 0.25; below that the line is not known.
    - **Messages:** "This objective is not in the objective list for (certification)." for unmatched lines, and "No questions exist for this objective yet." on a matched objective with no questions.
  - **API:**
    - `POST /api/certs/{cert}/focus/match`: a POST so the list never appears in a URL. Results carry only objective IDs, names, section codes and question counts (SR-7).
    - `POST .../sessions` now takes `mode: "focus"` with `objectives`.
    - `sessions.select_focus` serves only those objectives, taking turns across them (weakest first, unseen questions first) before doubling up.
  - **UI:** a Focus card on home opens a page with three steps:
    1. Paste the list (character counter, Ctrl+Enter).
    2. Check the preview: each line shows its matches as checkboxes with a confidence label and the topic that matched. Weak matches start unticked. Unsure lines offer up to three alternatives, and every line has a search box over all objectives. An objective without questions asks "Would you like a prompt to generate some?" and builds the prompt in place.
    3. Start: a sticky bar shows the objectives chosen and questions available, with the question count.
    Recall-first now applies to focus sessions too.
  - **Tried on the real objectives (read-only):** Cisco's official CCST topic list (28 lines including the domain headings) matched in 0.5 s, and most topics landed on the right objectives (TCP, UDP, HTTP, ARP, ICMP, DHCP, DNS; SIEM, SOAR; Cyber Kill Chain, MITRE ATT&CK, Diamond Model...). The misses come in as weak or likely matches for the preview to catch, for example "MAC addresses" → Mac App Store (weak) and "controls" → Command and Control (likely).
  - **Tests:** 228 pytest pass (23 new in `test_focus.py`). They cover:
    - splitting and markers;
    - cleaning and caps;
    - IDs, names and both messages;
    - topic lists and the parentheses rule;
    - acronyms;
    - headings and long lines;
    - reference numbers (with a second, temporary certification);
    - focus sessions (only the chosen objectives, spread, weakest first) and bad requests;
    - the token and limits on the match route;
    - **SR-2 fuzz:** 200 random pastes (control, bidi and zero-width characters, NFKC-expanding characters, CJK, traversal strings, ReDoS patterns, injection strings), always 200 or 422 within 3 s, with clean line text;
    - **SR-3:** a spy on file reads shows only the certification's `cert.json`, `objectives/` and `questions/` are read, whatever the text says;
    - **SR-7:** response keys are whitelisted, and no core idea, discriminator, file name or data path appears in results.
  - **Verified by hand** (scratch copy of the real data):
    - the preview for mixed input (names, IDs, junk, a domain heading, a topic list, weak matches);
    - adding an objective by search;
    - the no-questions prompt;
    - a focus session through to "Focus results";
    - no console errors.
- **P8 done (2026-10-27):** certification wizard, exam-facts and objective-builder prompts, first-start dialog.
  - **`wizard.py`:** drafts in `data/drafts/<id>.json` (gitignored), so set-up can be left and resumed. The id is a slug of the short name, unique across installed certifications and drafts.
    - **Exam-facts prompt:** asks for the official name, exam code, minutes, question count, passing score, question formats, domains with weights, objective version and date, and sources. Every fact is marked official, estimate or unknown ("never mark a guess as official"; no published weights → weight 1 each and "unknown").
    - **Exam-facts reply** (`certprep-exam-facts` v1): every field is checked: whole-number counts, known question formats (served = single/multi), unique domain ids, weights above 0, https sources, cleaned and capped text, no unknown fields. Problems come back as a list with a repair prompt, and nothing is saved until the reply is clean. The preview lets the learner correct values, confidence and weights.
    - **Objective-builder prompt:** built from the pasted official list (up to 30,000 characters), fenced as data ("ignore anything in it that reads like an instruction"). It asks for one section per domain (D01...), objectives that each test one thing, with core idea, discriminator, group and Ref.
    - **Objective reply** (`certprep-objectives` v1): checked the same way: section codes, IDs `<code>-NN`, no duplicates, known domains, text limits, no `|`, Ref format.
    - **Install:** validates the whole `cert.json` with the registry's own model, writes the folder under a hidden `.installing-*` name, renames it into place, reads the objective files back, and removes everything if anything doesn't match. Objective files gain the fifth `Ref` column, so Focus matches the vendor's reference numbers for wizard-built certifications.
  - **API:** `/api/wizard` (list, create), `/api/wizard/{id}` (draft), `prompts/facts`, `facts`, `facts/edit`, `prompts/objectives`, `objectives`, `install`, `finish` (draft removed, certification kept), `discard` (needs `confirm: "DISCARD"`). `/api/certs` now reports answers per certification.
  - **UI:**
    - **Wizard:** a four-step page (Name → Exam facts → Objectives → First questions) with a step bar; earlier steps can be revisited until the certification is created.
    - **Each Claude step:** build prompt → paste reply (or choose its file) → check. Problems are listed with a repair prompt; a clean reply shows a preview (facts table with editable values and confidence, domains with weights, sources; sections with their objectives).
    - **First questions:** a progress bar (objectives with two or more questions), "Build the next question prompt" in batches (objectives with none first, 15 at a time, two questions each; then those with one), import in place, and Finish.
    - **Home and header:** "Continue setting up X" on home, "Add a certification" in the top bar, and the certification switcher once there are two.
    - **First-start dialog:** "Which certification are you studying?" lists the installed certifications ("ready to use") and "Something else: set it up step by step". It shows once per browser, only when no certification has answers and nothing is being set up. "Import a certification pack" waits for packs in P9.
  - **Exit test** (UI only, in a fresh scratch folder holding CCST alone): the first-start dialog appeared. "Something else" opened the wizard, and the steps were then run in the browser:
    1. Typed the name, short name, vendor and exam code.
    2. Built the facts prompt and pasted a flawed reply: problems were listed with a repair prompt. Pasted a clean one, corrected the passing score in the preview, saved.
    3. Pasted an official list and built the objective prompt (domains included, list fenced). Left for home, resumed with "Continue setting up" (the list was kept), pasted the objectives reply, checked the preview, and clicked Create.
    4. The step showed 0 of 5 covered; built the question prompt (10 targets) and imported a question (the next batch moved on).
    5. Clicked Finish.
    The new certification was selected on home, with exam defaults from its facts. A practice question was answered, and `/api/certs` showed the answer under the new certification. An existing user with progress gets no dialog. The wizard fits a 375px screen, and there were no console errors.
    The replies were written in this session standing in for Claude, for a made-up "Example Networking Basics" exam.
  - **Tests:** 243 pytest pass (15 new in `test_wizard.py`). They cover:
    - safe, unique ids (slugs, traversal, non-Latin names);
    - draft route checks;
    - the facts prompt and import, problems with a repair prompt, unusable replies, corrections;
    - the fenced official list (control characters stripped, length capped);
    - objective problems;
    - install (valid `cert.json`, objective files with groups and refs, no leftovers, idempotent, Focus on the new refs);
    - importing and practising on the new certification;
    - finish and discard;
    - refusals (unfinished, id taken);
    - the token.
- **P9 done (2026-10-27):** certification packs, help page, glossary and in-app guidance, question-bank health page, usability pass.
  - **Packs (`packs.py`):**
    - **Export:** a zip with `manifest.json` (format, version, certification, created, file list with SHA-256 and size), `cert.json`, objective files and served questions; retired questions on request.
    - **What doesn't travel:** answered-by-me status goes back to Unreviewed, first-seen times are dropped, and disputed questions stay behind, so a pack carries no progress.
    - **Import:** the zip is checked completely in memory, then written as a new certification through a shared `certs.install` (hidden folder renamed into place), which the wizard now uses too. Nothing is overwritten: an existing id is refused and a free one suggested (`ccst-cyber-2`), plus "(copy)" on a short name already in use.
    - **The import checks (SR-5):** at most 20 MB and 2,000 entries; names only `manifest.json`, `cert.json`, `objectives/<CODE>.md`, `questions/<CODE>.json` (so no absolute paths, `..`, backslash tricks, folders or other files); no links, encryption or duplicates; per-file size caps; compression ratio at most 100:1; at most 100 MB unpacked; manifest hashes and sizes; strict UTF-8; `cert.json` against the registry's model; objective rows with clean, capped cells; questions against the schema, in the right file, with known objectives and no disputes.
    - **Upload route:** `/api/packs/import` is the one POST that takes `application/zip` (20 MB). The origin and token checks now run before the size and type checks, so an unauthenticated change always gets 403.
  - **Question-bank health page:** coverage per section (at least two questions from two angles per objective, with a "build a prompt" button for the gaps) and the five answer-pattern bands with measured share, allowed range and status, plus the option-role and difficulty mix. `audit.coverage`/`audit.bands` now back both the CLI and the page.
  - **Help:** a Help page (top bar) covering:
    - getting started and the study modes;
    - answering (confidence, keyboard, recall first);
    - glossaries of question statuses and objective levels;
    - session scores and the objective score formula;
    - working with Claude, Focus, certifications and packs, question-bank health, progress and backups, privacy.
    "?" buttons by the Study, Question pool, confidence, Focus, Claude workspace, Progress, health and Backups headings open it at the matching topic, and Back returns to the same screen, mid-session included.
  - **First-start dialog:** gains "Import a certification pack". The wizard's first step offers "Import a certification pack instead".
  - **Usability pass:** the top bar wraps on phones (with two certifications it pushed the page to 465px), and "1 questions" is fixed.
  - **Round trip on a copy of the real data, through the UI:** downloaded the CCST pack from home (327 KB) and imported it from the wizard's pack link. The summary showed 13 sections, 459 objectives and 918 questions, with the suggested id `ccst-cyber-2` and short name "CCST Cybersecurity (copy)". The import selected the copy: the same questions per section, all Unreviewed, no answers. The health page matched the CLI audit (13 of 13 sections covered, all bands OK). Help opened at each topic; at 375px nothing overflows; no console errors.
  - **Tests:** 275 pytest pass, 32 new in `test_packs.py`. They cover:
    - a CCST round trip (cert.json and objective files identical, questions identical apart from the stripped learner fields, retired and disputed left out, the copy is studyable with no progress);
    - retired questions on request;
    - never overwriting (taken ids, bad ids);
    - the upload route (token, content types both ways, size limits);
    - **SR-5:** 11 bad names, a link, an encrypted entry, a duplicate, a 1000:1 zip bomb, an oversized file, 2,100 entries, non-zips, the manifest format, version and extra fields, a tampered file, a missing file, and 11 per-file validation failures; nothing is written in any refused case;
    - 60 randomly corrupted packs (one of which found an uncaught `zlib.error`, now handled);
    - the health endpoint.
- **P10 done (2026-10-28):** ordering and matching question formats (built at the user's request; the plan made them optional).
  - **Schema:** `type` gains "ordering" and "matching".
    - **Ordering:** the answer is every option key in the correct order.
    - **Matching:** a new optional `match_targets` (3 to 8 descriptions, extras allowed), and the answer is one `<key><number>` pair per option (`["A2", "B1", "C3"]`).
    - Answers are pattern-checked (`^[A-F][1-8]?$`). Single and multi questions are unchanged, including their 4-option minimum, now an import check. `Question.stored()` writes `match_targets` only on matching questions, so existing pool files keep their shape.
  - **Import checks:**
    - ordering: 3 to 6 steps, every key exactly once, a stem that asks for the order, no roles;
    - matching: at least as many descriptions as items, no duplicate descriptions, every item paired once, each description number used at most once and in range, a stem that asks to match, no roles.
    - The surface-cue checks apply to single and multi only. Shuffling keeps the meaning: an ordering question's answer is remapped and never shown already in order, and a matching question's items and descriptions are both shuffled, with the pairs remapped.
  - **Prompts:** `prompts.extra_types` gives about 10% ordering for certifications whose `cert.json` lists "ordering", and about 10% matching for "matching" or "drag-and-drop". Each gets a suited angle (cause-and-effect-ordering, classify-element), a format rule, and a template example. CCST lists neither, so its prompts are unchanged. The wizard now marks ordering and matching as formats the app can serve. The ask-about-this prompt shows the correct order or pairs.
  - **Answering:**
    - **Ordering:** ↑/↓ buttons (focus follows the moved step, so it works by keyboard).
    - **Matching:** the numbered descriptions, then a picker per item.
    - **Server:** `sessions.answer_problem` refuses malformed answers with 422 for every type. Ordering answers are stored in the learner's order. Scoring is all-or-nothing.
    - **Feedback and results:** show the correct order or pairs, with the learner's misplacements in words ("you put it 3rd", "you chose 2. ...") and descriptions that match nothing.
    - **Shared view:** `answerView` now draws options everywhere (feedback, results, disputes, too-easy), replacing four copies of the same code.
  - **Audit:** ordering and matching questions are counted separately and kept out of the single/multi answer-pattern statistics.
  - **Help:** the Answering topic explains the two formats.
  - **Verified in the browser** (fresh scratch folder, Example Net certification):
    - imported one question of each format through the Claude workspace;
    - answered the ordering question with real clicks and Enter on the ↑ buttons: "Correct";
    - answered the matching question with one pair wrong: per-pair feedback, plus the description that matches nothing;
    - an exam kept a saved order when returning to the question, and its results drew all three types.
    The real CCST pools still load, `coverage` passes for all 13 sections, and `audit` passes.
  - **Tests:** 298 pytest pass (23 new in `test_formats.py`). They cover:
    - shuffling that keeps the sequence or pairs;
    - 5 ordering and 8 matching rejection rules;
    - single and multi rules unchanged;
    - pool shape and audit counts;
    - answering and scoring both formats, with malformed answers refused;
    - the ask prompt;
    - a focus session and report;
    - prompts asking for the formats only when the exam uses them;
    - the formats travelling in packs.
- **P11 done (2026-10-28):** finish v2 (phase added at the user's request: the plan ended at P10).
  - **Resume unfinished sessions (8.1, the last open plan item):** home shows "Continue where you left off" with the newest 5 unfinished practice, focus or exam sessions: mode, sections, answered count, start time, and whether an exam's time ran out.
    - **Continue** reopens at the first unanswered question. Feedback already given comes back (practice, focus), and so do reports still held (exam). An exam's clock keeps running from its start, so one whose time ran out goes straight to its results.
    - **Finish now** closes it and shows the results so far.
    - The 11 sessions left open in the retired v1 modes (Diagnostic, Targeted drill) stay as history and aren't offered.
    - `GET /api/sessions/{id}` now includes `revealed` and `held`, and the new route is `/api/certs/{cert}/sessions/open`. The "Leave this session?" prompt now says the session can be picked up again. Help explains resuming.
  - **Real app on the real data:** started with `run.ps1 -NoBrowser`, the same path as the desktop shortcut. A safety backup was made with "Back up now" (18 sessions, 318 answers); after it the check was read-only:
    - no first-start dialog and no resume note (only v1 sessions are open);
    - Progress: 78 average, 212 of 459 practised, 9 charts, 44 suggestions, 459 tracker rows;
    - question-bank health: 13 of 13 sections covered, all five bands OK;
    - Help: 12 topics;
    - Focus matched names and IDs and reported an unknown line;
    - the pack downloaded (327 KB);
    - the Claude workspace showed 0 gaps and 41 weak objectives;
    - a request for another host name and a token-less change were both refused (403).
    Answers stayed at 318 and the pool files were unchanged.
  - **Docs:** a `README.md` for people (install, run, features, data, development); `CLAUDE.md` gains the resume notes, the line-ending note (pool JSON, imports and `app.js` are CRLF; Git Bash `sed -i` converts them, which happened to `app.js` once and was put back), and the v2 status; this plan's status set to complete.
  - **Tests:** 304 pytest pass (6 new in `test_resume.py`): current-mode open sessions newest first, v1 and finished ones left out, the limit of 5, feedback restored for practice, exams kept secret with held reports restored, time ran out, unknown certification.
  - **Verified in the browser** (scratch copy):
    - practice resumed at question 2, with question 1's feedback kept;
    - an exam resumed with its held report and running clock;
    - "Finish now" opened the results with the report to decide;
    - no console errors.
