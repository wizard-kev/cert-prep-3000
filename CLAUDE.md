# Kevin's Super Cert Prep 3000

Local web app for certification exam practice. Each certification has objective files, a reviewed question pool built against them, and exam facts (`cert.json`); CCST Cybersecurity (100-160) ships pre-built. Questions are written with Claude (in a chat or a Claude Code session) and imported; the app runs no AI model and makes no network calls.

**v2 in progress:** `Project Documents/v2_Scope_and_Plan.md` is the governing plan; read it before changing anything and follow its phase order (its section 15 logs what has landed). `Project Documents/CCST_Project_Scope_and_Plan.md` is the v1 (CCST-only) history and CCST content decisions; `CCST_Project_Instructions.md` holds the tutoring rules; `CCST_Official_Blueprint.md` holds Cisco's official topics.

## Map
- `data/certs/<cert-id>/`: one folder per certification (id matches `^[a-z0-9][a-z0-9-]{1,31}$`).
  - `cert.json`: name, exam facts with confidence labels (minutes, question count, passing score, formats), domains and weights, sections (code, name, domain). Validated by `certs.Cert` (unknown fields rejected).
  - `objectives/<CODE>.md`: one objective table per section (codes like `C01`, `^[A-Z]{1,3}\d{2}$`). Objective IDs `<CODE>-NN` are frozen within a certification: never rename, retire instead.
  - `questions/<CODE>.json`: the section's pool; question IDs `Q-<CODE>-NNNN`.
  - `imports/`: archived question files that were imported (CCST's authored sets live here).
- `data/progress.db`: sessions and attempts for every certification (gitignored). `data/backups/`: automatic backups (gitignored); the v1 `tracker.db` was moved here when it was migrated (2026-10-27).
- `src/certprep/certs.py`: certification registry; ids and section codes are pattern-checked and must exist on disk before they touch a path.
- `src/certprep/objectives.py`: section objective files and table parser.
- `src/certprep/schema.py`: question schema (plan 8.3).
- `src/certprep/generator.py`: question import, automated checks (plan 10.2) and surface-cue checks, option shuffle; `targets_for` assigns each chosen objective the angles it has used least (retired questions count, so a replacement takes a new approach).
- `src/certprep/prompts.py`: prompts for a Claude chat (questions, repair, study session, ask about a question); `RULES` mirrors the import checks, `PROMPT_ANGLES` the angles offered. Reply format `certprep-questions` version 1.
- `src/certprep/importer.py`: imports a pasted reply: envelope and field checks (unknown fields rejected), `clean_text` on every text field, per-question checks via `generator.import_items`, a dry run of the full checks on early rejects, a repair prompt for anything rejected, and an archive copy in the certification's `imports/` (`claude-<time>-<hash>.json`).
- `src/certprep/pool.py`: per-section pools, atomic writes; verify / retire.
- `src/certprep/tracker.py`: `progress.db` (schema version in `meta`), v1 migration, `backup(reason)` (keeps 10 per reason); objective status derived from attempts (plan 8.4).
- `src/certprep/sessions.py`: selection per mode, exam allocation by `cert.json` weights, reports, export summary.
- `src/certprep/main.py`: FastAPI routes (`/api/certs/{cert}/...`; sessions at `/api/sessions/{id}`); `/` serves `static/index.html` with this launch's CSRF token filled in; `static/`: UI.
- `src/certprep/security.py`: middleware run before every route (Host allowlist; Origin + CSRF token on POST; JSON-only, 1 MB body cap; CSP and other headers on every response) and `clean_text` for any free text from the user.
- `src/certprep/launch.py`: starts the app on 127.0.0.1 (`CERTPREP_PORT`, default 8000) and opens the browser; reuses a running instance.
- `tests/`: pytest; `conftest.py` points `CERTPREP_DATA_DIR` at a temp dir holding a copy of the CCST `cert.json` and objectives with empty pools, so tests never touch real data.
- UI testing: run the `certprep-uitest` launch config, whose `CERTPREP_DATA_DIR` points at a scratch copy of `data/` (certs plus a copy of `progress.db`), never the real progress.

## Commands
- Install / repair: `install\install.cmd` (idempotent: finds Python 3.12+, builds `.venv` from `requirements.txt`, removes obsolete model settings and renames `CCST_*` settings in `.env`, adds desktop and Start-menu shortcuts, starts the app; `-Port`, `-NoShortcuts`, `-NoStart`). Uninstall: `install\uninstall.cmd` (stops the app, removes shortcuts and `.venv`; keeps progress and certifications unless `-RemoveProgress`).
- Run: `.\run.ps1` or the desktop shortcut (http://127.0.0.1:8000; `-NoBrowser`). Development: `pip install -r requirements-dev.txt` into `.venv`; the `certprep-dev` launch config runs uvicorn with reload on port 8001 against the real data.
- CLI (set `PYTHONPATH=src`; `--cert` defaults to the only installed certification):
  - Import authored questions: `.\.venv\Scripts\python.exe -m certprep.cli import --section C01 --file <file.json> --model <model-id> [--dry-run]`
  - `coverage [--sections C01 C02]`, `audit [--sections ...]`, `retire --section C01 --reason "..." (--ids ... | --all-active) [--superseded]`
- Tests: `.\.venv\Scripts\python.exe -m pytest -q`; installer library: `powershell -ExecutionPolicy Bypass -File tests\test_install_lib.ps1`

## Version control (git, since 2026-10-27)
- Branch `main`. Tag `v1` = the CCST-only app before the v2 revision, identical to `C:\Claude\CCST Snapshots\CCST_v1_snapshot_2026-10-27.zip` apart from untracked files. Back to it: `git switch --detach v1` (its progress file is the `tracker-v1-*.db` in `data/backups`, renamed back to `data/tracker.db`).
- Not tracked (`.gitignore`): `.env`, `.venv`, caches, `install/install.log`, `data/*.db` (progress), `data/backups/`. Back up progress separately before risky changes (`tracker.backup("manual")`).
- `.gitattributes` sets `* -text` so files are stored byte-exact (pool JSON is CRLF, the rest LF). Don't add line-ending normalization.
- Commit one logical change at a time; never commit progress databases or `.env`.

## Adding questions
- **In the app (the normal way, v2 P4):** home page > "Open the Claude workspace": choose objectives (quick picks: fewer than 2 questions, weak), build the question prompt, paste it into claude.ai, paste the reply back under "Import". Rejected questions come back with reasons and a repair prompt. The rules Claude is given are `prompts.RULES`; keep them in step with the checks in `generator.py`.
- **By hand or in a Claude Code session:** write `{"questions": [...]}` files using the GeneratedQuestion fields (CCST's are in `data/certs/ccst-cyber/imports/`, e.g. `ch01_v2_set1a.json`) and use the CLI import. The rules below apply either way.

## Authoring rules (v2 format since 2026-10-21)
- One question per objective as primary (`objectives[0]`); add look-alike IDs as secondary. Two sets, a different angle per objective in each.
- Every option has a `role`: `best` (keyed answer), `partial` (technically correct, not best), `related` (neighbouring concept/protocol/practice), `wrong` (plausible misconception). Use one of each where it fits. A `partial` option requires a BEST/FIRST/MOST qualifier in the stem.
- No surface cues: options of similar length and form; no absolutes (always, never, only, all, every...) in wrong options unless the answer has one too; the answer must not repeat the stem's wording; no joke options. The import rejects violations.
- Spread answer lengths across the pool: the answer should be the longest option about a quarter of the time and the shortest about a quarter (`audit` enforces bands).
- Describe situations instead of naming the concept in the stem; avoid "which is NOT". Use `exhibit` (log, config, command output, max 30 lines) where it fits.
- About 20-25% multi-select (5 options, 2 answers, stem ends "(Choose two.)"). Difficulty: 1 recall in context, 2 apply to a scenario, 3 best-of-valid or two-step.
- Name the objective's key term somewhere in the question (the explanation counts).
- Don't refer to option letters in rationales or the explanation; options are shuffled.
- Use only the section's own objective IDs, at most 3 per question. Never use specific-looking CVE IDs.
- Run `--dry-run` before importing; after importing run `coverage --sections <CODE>` and `audit --sections <CODE>` (both must pass).
- Replacing a pool: `python -m certprep.cli retire --section <CODE> --all-active --superseded --reason "..."`, then import. `--superseded` keeps the learner's answers counting; without it (reported or flawed questions) their answers are dropped from objective status.
- Reported questions are retired by the app; check `coverage` (or the workspace's "Fewer than 2 questions" pick) and write replacements on a different angle (the prompt builder does this automatically). Q-C09-0100 (reported 2026-10-22) was replaced by Q-C09-0154 through the in-app flow on 2026-10-27.

## Rules
- The browser sends only certification ids, section codes, question and session IDs, option keys, fixed choices, and short notes; ids are pattern-checked and must exist in the registry. Never put user text into prompts (SR6).
- Security baseline (v2 SR-1 to SR-4, `security.py`): every new route is covered by the middleware automatically; any new free-text field goes through `security.clean_text` with a length cap; never use user text in paths, SQL strings, regexes, or shell. Tests and API clients must send `Host: 127.0.0.1`/`localhost`, plus `Origin` and `X-CSRF-Token` on POSTs (see the test fixtures).
- Treat model output as untrusted: validate, and render with `textContent` only (SR7). The CSP forbids inline scripts, inline styles, and `eval`; `tests/test_security.py` fails if the UI builds HTML from strings.
- Imported questions enter the pool as `draft`; exam simulation uses `verified` only (D7, until v2 P5 changes it). Retire, never edit in place.
- Never use real exam questions (brain dumps).
- No API keys in code or the browser; `.env` is gitignored.
