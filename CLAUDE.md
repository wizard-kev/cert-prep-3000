# CCST Cybersecurity Exam Prep

Local web app that serves CCST (100-160) practice questions from a reviewed pool built against per-chapter objective files. Questions are written with Claude (in a chat or a Claude Code session) and imported; the app runs no AI model and makes no network calls (v2 P1).

**v2 in progress (2026-10-27):** the app is being generalized into *Kevin's Super Cert Prep 3000* (any certification, prompts for Claude web chat instead of a local model, no Docker). `Project Documents/v2_Scope_and_Plan.md` is the governing plan; read it before changing anything and follow its phase order. Until a phase lands, the sections below describe the v1 app as it still exists in the code.

Read `Project Documents/CCST_Project_Scope_and_Plan.md` for the v1 history and CCST content decisions. `Project Documents/CCST_Project_Instructions.md` holds the tutoring rules; `Project Documents/CCST_Official_Blueprint.md` holds Cisco's official topics.

## Map
- `Objective Documents/CCST_ChXX.md` (01-13): source of truth. Objective IDs `Cxx-yy` are frozen: never rename, retire instead.
- `src/ccst/objectives.py`: chapter allowlist (int 1-13) and table parser.
- `src/ccst/schema.py`: question schema (plan 8.3).
- `src/ccst/generator.py`: question import, automated checks (plan 10.2) and surface-cue checks, option shuffle; `plan_targets` (coverage + angle rotation) for the v2 prompt builder.
- `src/ccst/launch.py`: starts the app on 127.0.0.1 (`CCST_PORT`, default 8000) and opens the browser; reuses a running instance.
- `src/ccst/pool.py`: `data/questions/chNN.json`, atomic writes; verify / retire.
- `src/ccst/tracker.py`: SQLite sessions and attempts (`data/tracker.db`); objective status derived from attempts (plan 8.4).
- `src/ccst/sessions.py`: question selection per mode, exam domain allocation, reports, export summary.
- `src/ccst/main.py`: FastAPI routes; `static/`: UI (home, session, report, draft review queue, tracker).
- `tests/`: pytest; `conftest.py` points `CCST_DATA_DIR` at a temp dir, so tests never touch real data.
- UI testing: run a second instance with `CCST_DATA_DIR` set to a scratch copy of `data/`, never the real tracker.

## Commands
- Install / repair: `install\install.cmd` (idempotent: finds Python 3.12+, builds `.venv` from `requirements.txt`, removes obsolete model settings from `.env`, adds desktop and Start-menu shortcuts, starts the app; `-Port`, `-NoShortcuts`, `-NoStart`). Uninstall: `install\uninstall.cmd` (stops the app, removes shortcuts and `.venv`; keeps `data\tracker.db` unless `-RemoveProgress`).
- Run: `.\run.ps1` or the desktop shortcut (http://127.0.0.1:8000; `-NoBrowser`). Development: `pip install -r requirements-dev.txt` into `.venv`; the `ccst-dev` launch config runs uvicorn with reload on port 8001 against the real data.
- Installer library tests: `powershell -ExecutionPolicy Bypass -File tests\test_install_lib.ps1`
- Import authored questions: `.\.venv\Scripts\python.exe -m ccst.cli import --chapter 1 --file data\authored\ch01_claude.json --model <model-id> [--dry-run]` (run from `src` or set `PYTHONPATH=src`)
- Tests: `.\.venv\Scripts\python.exe -m pytest -q`

## Version control (git, since 2026-10-27)
- Branch `main`. Tag `v1` = the app before the v2 scope revision, identical to `C:\Claude\CCST Snapshots\CCST_v1_snapshot_2026-10-27.zip` apart from the untracked files below. Back to it: `git switch --detach v1` (or `git switch -c v1-restore v1`).
- Not tracked (`.gitignore`): `.env`, `.venv`, caches, `install/install.log`, and `data/tracker.db` (the learner's answer history). The v1 copy of `tracker.db` lives only in the snapshot zip; back it up separately before risky changes.
- `.gitattributes` sets `* -text` so files are stored byte-exact (pool JSON is CRLF, the rest LF). Don't add line-ending normalization.
- Commit one logical change at a time; never commit `data/tracker.db` or `.env`.

## Authoring a chapter pool (current generation source, plan D1 amended; v2 format since 2026-10-21)
Write `data/authored/chNN_v2_set1a.json` etc. as `{"questions": [...]}` using the GeneratedQuestion fields. Rules:
- One question per objective as primary (`objectives[0]`); add look-alike IDs as secondary. Two sets, a different angle per objective in each.
- Every option has a `role`: `best` (keyed answer), `partial` (technically correct, not best), `related` (neighbouring concept/protocol/practice), `wrong` (plausible misconception). Use one of each where it fits. A `partial` option requires a BEST/FIRST/MOST qualifier in the stem.
- No surface cues: options of similar length and form; no absolutes (always, never, only, all, every...) in wrong options unless the answer has one too; the answer must not repeat the stem's wording; no joke options. The import rejects violations.
- Spread answer lengths across the pool: the answer should be the longest option about a quarter of the time and the shortest about a quarter (`audit` enforces bands).
- Describe situations instead of naming the concept in the stem; avoid "which is NOT". Use `exhibit` (log, config, command output, max 30 lines) where it fits.
- About 20-25% multi-select (5 options, 2 answers, stem ends "(Choose two.)"). Difficulty: 1 recall in context, 2 apply to a scenario, 3 best-of-valid or two-step.
- Name the objective's key term somewhere in the question (the explanation counts).
- Don't refer to option letters in rationales or the explanation; options are shuffled.
- Use only the chapter's own objective IDs, at most 3 per question. Never use specific-looking CVE IDs.
- Run `--dry-run` before importing; after importing run `coverage --chapters N` and `audit --chapters N` (both must pass).
- Replacing a pool: `python -m ccst.cli retire --chapter N --all-active --superseded --reason "..."`, then import. `--superseded` keeps the learner's answers counting; without it (reported or flawed questions) their answers are dropped from objective status.
- Reported questions are retired by the app; check `coverage` and write replacements (`chNN_v2_fixN.json`) on a different angle from the surviving partner.

## Rules
- Browser sends only chapter numbers, question IDs, option keys. Never put user text into prompts (SR6).
- Treat model output as untrusted: validate, and render with `textContent` only (SR7).
- Generated questions enter the pool as `draft`; exam simulation uses `verified` only (D7). Retire, never edit in place.
- Never use real exam questions (brain dumps).
- No API keys in code or the browser; `.env` is gitignored.
