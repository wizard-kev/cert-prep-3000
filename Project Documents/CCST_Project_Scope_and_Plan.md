# CCST Cybersecurity (100-160) Exam Prep: Project Scope and Plan

> **Superseded for new work (2026-10-27):** the app is being generalized into *Kevin's Super Cert Prep 3000*. See `v2_Scope_and_Plan.md`, which overrides this plan wherever they differ. This document remains the record of the CCST build (git tag `v1`).

**Purpose of this document:** master scope and plan for the CCST Cybersecurity exam-prep platform. It captures goals, decisions, current status, the app specification, security requirements, and the build plan, so work can continue without the original conversations. Read it fully before building anything.

**Doc version:** v2 (2026-10-07) | **Supersedes:** v1 (free-tier planning conversation)
**v2 change summary:** delivery moved from a published artifact to a local, Dockerized web app; questions are now generated at runtime by an AI provider (Claude API or local Ollama) and stored in a reviewed question pool; security, cost, hardware, and deployment requirements added; build plan merged.

**Tags used:** **[DECISION]** settled; **[OPEN]** needs an answer before the related phase starts; **[VERIFY]** fact must be checked before relying on it.

---

## 1. Goal
Prepare the user to pass the **Cisco Certified Support Technician (CCST) Cybersecurity exam (100-160)** using a realistic, targeted testing environment that:
- tests *discriminators* (the one fact separating look-alike concepts), not bare definitions
- tracks which objectives the user struggles with and drills them
- avoids repetitive question patterns and tests underlying theory
- is token-efficient and stays accurate to the real exam objectives

## 2. Project summary
A certification exam simulation platform. A local web app (HTTP session) generates practice questions at runtime by sending the authoritative, chapter-sorted objective documents to an AI model, stores them in a question pool, and serves them to the user as quizzes and timed simulations. The app runs in Docker containers and is designed to be deployed to multiple machines with a simple, automated installer.

## 3. Exam facts: verified vs unverified
**Seen on multiple training-provider pages (not yet confirmed on a primary Cisco page):**
- Exam code 100-160; 50 minutes
- Five domains: 1.0 Essential Security Principles, 2.0 Basic Network Security Concepts, 3.0 Endpoint Security Concepts, 4.0 Vulnerability Assessment and Risk Management, 5.0 Incident Handling

**Phase 0 result (2026-10-07):**
- **Confirmed on Cisco primary pages** (exam page and Learning Network topics page): exam code 100-160; 50 minutes; USD 125; the five domains above; official sub-objectives 1.1 to 5.4, saved in `CCST_Official_Blueprint.md`.
- **Cisco states** that the exam uses performance-based (lab-style) items and that "the number of questions on your exam may vary."
- **Not published by Cisco:** domain weight percentages, question count, passing score, and an itemized list of question types. Third-party sites give conflicting or unsupported figures (about 35 to 50 questions; "70%" or a 750 to 850 scaled score). A search-engine summary quoted weights of 22% and 20% for Domains 1 and 2, but it echoed numbers I had typed into the query, so treat it as **unverified and do not use**.
- **[DECISION]** Until Cisco publishes weights, exam simulation uses a user-adjustable weighting (default: proportional to the number of official sub-objectives per domain: 4, 5, 6, 4, 4 of 23) and the timer defaults to 50 minutes. The app must label these as estimates. The Phase 7 exit criterion "follows real domain weights" is changed to "follows the official domain and sub-objective structure."
- **Question types:** official list unavailable. Build `single` and `multi` first; keep `ordering` and `matching` in the schema as likely lab-style analogues. Check the Pearson VUE exam tutorial (section 17, item 10) for the interface.

## 4. Study material
**Sybex CCST Cybersecurity Exam Study Guide**, 13 chapters: 1 Security Concepts; 2 Network Security Devices; 3 IP, IPv6, and NAT; 4 Network Device Access; 5 Secure Access Technology; 6 OS Basics and Security; 7 Endpoint Security; 8 Risk Management; 9 Vulnerability Management; 10 Disaster Recovery; 11 Incident Handling; 12 Digital Forensics; 13 Incident Response.
Chapters do not map one-to-one to the five exam domains, so every objective carries both a chapter number and a provisional domain tag, and a crosswalk (chapter, domain, objective IDs) is required.

## 5. Current status
| Item | Status |
|---|---|
| Objective files Ch1 to Ch13 (`Objective Documents/CCST_Ch01.md` ... `CCST_Ch13.md`) | All 13 present. Ch1 v2 (C01-01 to C01-48), Ch2 v2 (C02-01 to C02-44), Ch3 v1 (C03-01 to C03-39); Ch4 to Ch13 counts not yet recorded here |
| File naming | Done (2026-10-07): `CCST_Ch6.md` renamed to `CCST_Ch06.md`; all objective files now follow `CCST_ChXX.md` (XX = 01 to 13), so the chapter-ID allowlist is uniform (see 7.1) |
| Phase 0 (blueprint verification) | Done 2026-10-07; official topics saved in `CCST_Official_Blueprint.md`; weights, count, passing score not published (see section 3) |
| Official-blueprint crosswalk | Not started (Phase 7); official sub-objectives now available as input |
| App, question pool, tracker, installer, flashcards | Not started |

Objective files are the source of truth. Domain tags in them are provisional.

## 6. Decisions (do not relitigate without reason)

