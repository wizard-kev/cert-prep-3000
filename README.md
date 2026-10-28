# Kevin's Super Cert Prep 3000

A study app for certification exams that runs on your own computer. It asks you practice questions, simulates the
exam, and tracks how well you know each exam objective over time. CCST Cybersecurity (Cisco 100-160) comes ready to
use; any other certification can be set up with the built-in wizard.

The app runs no AI itself and makes no network connections. Where Claude helps (writing questions, gathering exam
facts, building objective lists, tutoring), the app writes the prompt; you paste it into a chat at claude.ai and
paste Claude's reply back.

## Install and run

- **Install:** run `install\install.cmd`. It finds Python 3.12 or newer, sets up the app, adds desktop and
  Start-menu shortcuts, and starts it.
- **Run:** use the desktop shortcut, or `.\run.ps1`. The app opens at http://127.0.0.1:8000.
- **Uninstall:** run `install\uninstall.cmd`. Your progress and certifications are kept unless you add `-RemoveProgress`.

## What it does

- **Practice:** feedback after every answer. It leans toward your weak objectives, brings back what you missed, and
  keeps introducing objectives you haven't tried.
- **Focus:** paste a list of objectives (from an exam guide, say) and get questions on just those.
- **Exam simulation:** timed and weighted like the real exam, with feedback at the end.
- **Progress:** an objective tracker, charts over time, how well your confidence matches your results, and
  suggestions for where new questions would help.
- **Question checks:** answer a question and it counts as Passively-Validated. Mark it "Looks right", or report a
  problem; reported questions are out of play until you confirm or undo the report.
- **Certifications:** set one up with the wizard (name, exam facts, objectives, first questions), or move one between
  computers as a pack.
- **Pick up where you left off:** unfinished sessions wait on the home page.
- **Backups:** your progress is backed up before every upgrade, reset and restore, and you can back up, restore or
  download it yourself.

The **Help** page in the app explains every feature, the question statuses and objective levels, and how scores
are worked out.

## Your data

Everything lives in the `data` folder:

- `data\progress.db`: your sessions and answers;
- `data\backups`: progress backups;
- `data\certs`: one folder per certification, with its exam facts, objectives and questions.

Progress is never put in version control and never included in a pack.

## For developers

- **Tests:** `.\.venv\Scripts\python.exe -m pytest -q` (install `requirements-dev.txt` first).
- **Command-line tools:** coverage and audit of a question pool, imports, retiring questions. See `CLAUDE.md`.
- **Design and history:** `Project Documents\v2_Scope_and_Plan.md` (git tags `v1` and `v2`).
