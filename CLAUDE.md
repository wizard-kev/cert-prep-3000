# CCST Cybersecurity Exam Prep

Local web app that generates CCST (100-160) practice questions from per-chapter objective files using a local Ollama model (Claude API is Phase 2), stores them in a reviewed pool, and serves drills.

Read `Project Documents/CCST_Project_Scope_and_Plan.md` before changing scope, schema, or phases. `Project Documents/CCST_Project_Instructions.md` holds the tutoring rules; `Project Documents/CCST_Official_Blueprint.md` holds Cisco's official topics.

## Map
- `Objective Documents/CCST_ChXX.md` (01-13): source of truth. Objective IDs `Cxx-yy` are frozen: never rename, retire instead.
- `src/ccst/objectives.py`: chapter allowlist (int 1-13) and table parser.
- `src/ccst/schema.py`: question schema (plan 8.3) and the JSON schema sent to the model.
- `src/ccst/generator.py`: target planning (coverage + angle rotation), prompt, automated checks (plan 10.2), option shuffle.
- `src/ccst/providers/`: provider interface; `ollama.py` live, `claude.py` stub.
- `src/ccst/pool.py`: `data/questions/chNN.json`, atomic writes; verify / retire.
- `src/ccst/tracker.py`: SQLite sessions and attempts (`data/tracker.db`); objective status derived from attempts (plan 8.4).
- `src/ccst/sessions.py`: question selection per mode, exam domain allocation, reports, export summary.
- `src/ccst/main.py`: FastAPI routes; `static/`: UI (home, session, report, draft review queue, tracker).
- `tests/`: pytest; `conftest.py` points `CCST_DATA_DIR` at a temp dir, so tests never touch real data.
- UI testing: run a second instance with `CCST_DATA_DIR` set to a scratch copy of `data/`, never the real tracker.

## Commands
- Install / repair (Phase 5): `install\install.cmd` (idempotent; `-Bundle <dir>`, `-Model`, `-Port`, `-StopNativeOllama`, `-NonInteractive`, `-NoBrowser`). Uninstall: `install\uninstall.cmd` (keeps `data\tracker.db` unless `-RemoveProgress`). Offline bundle: `install\make-bundle.ps1 -Out <empty dir>`.
- Docker directly: `docker compose up -d`, then http://127.0.0.1:8000. Optional manual model pull: `docker compose --profile pull run --rm ollama-pull`.
- Installer model-choice test: `powershell -ExecutionPolicy Bypass -File tests\test_install_select_model.ps1`
- Run app without Docker: `.\run.ps1` (http://127.0.0.1:8000); first install `pip install -r requirements-dev.txt` into `.venv`
- Generate from CLI: `.\.venv\Scripts\python.exe -m ccst.cli generate --chapter 1 --count 5` (run from `src` or set `PYTHONPATH=src`)
- Import authored questions: `... -m ccst.cli import --chapter 1 --file data\authored\ch01_claude.json --model <model-id> [--dry-run]`
- Tests: `.\.venv\Scripts\python.exe -m pytest -q`

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