### 6.1 Content decisions (carried from v1)
1. Objective IDs are `Cxx-yy` (chapter, sequence). **IDs are frozen:** never rename, retire instead. Every question links back to an objective ID.
2. One objective file per chapter, for token optimization. Each row: ID, Objective, Core idea, Discriminator.
3. Questions test discriminators and application, with rotating angles (see section 11).
4. Ch1: ransomware kept as a single objective. Tailgating and piggybacking are **distinct** (tailgating = without the authorized person's knowledge/consent; piggybacking = with their knowledge/consent). User-approved Ch1 additions beyond their list: virus, spyware, keylogger, rootkit, adware, malvertising, whaling.
5. Ch2: "Inference" in the user's list was a typo for **Interference**. Section E (firewalls, stateless/stateful/NGFW, host vs network firewall, IDS, IPS, signature vs anomaly detection, proxy/web filter) was **added by the user's approval** and was not in the book list.
6. Ch3: "IPv4 Hierarchical Addressing Structure" and "IPv4 Network Addressing" merged into C03-22. Class E not included (not in the user's list).
7. All questions are original. Never use recalled real exam questions ("brain dumps"); this violates the Cisco certification exam agreement and can lead to revocation of certification and bans from future exams.
8. Flashcards (Anki CSV) cover pure recall facts. Chat is used for explanation, remediation, and scenario reasoning.

### 6.2 Platform decisions (new in v2)
| ID | Decision | Rationale |
|---|---|---|
| D1 | **[DECISION]** Questions are generated at runtime by an AI model, not hand-written. | User's choice. |
| D2 | **[DECISION]** No RAG / vector database. The backend loads the objective file for the requested chapter directly. | Chapter-sorted files make retrieval a simple lookup. |
| D3 | **[DECISION]** The AI provider sits behind a single abstraction (e.g. `generate_questions(chapter, n)`) with a config setting to choose **Claude API** or **local Ollama**. | Free local development/testing; Claude for higher-quality questions; side-by-side quality comparison. |
| D4 | **[DECISION]** The app runs locally in Docker (Docker Compose: `app` + `ollama` services). Replaces v1's published-artifact delivery. | Local control, multi-machine deployment. |
| D5 | **[DECISION]** Deployment to other machines uses an automated, idempotent installer. | Repeatable installs. |
| D6 | **[DECISION]** Generated questions are stored and reused in a **question pool**; the model is called only when a chapter's pool runs low. | Cuts cost and latency; allows quality review. |
| D7 | **[DECISION]** Generated questions enter the pool as `draft`. They become `verified` only after passing automated checks (section 10.2) and user spot-checks. Exam simulation draws from `verified` questions only; drills may use `draft` questions, labelled as such. | Keeps v1's verification standard under runtime generation. |

## 7. Architecture

### 7.1 Components
1. **Source of truth:** per-chapter objective files (`/docs/objectives/`), static.
2. **Backend:** loads the objective file for an allowlisted chapter ID, builds the prompt, calls the selected provider, validates output, writes to the question pool, serves quizzes, records results.
3. **Providers:** Claude API or Ollama, behind one interface (D3).
4. **Question pool:** JSON, one file per chapter (`/data/questions/`).
5. **Frontend:** browser UI on `127.0.0.1`; sends only chapter IDs and answers, never free text used in prompts.
6. **State (tracker):** stored locally by the backend. **[OPEN]** storage choice (e.g. SQLite file or JSON in a mounted volume); must survive container rebuilds.
7. **Practice engines:** (a) the local app; (b) Anki flashcard CSVs generated from objective files; (c) chat sessions for teaching and review, which load only a short weak-objectives summary refreshed from the app's export.
8. **External calibration (user to check):** the Sybex book's online test bank if included, Cisco's official practice material, Pearson VUE exam tutorial, Packet Tracer labs for network objectives. Not verified; user to confirm what exists.

### 7.2 Target folder structure
```
/docs/project/        # scope, plan, decisions, instructions (currently "Project Documents")
/docs/objectives/     # one .md per chapter, CCST_Ch01.md to CCST_Ch13.md (currently "Objective Documents")
/data/questions/      # generated question pool, JSON, one file per chapter
/src/                 # application code
/install/             # install.ps1, install.sh, uninstall scripts
docker-compose.yml
CLAUDE.md             # map of the repo + rules for question generation (keep < 200 lines)
.env.example          # documented config keys, no real secrets
.gitignore            # must include .env before first commit
```

## 8. App specification

### 8.1 Functional requirements
- **FR1** The user selects a chapter. The browser sends **only a chapter ID**, never free text, to the backend.
- **FR2** The backend validates the chapter ID against an allowlist (Ch01 to Ch13) before loading `/docs/objectives/CCST_ChXX.md`.
- **FR3** Questions are generated in **batches** (e.g. 10 per call), not one per call.
- **FR4** Every question uses the schema in 8.3.
- **FR5** Results can be broken down by objective ID, so scores are reported per objective and per domain.
- **FR6** A **"Report this question"** button removes the flagged question from the pool (status `retired`, reason recorded).
- **FR7** An "Explain this" action in Review mode calls the selected provider with the question ID (not free text) and returns an explanation grounded in the objective file.

### 8.2 Modes
- **Exam simulation:** blueprint-weighted selection from `verified` questions, countdown timer (default 50 min, **[VERIFY]**), flag for review, question navigator, no per-question feedback until the end, score report by domain and objective.
- **Targeted drill:** weighted toward Weak objectives with spaced revisits of Solid ones; immediate feedback with rationale.
- **Review:** replay misses; "Explain this" (FR7).
- **Diagnostic:** broad sweep (about one question per objective) to seed the tracker.

### 8.3 Question schema
```json
{
  "id": "Q-C01-0001",
  "chapter": 1,
  "objectives": ["C01-10"],
  "domain": "1.0",
  "type": "single | multi | ordering | matching",
  "angle": "symptom-to-attack",
  "difficulty": 1,
  "stem": "...",
  "exhibit": "optional log / config / command output (max 30 lines, monospace)",
  "options": [{"key": "A", "text": "...", "rationale": "why right or wrong", "role": "best | partial | related | wrong"}],
  "answer": ["B"],
  "explanation": "...",
  "discriminator_tested": "...",
  "source_ref": "CCST_Ch01.md#C01-10",
  "provider": "claude | ollama",
  "model": "...",
  "status": "draft | verified | retired"
}
```
- `objectives[0]` is the primary objective used for per-objective scoring.
- Multi-select stems must say how many to choose. Question types should match what the real exam uses once verified.
- **Option roles (v2, 2026-10-21):** `best` = keyed answer; `partial` = technically correct but not the best answer the stem asks for (requires a BEST/FIRST/MOST qualifier); `related` = neighbouring topic, protocol, standard, or practice; `wrong` = plausible misconception. Roles are shown to the learner only after answering. `difficulty`: 1 recall in context, 2 apply to a scenario, 3 best-of-valid or two-step reasoning.

### 8.4 Tracker model (per objective)
Attempts, correct, last-five results, confidence calibration, error-type counts, last seen, sessions in which answered correctly, angles seen, status.
- **Confidence rating** (Guess / Unsure / Sure) before each answer. "Sure but wrong" is the highest-priority signal.
- **Error types:** concept gap, terminology confusion, misread question, scenario application.
- **Status (proposed, tunable):** New (no attempts); Weak (under 60% over last five, or any Sure-but-wrong); Improving; Solid (3 correct across at least 2 sessions and at least 2 angles, last-five at or above 80%).
- **Guesses (2026-10-21):** a correct answer marked Guess still scores in the session, but counts as a miss for mastery (last five, Solid evidence) and shows as "?" in the tracker. Calibration records what actually happened.
- **Too-easy flag (2026-10-21):** a question answered correctly and Sure in each of its last 3 sessions is listed on the tracker page to keep or retire ("Guessable / too easy" report reason).
- **Recall-first mode (2026-10-21):** optional, all modes except exam: the stem shows first and the options stay hidden until the learner commits an answer (typed note stays in the browser, never sent).
- **Spaced revisit (proposed):** Solid objectives resurface after about 3, 7, then 14 days.

### 8.5 Export summary (for pasting into chat)
Compact text: date, session type, overall score, per-domain %, top weak IDs with dominant error type, newly Solid IDs, recommended next focus. Chat updates its short weak list from this.

### 8.6 UX
Mobile-friendly, keyboard accessible, dark/light aware, clear indicator of active provider (Claude / Ollama) and of whether a question is `draft` or `verified`, reset option.

## 9. Security requirements

### 9.1 API key and cost (Claude mode)
- **SR1** The API key lives only in the backend and is loaded from an environment variable. It is never sent to the browser.
- **SR2** `.env` is listed in `.gitignore` before the first commit, and GitHub secret scanning is turned on.
- **SR3** A workspace spend limit is set in the Claude Console before any code calls the API.
- **SR4** The installer never includes an API key. Deployed installs **default to local-only (Ollama) mode** and ask for a key only if the person installing explicitly chooses Claude mode.
- **SR5** Rate limiting on the generation endpoint, to prevent "denial of wallet."

### 9.2 Prompt and output handling
- **SR6** No user-supplied text is put into prompts (prevents prompt injection). The chapter-ID allowlist also prevents path traversal.
- **SR7** All model output is treated as untrusted. JSON is validated against the schema, and question text is displayed as plain text, never as HTML (prevents XSS).
- **SR8** The backend checks that every `answer` key matches an option key, and checks `stop_reason` so a response cut off at `max_tokens` (incomplete JSON) is caught and discarded.

### 9.3 Containers and network
- **SR9** The Ollama port is **not published** in Compose. Only the `app` container can reach it, over the internal network (`http://ollama:11434`). Ollama has no built-in authentication.
- **SR10** The app port is published to `127.0.0.1` only, so it isn't reachable from the network.
- **SR11** Image tags are pinned to specific versions (no `latest`).
- **SR12** Models are stored in a named volume so they survive rebuilds.

## 10. Question quality controls

### 10.1 Content rules
- Every question maps to at least one objective ID and tests its **discriminator**.
- Every option has a rationale (why correct, or which look-alike it matches).
- Distractors must come from genuine neighbors (e.g., tailgating vs piggybacking, IDS vs IPS, static NAT vs PAT, WPA2-Personal vs Enterprise).
- Avoid ambiguity, double-barrelled stems, and "per the book" wording.
- Anti-repetition: store a one-line fingerprint (objective, angle, format) per question; never reuse the same angle for an objective back-to-back. Pass recently used angles for the chapter into the generation prompt.

### 10.2 Promotion from `draft` to `verified` (D7)
1. Automated: schema valid; answer keys exist in options; every option has a rationale; objective IDs exist in the chapter file; no near-duplicate stem already in the pool; not truncated (SR8).
   - **Surface-cue checks (v2, 2026-10-21), per question:** answer not noticeably longer or shorter than the distractors (1.25x mean, 1.15x longest, plus 6 characters of slack); option lengths within 2.5x of each other; no absolute words only in wrong options; answer doesn't repeat the stem's wording (2+ words beyond the best distractor); every option has a role, answers are exactly the `best` options, and a `partial` option needs a BEST/FIRST/MOST stem.
   - **Pool bands, `python -m ccst.cli audit`:** answer is the longest option in 15-35% of single-answer questions and the shortest in 15-35% (uniform is 25%); multi-select answers are the longest options in at most 20%; absolutes only in distractors at most 5%; answer echoes the stem most at most 15%. v1 pools measured 68% longest-is-answer and a 1.91x answer/distractor length ratio.
2. Human: user spot-checks a sample of each generated batch against the book and objective file.
3. Reported questions (FR6) are retired, never edited in place.

**Known risk:** local models are weaker than Claude-class models at writing plausible wrong answers and getting subtle technical distinctions right. Grounding them in the objective documents reduces this risk but doesn't remove it. Compare providers in Phase 2 before relying on Ollama output.

## 11. Question-angle bank
- Symptom to attack (log excerpt, user complaint, traffic description)
- Attack to mitigation; mitigation to threat addressed
- Neighbor discrimination (A vs B)
- Scenario containing a distractor that matches a different concept
- "Which is NOT" / exception
- Root cause vs symptom
- Cause-and-effect ordering
- Chapter-specific: choose the wireless protocol or band for a site; choose the device (stateless vs stateful firewall, IDS vs IPS, proxy); port or protocol to service and secure vs insecure; secure replacement (Telnet to SSH, HTTP to HTTPS); address to class, type, or public vs private; worked NAT scenario (inside local vs inside global); IPv6 shorten or identify type; cross-chapter pairs (ARP/ARP spoofing, DHCP/rogue DHCP, DNS/DNS poisoning, TCP/SYN flood, ICMP/smurf).

## 12. Cost and token optimization

### 12.1 Claude API
- Use **prompt caching**: put the static instructions and chapter objectives first, and place the cache breakpoint at the **end of the static content**, not on the part that changes each request.
- **[VERIFY]** Minimum cacheable prompt size depends on the model (reported: 512 tokens for Sonnet 5.5, 4,096 for Haiku 4.5). Prompts below the minimum are silently not cached. Measure the token count of each chapter file.
- Default cache lifetime is 5 minutes. Use `usage.cache_read_input_tokens` to confirm cache hits.
- Use **structured outputs** (`output_config.format` with a JSON schema) so the output always parses.
- **[VERIFY]** Compare **Haiku 4.5** (reported $1/$5 per million input/output tokens) with **Sonnet 5.5** (reported $2/$10) on question quality before choosing. Confirm current pricing on the Claude pricing page.

### 12.2 Ollama (local)
- Use Ollama structured outputs: pass a JSON schema in the `format` parameter.
- Ollama ignores schema `description` fields, so put per-field instructions in the prompt.
- Smaller models can still slip in extra text, so validate and repair output either way.

### 12.3 Claude Code (development workflow)
- Run `/clear` between unrelated tasks, use plan mode for complex changes, write specific prompts, keep CLAUDE.md short, check `/context`, and use Sonnet by default.

## 13. Hardware and model selection
| Machine | Stated specs | Status |
|---|---|---|
| Dev laptop | 16 GB RAM, "8 GB VRAM" | **Checked 2026-10-07:** about 14.8 GB RAM usable; AMD Radeon integrated graphics, no dedicated VRAM; CPU-only for Ollama |
| Target OptiPlex | 32 GB RAM, "16 GB VRAM" | **[VERIFY]** |

**[VERIFY] high priority:** both "VRAM" figures are exactly half of system RAM, which is what Windows reports as *shared* GPU memory, not dedicated VRAM. Check Task Manager > Performance > GPU > **Dedicated GPU memory**, or run `nvidia-smi`. Most OptiPlex models ship with integrated graphics only, and the SFF/Micro chassis limit which GPU cards fit.

| Confirmed hardware | Candidate model |
|---|---|
| 8 GB dedicated (NVIDIA) | Qwen3 8B (~7 GB at Q4, tight) or a 4B model |
| 16 GB dedicated | Qwen3 14B (~12 GB) or gpt-oss 20B (~14 GB) |
| Integrated graphics only | 4B-class on CPU (slow, weaker quality); Claude mode may be better |

**[VERIFY]** The local model landscape changes monthly. Confirm current model names and sizes at ollama.com/library before choosing.

## 14. Docker and deployment

### 14.1 Compose design
- `app`: web app, published on `127.0.0.1:<port>`; mounts `/docs/objectives` read-only and `/data` read-write.
- `ollama`: no published ports, named volume for models, GPU access configured per platform.
- GPU: NVIDIA requires the NVIDIA Container Toolkit; AMD uses the `ollama/ollama:rocm` image; Vulkan is included in the standard image. **[VERIFY]** against current Ollama Docker docs.

### 14.2 Installer requirements
1. Check prerequisites and clearly explain anything missing (Docker installed and running, disk space, GPU).
2. Detect dedicated VRAM and choose a matching model automatically (section 13).
3. Run `docker compose up` and wait for a health check before reporting success.
4. Download the model with progress messages. Offer an **offline bundle** option (pre-saved model volume).
5. Open the browser automatically.
6. Make every step idempotent: re-running after a failure resumes instead of breaking things.
7. Provide an uninstall script that removes containers, images, and volumes.

**Known limitation:** on Windows, Docker Desktop and WSL2 installation need admin rights and often a reboot, so they can't be fully automated. The installer must detect this and explain it rather than fail.

### 14.3 Licensing
- **[OPEN]** Who owns the OptiPlexes? Docker Desktop is free for personal use, education, non-commercial open source, and small businesses (fewer than 250 employees **and** less than $10M revenue). Larger organizations and government entities need a paid subscription. **[VERIFY]** current terms.
- Free alternatives: **Docker Engine on Linux** (free regardless of owner) or Podman.

## 15. Content and compliance
- Objective documents are the user's own paraphrased notes built around public exam outlines and the Sybex guide. The notes are the user's own work; the risk is close paraphrase that follows one study guide's structure and wording. That risk is low for personal use and higher if the platform is published or sold.
- **Never** use recalled real exam questions ("brain dumps"); this violates the Cisco certification exam agreement (see 6.1 item 7).
- Every objective has a stable ID (`Cxx-yy`) that questions link back to.

## 16. Build plan (merged)
| Phase | Deliverable | Exit criteria |
|---|---|---|
| 0 | Verify blueprint (weights, count, time, question types) from Cisco plus a second source | Facts in section 3 confirmed or corrected |
| 1 | Quiz app running locally with **Ollama** (Ch1 pilot), behind the provider interface (D3). **Changed 2026-10-07:** Claude API integration is tabled; no API key or spend limit needed yet | Ch1 generates valid questions per batch (batch size tuned to CPU speed); schema validation and plain-text rendering in place; provider interface in place with Claude as a stub |
| 2 | Add Claude provider (when the user opts in) | Same chapter generates through either provider by changing one setting; quality compared and recorded; before this phase: API key in `.env` and a Console spend limit set (SR1 to SR3). Note: a free claude.ai account does not include API access; the API is billed separately with prepaid credits |
| 3 | Question pool, verification flow, reporting, tracker | Pool reuse working; draft-to-verified promotion; report-question flow; per-objective scoring; tracker persists; export summary works; all four modes run |
| 4 | Docker Compose | `docker compose up` brings the whole system up; Ollama unpublished; app on localhost only; pinned tags; data survives rebuild |
| 5 | Installer and hardware detection | Fresh-machine install succeeds; re-run is safe; uninstall works; offline bundle tested |
| 6 | Content rollout Ch2 to Ch13 | Each chapter generates and passes verification; no objective ID changes |
| 7 | Crosswalk (chapter, domain, IDs) from the official blueprint; correct provisional tags | Exam simulation follows the official domain and sub-objective structure (weights are estimates; Cisco publishes none) |
| 8 | Flashcard CSVs (ports, IPv6 specials, Wi-Fi security, private ranges, protocol list) | Imports into Anki cleanly |
| 9 | Readiness rule | e.g., three consecutive full simulations above a user-set target |

Rule: finish and understand each phase before starting the next.

## 17. Open questions and risks
1. **[DECISION 2026-10-07]** Backend: Python + FastAPI.
2. **[DECISION 2026-10-07]** Tracker storage: SQLite file on a mounted volume.
3. **[DECISION 2026-10-07]** Target OptiPlex OS: Windows 10/11 (Docker Desktop + WSL2; PowerShell installer; admin rights and a reboot may be needed, see 14.2).
4. **[DECISION 2026-10-07]** Target machines are personal/home, so Docker Desktop is free to use (re-check terms if ownership changes).
5. **[VERIFY]** Dedicated VRAM on the OptiPlexes. Dev laptop checked 2026-10-07: AMD Radeon integrated graphics only (no NVIDIA, `nvidia-smi` absent), about 14.8 GB RAM, so the earlier "8 GB VRAM" claim is wrong. Local Ollama on the laptop would run CPU-only (4B-class models, slow); use Claude mode for development there. Docker is not installed on the laptop yet.
6. **[VERIFY]** Token size of each chapter objective file, for cache minimums and model choice.
7. **[VERIFY]** Exam blueprint facts (section 3); domain tags provisional.
8. Ch2 Section E and Ch1 additions are user-approved, not from the book list; move them if the book places them elsewhere (IDs stay).
9. Possible gaps vs Cisco's official objectives; check once the blueprint is in hand.
10. App cannot replicate the Pearson VUE interface; user should view the official exam tutorial.
11. Tracker sync between app and chat is manual (paste export).
12. Local-model question quality (section 10.2 known risk).

**Status 2026-10-07:** Python 3.14.8 installed on the laptop; Claude API deferred (Phase 2).

**Phase 1 pilot result (2026-10-07):** App built (`src/ccst/`, FastAPI, Ollama provider, validation, pool, drill UI; 36 tests pass). Ollama 0.40.0 + `qwen3:4b` on the laptop CPU. Pipeline works end to end, and security checks pass (allowlist, 409 on concurrent generation, 422 on bad input, both services bound to 127.0.0.1). **Question quality is not acceptable:** 2 batches of 3 took 8 and 13 minutes (about 3 tokens/s); automated checks rejected 4 of 6; both accepted questions were wrong on review (off-objective; keyed answer contradicting its own rationale) and were retired. Confirms the section 10.2 known risk.

**[DECISION 2026-10-07] D1 amended (generation source):** until a capable runtime model is available (Claude API in Phase 2, or a GPU machine), question pools are **authored by Claude in a Claude Code session** and imported with `python -m ccst.cli import`. Imports go through the same automated checks as runtime output and enter as `draft` (`provider: claude`, `model` = the session's model). The authored source is kept in `data/authored/chNN_claude.json`. The runtime Ollama path stays in the code for later comparison.
**Ch1 pool:** 48 questions imported (Q-C01-0003 to Q-C01-0050), one per objective, all passing automated checks. Mix: 43 single and 5 multi; difficulty 8/30/10 (levels 1/2/3); all 8 angles used. Q-C01-0001 and Q-C01-0002 (Ollama) are retired. **Next:** user spot-checks the Ch1 drafts; the draft-to-verified promotion UI is built in Phase 3.
**Ch3 pool (2026-10-07):** 39 questions imported (Q-C03-0001 to Q-C03-0039), one per objective; 32 single and 7 multi; difficulty 5/25/9 (levels 1/2/3). Chapter-specific angles from section 11 were added to the schema (identify-from-port, secure-replacement, classify-address, nat-scenario, ipv6-shorten-or-type). The author's second-pass review replaced one option that HTTP/3 (QUIC over UDP 443) makes ambiguous.
**Validation test (Ch3):** 8 deliberately broken questions were run through the checks. All structural faults were caught: bad answer key, missing "(Choose two.)", option-letter reference, off-objective question, unknown objective ID, "all of the above", duplicate of a pooled question. A factual error (SNMP traps on UDP 161 instead of 162) is **not detectable** by automated checks. **Conclusion:** automated checks guard structure only; factual accuracy depends on the author's review plus the user's spot-check before promotion to `verified` (D7). Fix made during the test: `--dry-run` now checks duplicates against the stored pool, as a real import does.

**Phase 3 build (2026-10-07):** done. Exit criteria were checked against a scratch copy of the data, so the user's real tracker and pool stayed untouched.
- **Tracker:** SQLite at `data/tracker.db` (open question 2 resolved). Sessions and attempts are stored there. Per-objective status is always derived from attempts, never stored. Attempts on retired questions no longer count.
- **Modes:** all four run.
  - Diagnostic: one question per objective, feedback at the end.
  - Targeted drill: drill weights Weak 8, Improving 3, Solid-due 3, New 2, Solid 0.2; immediate feedback.
  - Exam simulation: verified only; estimated domain weights; 50-minute timer; flag and navigator; feedback at the end.
  - Review misses: shows the questions whose latest answer was wrong; "Explain this" calls the local model.
- **Confidence:** a confidence rating (Guess / Unsure / Sure) is recorded with every answer.
- **Error types:** an error type can be chosen after a miss (after finishing, in exam and diagnostic).
- **Verification flow:**
  - A "Review drafts" queue shows the answer, rationales, and objectives, with Verify, Skip, and Report buttons.
  - Report retires a question with a fixed reason plus an optional note. The note is stored only and never sent to a model (SR6).
- **Export summary:** follows section 8.5. "Newly Solid" means objectives that became Solid in the last finished session.
- **Reset:** clears sessions and attempts; question pools are kept.
- **Tests:** 49 pass (status rules, revisit schedule, mode selection, exam allocation, API flows, input validation).

**Finding: pool depth.** Each objective has exactly one primary question, so Solid (needs 2+ angles) is unreachable, and drills repeat the same question. Pools need 2 to 3 questions per objective, with different angles, before the tracker is meaningful. Recommended next content step: a second authored pass for Ch1 and Ch3.
**Resolved 2026-10-07 (second sets):**
- Imported 48 Ch1 (Q-C01-0051 to 0098) and 39 Ch3 (Q-C03-0040 to 0078) questions. Every objective now has 2 active questions on 2 different angles, so Solid is reachable.
- Each set 2 has 8 multi-select questions (first sets: 5 and 7).
- The second sets lean on "which-is-not" and the chapter-specific angles.
- The author's review fixed one stem whose rationale relied on an unstated fact.
- **Validator fixes found while importing:**
  - The option-letter check was case-insensitive and flagged "answers a SYN". The letter must now be a capital.
  - The near-duplicate check compared stems only and flagged templated "Which statement about X is NOT true?" stems. It now compares stem plus option texts.
  - Both fixes have regression tests (51 tests pass).

**Phase 6 progress: content rollout (author-written pools, D1 amended).** The user asked to go one chapter batch at a time and to be asked before the next chapter.
- **Ch2 (2026-10-19):**
  - 88 questions imported: Q-C02-0001 to 0044 (set 1) and Q-C02-0045 to 0088 (set 2), with 2 per objective on different angles. All passed automated checks on the first run, with 0 rejects.
  - 10 multi-select, below the 25% target. Difficulty is 22/57/9 (levels 1/2/3).
  - Three chapter angles were added to the schema: choose-protocol, choose-band-or-standard, and choose-device.
  - The objective file was reviewed before writing: no factual errors.
  - The author's second-pass technical review found no errors.
  - The domain tag is None (Ch2 spans 1.0 and 2.0), so the questions count as "untagged" in exam allocation until Phase 7.
- **Ch4 (2026-10-19):**
  - 48 questions imported: Q-C04-0001 to 0024 (set 1) and 0025 to 0048 (set 2), with 2 per objective on different angles and 0 rejects.
  - 7 multi-select. Difficulty is 7/30/11 (levels 1/2/3).
  - Two chapter angles were added: classify-factor and interpret-config. The config questions show IOS fragments in the stem.
  - One authoring slip was fixed before import: a secondary objective written as C04-27, which does not exist. The validator would have rejected it.
  - The author's technical review found no errors.
  - **Objective-file notes:**
    - C04-21 duplicates C02-05 (posture), and C04-23 duplicates C02-06 (guest network); C04-17 overlaps C02-04. Phase 7 should decide whether to merge them. IDs are frozen, so the option is to retire one, never rename.
    - C04-01 says `password` "is not hashed". More precisely, it is stored in cleartext, or weakly obscured as type 7 with `service password-encryption`.
  - The domain tag is None (Ch4 spans 1.0 and 2.0).
- **Ch5 (2026-10-19):**
  - 74 questions imported: Q-C05-0001 to 0037 (set 1) and 0038 to 0074 (set 2), with 2 per objective on different angles and 0 rejects.
  - 7 multi-select, all in set 2. Difficulty is 10/51/13 (levels 1/2/3).
  - Three chapter angles were added: complete-config, find-config-error, and interpret-output.
  - About 20 questions use IOS config fragments or `show` output (packet decisions, wildcard math, shadowed entries, `access-class` vs `access-group`, unnumbered entries appended in named ACLs).
  - The author's technical review found no errors.
  - **Objective-file note:** C05-34 ties sequence-number editing to named ACLs; modern IOS also allows it on numbered ACLs (via `ip access-list` mode). The questions use named ACLs only.
  - The domain tag is None (Ch5 spans 1.0 and 2.0).
- **Ch6 (2026-10-20):**
  - 54 active questions: set 1 Q-C06-0001 to 0027 (with 0019 retired), the replacement 0028, and set 2 0029 to 0055. Each objective has 2 questions on different angles.
  - 9 multi-select, a higher share as offered. Difficulty is 7/37/10 (levels 1/2/3). The domain tag is 3.0.
  - One angle was added: compute-permissions (share + NTFS, copy vs move, chmod).
  - **Validator catches:**
    - 4 set 1 questions used cross-chapter secondary IDs (C04-08, C01-08, C04-10, C03-09). The importer accepts only same-chapter IDs, so these were changed to Ch6 IDs.
    - The near-duplicate check counted retired questions, which would block corrected replacements. It now skips retired questions (regression test added; 52 tests pass).
  - **Author review found 1 factual issue after import:** Q-C06-0019 said that after Windows 10 end of support (Oct 14, 2025) PCs "no longer receive security patches", ignoring Microsoft's paid Extended Security Updates (ESU). It was retired with that reason and replaced by Q-C06-0028 ("not enrolled in ESU"). The set 2 explanation was corrected before import.
  - **Objective-file notes:**
    - C06-19 should mention ESU.
    - C06-16 says the macOS application firewall has "`pf` underneath". The application firewall is a separate per-application socket filter, and `pf` is a distinct packet filter. No question depends on this.
- **Ch7 (2026-10-20):**
  - 84 questions imported: Q-C07-0001 to 0042 (set 1) and 0043 to 0084 (set 2), with 2 per objective on different angles and 0 rejects.
  - 11 multi-select. Difficulty is 33/43/8 (levels 1/2/3), easier on average because the chapter is tool and step recall. The domain tag is 3.0.
  - One angle was added: choose-tool.
  - Output-reading questions cover nslookup, netstat, tracert, and port-scan results (open, closed, filtered).
  - The author's technical review found no errors.
  - **Objective-file note:** C07-19 says a standard format leaves data recoverable. That is true of a quick format, but a Windows full format (Vista and later) zero-fills the volume. The questions say "standard (quick) format".
- **Ch8 (2026-10-20):**
  - 62 questions imported: Q-C08-0001 to 0031 (set 1) and 0032 to 0062 (set 2), with 2 per objective on different angles and 0 rejects.
  - 8 multi-select. Difficulty is 27/31/4 (levels 1/2/3). The domain tag is 4.0.
  - Four angles were added: classify-element, assess-risk, choose-response, and find-missing-element.
  - The author's technical review found no errors.
  - **Tool fix:** `--dry-run` crashed on a schema error (one item had 4 objective IDs, and the maximum is 3) instead of reporting it. It now reports schema errors per question, as a real import does. The item was fixed to 3 IDs.
  - **Objective-file note:** C08-19 (posture assessment) is the third copy of the posture concept (after C02-05 and C04-21). Add it to the Phase 7 merge list.
- **Coverage verification (2026-10-20, user request):** every objective in Ch1 to Ch9 has exactly 2 active questions on 2 distinct angles, and no question references an ID missing from its objective file. This is now a permanent command: `python -m ccst.cli coverage --chapters 1 2 ...` (exit code 1 on any failure).
- **Ch9 (2026-10-20):**
  - 76 active questions: set 1 Q-C09-0001 to 0038 (with 0016 retired), the replacement 0039, and set 2 0040 to 0077.
  - 8 multi-select. Difficulty is 35/37/4 (levels 1/2/3). The domain tag is 4.0.
  - **Author review retired Q-C09-0016:** its stem used "CVE-2025-12345" as an example, and real CVE IDs share that format, so it could appear to state facts about an actual CVE. The replacement describes the finding without an ID. **Rule going forward: no specific-looking CVE IDs in questions.**
  - **Objective-file notes:**
    - More cross-chapter overlap for Phase 7: C09-01 vs C08-03 (vulnerabilities), C09-09 vs C01-29 (brute force), C09-12 vs C01-39 (social engineering), C09-36 vs C07-31 (recovery).
    - `setenforce` only switches between enforcing and permissive; disabling SELinux needs a config change and a reboot. No question claims otherwise.
- **Ch10 (2026-10-20):**
  - 96 questions imported: Q-C10-0001 to 0048 (set 1) and 0049 to 0096 (set 2), with 2 per objective on different angles and 0 rejects. `coverage` passes for Ch1 to Ch10.
  - 11 multi-select. Difficulty is 46/43/7 (levels 1/2/3).
  - The domain tag is None: the file says its fit is uncertain (1.0, 4.0, or 5.0), so this goes to Phase 7.
  - One authoring slip was fixed before the dry-run: one item had the angle in its `type` field.
  - The author's technical review found no errors.
  - **Objective-file notes:**
    - C10-27 describes single-interlock preaction; double-interlock needs both detection and an opened head.
    - NAF-S-III (an HCFC) and FM-200 (an HFC) face their own phase-out or phase-down rules. The file doesn't claim otherwise, and no question depends on it.
- **Ch11 (2026-10-20):**
  - 46 questions imported: Q-C11-0001 to 0023 (set 1) and 0024 to 0046 (set 2), with 2 per objective on different angles and 0 rejects. `coverage` passes for Ch1 to Ch11.
  - 6 multi-select. Difficulty is 24/21/1 (levels 1/2/3); the chapter is mostly definitions and regulation scopes. The domain tag is 5.0.
  - The author's technical review found no errors.
  - **Objective-file notes (more Phase 7 overlap):** C11-02 vs C06-27 (SIEM), C11-08 vs C02-43 (anomaly detection), C11-12 vs C09-15 (threat intelligence), C11-16 vs C07-25 (regulatory compliance).
- **Ch12 (2026-10-20):**
  - 20 questions imported: Q-C12-0001 to 0010 (set 1) and 0011 to 0020 (set 2), with 2 per objective on different angles and 0 rejects. `coverage` passes for Ch1 to Ch12.
  - 3 multi-select. Difficulty is 5/13/2 (levels 1/2/3). The domain tag is 5.0.
  - The author's technical review found no errors. The objective file's Kill Chain order, ATT&CK structure, Diamond features, and order of volatility are accurate.
  - **Objective-file notes (Phase 7):** C12-10 duplicates C09-34 (chain of custody), so add it to the merge list. C12-06 (TTPs) vs C11-13 (IoC) is a neighbor pair, not a duplicate: crosswalk it as a link.
- **Ch13 (2026-10-20):**
  - 96 questions imported: Q-C13-0001 to 0048 (set 1) and 0049 to 0096 (set 2), with 2 per objective on different angles and 0 rejects. `coverage` passes for Ch1 to Ch13.
  - 14 multi-select. Difficulty is 24/70/2 (levels 1/2/3). The domain tag is 5.0.
  - The author's technical review found no errors. NIST questions name SP 800-61 Revision 2 for the four-phase lifecycle and note that Revision 3 (April 2025) supersedes it. FISMA questions say "within required timeframes" and give no specific number of hours.
  - **Objective-file notes (Phase 7):**
    - C13-24 (containment) and C13-43 (eradication) both list disabling accounts, so no question uses account disabling alone to tell the two phases apart.
    - Cross-links: C13-32 and C13-41 vs C12-08 to C12-10 (evidence); C13-37 "improper usage" vs C13-08 (insider).
- **Pools:** Ch1 96, Ch2 88, Ch3 78, Ch4 48, Ch5 74, Ch6 54, Ch7 84, Ch8 62, Ch9 76, Ch10 96, Ch11 46, Ch12 20, Ch13 96 = **918 active (all draft)**.
- **Authoring is complete for all 13 chapters.** Phase 6's exit criterion ("passes verification") still needs the user's spot-check: verify drafts in the Review queue. Exam simulation stays locked until verified questions exist.

**Phase 6b: v2 cue-free rewrite (started 2026-10-21).** User feedback: difficulty varied too much, and answers could be inferred from the options alone. A cue audit of the 918 v1 questions confirmed it: the answer was the longest option in 68% of single-answer questions (chance is 25%), at 1.91x the distractors' length. The user approved the four-role option structure (wrong / related / technically correct / best) and suggestions 1-6: stems that don't name the concept, few "which is NOT" items, recall-first mode, guesses not counted as mastery, too-easy flags, and exhibits. Chapter-by-chapter rollout as before; ask before each chapter.
- **Tooling:** option `role` and question `exhibit` fields; surface-cue checks at import (10.2); `audit` and `retire` CLI commands; recall-first mode, role labels in feedback, exhibit rendering, guess rule, too-easy list and report reason in the app (8.4). 66 tests pass. Verified in the browser on a scratch-data instance (`ccst-uitest`, port 8002).
- **Ch1 pilot (2026-10-21):** v1 Q-C01-0003 to 0098 retired (superseded). A first v2 import (0099 to 0194) passed per-question checks but the audit still showed the answer longest in 37% of singles and the two longest options as the answers in 10 of 17 multi-selects; rebalanced (some answers shortened to be the shortest option, not only distractors lengthened, to avoid a "middle-length" cue) and re-imported as **Q-C01-0195 to 0290**. Files: `data/authored/ch01_v2_set1a/1b/2a/2b.json`.
  - Audit: answer longest 20%, shortest 28%, length ratio 0.99x, absolutes-only-in-distractors 0%, multi answers = longest 0%, stems naming their objective 20%, which-is-NOT 0, exhibits 10, 17 multi-select. Difficulty 6/64/26 (levels 1/2/3). Roles: 61 partial options. `coverage` and `audit` pass.
  - User review (2026-10-21): "these questions are perfect, especially the ones with practical applications of log analysis/command schema". Two reported: Q-C01-0224 (ambiguous: the partial option was also a full description) and Q-C01-0251 (reported wrong-answer; author still considers the key correct, since disabling directed broadcasts and ignoring broadcast pings are the standard amplifier fixes). Replaced on new angles by Q-C01-0291 and 0292 (`ch01_v2_fix1.json`).
- **History fix (2026-10-21):** answers to retired questions were excluded from objective status, so retiring a pool for a rewrite silently dropped the learner's history (10 Ch1 answers). Now only flawed retirements (reported, factual error) are excluded; retirements whose reason starts with "Superseded" keep counting (`pool.flawed_ids`, `retire --superseded`).
- **Ch2 (2026-10-21):** v1 Q-C02-0001 to 0088 retired as superseded; v2 **Q-C02-0089 to 0176** imported (88, 0 rejects). Audit: longest 25%, shortest 22%, ratio 1.02x, absolutes 0%, multi answers = longest 0%, 11 multi-select, **23 exhibits** (firewall/IPS/proxy logs, wireless scans, AP configs, NAC posture and switch logs, ACLs, state table), difficulty 5/66/17. Stems naming their objective: 45% (protocol-comparison objectives like WPA2 vs WPA3 and "Wi-Fi" terms need the name in the stem). `coverage` and `audit` pass for Ch1 and Ch2.
- **Ch3 (2026-10-21):** v1 Q-C03-0001 to 0078 retired as superseded; v2 **Q-C03-0079 to 0156** imported (78, 0 rejects). Audit: longest 30%, shortest 19%, ratio 1.04x, absolutes 0%, multi answers = longest 0%, 14 multi-select, **19 exhibits** (Telnet/FTP/SNMP/SSH/DNS/TFTP/DHCP captures, `ipconfig`, `netstat`, `tracert`, `arp -a`, NAT translation tables, cert warning), difficulty 6/57/15. Stems naming their objective 44% (protocol and address-class objectives). IPv6 shortening items avoid equal-length zero runs, so only one compressed form is correct. `coverage` passes for Ch1 to Ch3.
- **Ch4 (2026-10-21):** v1 Q-C04-0001 to 0048 retired as superseded; v2 **Q-C04-0049 to 0096** imported (48, 0 rejects). Audit: longest 26%, shortest 28%, ratio 1.01x, absolutes 0%, 5 multi-select, **13 exhibits** (IOS local-account and AAA method-list configs, TACACS+ authorization and accounting logs, RADIUS packets and Access-Challenge exchange, 802.1X port status, NAC profiler result, guest ACL), difficulty 3/40/5. `coverage` passes for Ch1 to Ch4.
- **Ch5 (2026-10-21):** v1 Q-C05-0001 to 0074 retired as superseded; v2 **Q-C05-0075 to 0148** imported (74, 0 rejects). Audit: longest 21%, shortest 28%, ratio 1.02x, absolutes 0%, 7 multi-select, 11 exhibits plus CLI in stems and options (ACL entries, `show access-lists`, `show ip interface`, `show crypto isakmp/ipsec sa`, VTI config, cert path, `Get-FileHash`), difficulty 9/42/23. Set 1 first drafted at 56% longest-is-answer; rebalanced before import by shortening 10 answers. `coverage` passes for Ch1 to Ch5.
- **Ch6 (2026-10-21):** v1 Q-C06-0001 to 0055 retired as superseded (0019 had already been retired as flawed); v2 **Q-C06-0056 to 0109** imported (54, 0 rejects). Audit: longest 27%, shortest 27%, ratio 1.01x, absolutes 0%, 6 multi-select, **11 exhibits** (`Get-NetFirewallProfile`, `icacls`, `net share`, Event Viewer 4625, Security log with 4720/4732/1102, `ls -l`, `apt upgrade`, `ufw status`, Cisco syslog messages, SIEM correlation alert), difficulty 4/41/9. The OS life-cycle questions avoid Windows 10 dates (the ESU nuance that retired v1 Q-C06-0019). `coverage` passes for Ch1 to Ch6.
- **Ch7 (2026-10-21):** v1 Q-C07-0001 to 0084 retired as superseded; v2 **Q-C07-0085 to 0168** imported. The first audit failed the echo band (17%: the answer repeated stem words more than any distractor), so four answers were reworded (C07-26, 30, 39, 42), their questions Q-C07-0110, 0114, 0123 and 0126 retired as superseded, and the fixes imported as **Q-C07-0169 to 0172** (`ch07_v2_fix1.json`). `rank.py` now reports echo before import. Audit: longest 30%, shortest 22%, ratio 1.06x, absolutes 0%, 8 multi-select, 12 exhibits, difficulty 15/62/7.
- **Ch8 (2026-10-21):** v1 Q-C08-0001 to 0062 retired as superseded; v2 **Q-C08-0063 to 0124** imported (62, 0 rejects). Audit: longest 28%, shortest 19%, ratio 1.05x, absolutes 0%, 5 multi-select, 7 exhibits, difficulty 15/44/3.
- **Ch9 (2026-10-21):** 76 active v1 questions retired as superseded; v2 **Q-C09-0078 to 0153** imported (76, 0 rejects). Audit: longest 24%, shortest 30%, ratio 1.03x, echo 10%, absolutes 0%, 9 multi-select, **13 exhibits** (vulnerability scan report, `dig axfr`, `nmap`, FTP capture, brute-force login log, NVD-style entry with placeholder ID, GPO precedence, `getenforce` with AVC denial, `smb.conf`, `ss -tlnp`, incident log, custody log, post-incident review), difficulty 11/55/10. `coverage` passes for Ch1 to Ch9.
- **Ch10 (2026-10-22):** 96 v1 questions retired as superseded; v2 **Q-C10-0097 to 0192** imported (96, 0 rejects). Audit: longest 26%, shortest 25%, ratio 1.01x, echo 7%, absolutes 0%, 12 multi-select, 9 exhibits (backup plan, `copy running-config tftp:`, incremental schedule, RPO timeline, humidity readings, PDU power path, DR agreement, load-balancer pool, `show standby brief`), difficulty 27/60/9. Stems naming their objective: 68%, since many objectives are equipment or agent names (UPS types, suppression agents, site types).
- **Ch11 (2026-10-22):** 46 v1 questions retired as superseded; v2 **Q-C11-0047 to 0092** imported (46, 0 rejects). Audit: longest 28%, shortest 30%, echo 5%, 6 multi-select, 5 exhibits (SIEM correlated alert, login baseline table, UEBA alert, threat feed vs host scan, breach notification timeline).
- **Ch12 (2026-10-22):** 20 v1 questions retired as superseded; v2 **Q-C12-0021 to 0040** imported (20, 0 rejects). Audit: longest 31%, shortest 25%, echo 12% (2 of 16), 4 multi-select, 1 exhibit (lab notes showing the original disk examined before imaging).
- **Ch13 (2026-10-22):** 96 v1 questions retired as superseded; v2 **Q-C13-0097 to 0192** imported (96, 0 rejects). Audit: longest 26%, shortest 24%, echo 5%, 14 multi-select, 6 exhibits (responder notes in mixed formats, event log, phishing email, risk table, response log, recovery checklist done out of order). NIST SP 800-61 items name Rev. 2 for the four-phase lifecycle and note that Rev. 3 (April 2025) supersedes it.
- **Phase 6b complete (2026-10-22):** all 13 chapters are on v2. Whole pool: 918 active (801 single, 117 multi), answer longest 26%, shortest 25%, length ratio 1.02x, echo 7%, absolutes-only-in-distractors 0%, multi answers = longest 0%, 140 exhibits, difficulty 149/637/132; `coverage` (2 per objective, 2 angles) and `audit` pass for Ch1 to Ch13. All questions are drafts; exam simulation still needs verified questions.
- **Next:** the user flags ambiguous questions while drilling; check `coverage` after reports and write `chNN_v2_fixN.json` replacements on a new angle.

**Phase 4 complete (2026-10-12)** on Docker Desktop 29.8.1 / Compose v5.5.1 (WSL2) on the dev laptop. All exit criteria were verified:
- `docker compose up -d` brings up app, ollama, and ollama-pull, all healthy or exited 0.
- `docker port ccst-ollama-1` is empty, and 127.0.0.1:11434 is unreachable from the host while the app reaches Ollama (`/api/status` shows reachable, model present).
- The app listens on 127.0.0.1:8000 only; it is not reachable from the LAN IP.
- Tags are pinned.
- `tracker.db` and the pool JSON had identical hashes before and after `docker compose down` plus a `--no-cache` rebuild, and a container-written file survived the rebuild.
- The container runs as uid 10001, and the objective files are read-only.
- "Explain this" ran end to end in 52.5 s (36 s on native Windows Ollama).

**Lessons for Phase 5:**
- The Ollama image is 3.78 GB compressed (9.4 GB on disk); at about 0.5 MB/s it took about 2 hours. The installer needs progress reporting and the offline-bundle option (14.2 item 4).
- Seeding the `ccst_ollama-models` volume from an existing local model store (copy into `/root/.ollama/models`) skips the 2.5 GB model download; ollama-pull then finishes in seconds.
- Native Windows Ollama autostarts at login and must be stopped (or disabled) while the Docker stack runs, to avoid two CPU-bound model servers.
- Non-TTY `docker pull` prints no progress bars; measure adapter throughput instead.

**Phase 5 complete (2026-10-12): Windows installer.**
- **Scripts:** `install/install.ps1` (+ `install.cmd`), `uninstall.ps1` (+ `.cmd`), `make-bundle.ps1`, `lib.ps1`. A Linux `install.sh` was not built, because the target OS is Windows (decision 3).
- **Installer steps:**
  - Checks prerequisites: Docker CLI, engine (starts Docker Desktop if it is installed but stopped), Compose v2, disk space, and the port.
  - Warns about, or stops (`-StopNativeOllama`), the Windows Ollama app.
  - Detects hardware: `nvidia-smi`, else the registry's dedicated-memory value, which flags integrated GPUs as shared RAM. It reads the memory Docker can use.
  - Picks a model: NVIDIA ≥15 GB gets qwen3:14b, ≥7.5 GB gets qwen3:8b, a smaller NVIDIA gets qwen3:4b; with no NVIDIA it gets qwen3:4b on CPU, or qwen3:1.7b when Docker has less than 6 GB. Docker Desktop on Windows can't use AMD or Intel GPUs.
  - NVIDIA machines get `docker-compose.gpu.yml` through COMPOSE_FILE in `.env`, with automatic CPU fallback.
  - Model source, in priority order: bundle, then this PC's own Ollama store (copies only that model's files), then download via `docker compose exec ollama ollama pull` (TTY progress).
  - Starts the stack, waits until the app and model are ready, and opens the browser.
  - Never asks for an API key (SR4). The app port is configurable (`-Port`) and always bound to 127.0.0.1.
- **Compose change:** `ollama-pull` moved behind the `pull` profile, so an offline `up` makes no network calls.

**Exit-criteria tests (dev laptop, AMD iGPU):**
- **Re-run safety:** a no-op install re-run (9 s), and an uninstall re-run.
- **Uninstall:** removes containers, network, model volume, and both images. `.env` keys are cleaned; the user's `tracker.db` and pool are byte-identical before and after.
- **Install from this PC's Ollama store:** uninstall with `-KeepImages`, then install (66 s).
- **Offline bundle (fresh-machine simulation):**
  - Built a 5.89 GB bundle (images.tar 3.57 GB + model 2.33 GB; checksums verified; no tracker, `.env`, or logs) in 6.6 min.
  - After a full uninstall (no images, no volume), installed from the bundle in its own folder in 5 min. Docker image events show **2 loads, 0 pulls**. The re-run took 8 s.
  - The real install was then restored from the project folder; mounts were confirmed and data hashes were unchanged.
- **Model-choice table:** 6 simulated hardware cases pass (`tests/test_install_select_model.ps1`).
- **Port conflict:** refused cleanly, with `.env` untouched.

**Bugs found and fixed while testing:**
- PowerShell 5.1 mangled double quotes in the `sh -c` script (exit 2); the script now uses single quotes only.
- `compose down` left the profile-gated `ollama-pull` container; uninstall now removes all project-labelled containers.
- The port check trusted any running app container, even one on a different port; it now checks that our container publishes that exact port.

**Not tested here:**
- The NVIDIA GPU path on real hardware (no NVIDIA card).
- The network model download (`ollama pull` path) end to end; about 1.4 h at this connection's speed.
- The "Docker not installed" message on a truly fresh PC.
- These need the OptiPlexes; the dedicated-VRAM check is still pending (section 17, item 5).

**Phase 4 files (written 2026-10-07):** Added `Dockerfile`, `docker-compose.yml`, and `.dockerignore`; runtime requirements are split from `requirements-dev.txt`.
- **Images:** pinned to `python:3.14.8-slim-trixie` and `ollama/ollama:0.40.0`; both tags confirmed on Docker Hub.
- **app:**
  - Published on `127.0.0.1:8000` only.
  - Runs as a non-root user.
  - Objective files are mounted read-only.
  - `./data` is bind-mounted, so the pool and `tracker.db` survive rebuilds and stay visible on the host.
- **ollama:** no published ports (SR9); a named volume `ollama-models` holds the models (SR12); healthcheck `ollama list`; an NVIDIA GPU block is included, commented out.
- **ollama-pull:** a one-shot service that pulls `OLLAMA_MODEL` and exits; safe to re-run.
- **Install prerequisite (resolved 2026-10-12):** the user installed WSL2 and Docker Desktop (admin rights and a reboot were needed, as 14.2 predicts).
- **Linux note for Phase 5:** the container user (uid 10001) must be able to write the bind-mounted `./data`. Docker Desktop on Windows handles this; on Linux the installer must set ownership or the UID.
- **Disk:** the containerized Ollama downloads its own copy of the model (2.5 GB) separate from the native Windows Ollama. Only one should run at a time to avoid two CPU-bound model servers.

## 18. Handoff instructions
1. Project instructions: `CCST_Project_Instructions.md`. Source of truth: this document plus `CCST_Ch01.md` to `CCST_Ch13.md`.
2. Before writing code: answer open questions 1 to 4 (section 17) and complete the hardware check (section 13).
3. First build message: "Read the project scope and plan. Complete Phase 0, then build Phase 1 with the Chapter 1 pilot."

## 19. References
- Claude Code: Manage costs: https://code.claude.com/docs/en/costs
- Claude API: Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Claude API: Structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Ollama: Structured outputs: https://docs.ollama.com/capabilities/structured-outputs
- Ollama: Docker: https://docs.ollama.com/docker
- Docker Desktop license: https://docs.docker.com/subscription/desktop-license/
- Local model VRAM estimates: https://www.promptzone.com/llm-gpu-calculator
- Open-weight local models overview: https://huggingface.co/blog/daya-shankar/open-source-llm-models-to-run-locally
