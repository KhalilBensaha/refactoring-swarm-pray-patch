# Refactoring Swarm Template

Multi-agent Python code repair loop (Auditor → Fixer → Judge) designed for the IGL practical session (2025–2026).

## Architecture

- See the full system design and module map in [ARCHITECTURE.md](ARCHITECTURE.md).

## What This Does

Given a target directory of Python files (e.g. `./sandbox`), the system will:

- Analyze the code and produce a structured refactoring plan (Auditor).
- Apply minimal fixes based on that plan (Fixer).
- Validate by running pytest + pylint and feeding failures back into the next iteration (Judge).

Logs are written to `logs/experiment_data.json`.

## Requirements

- Python 3.10 or 3.11
- A Google Gemini API key (`GOOGLE_API_KEY`) in a `.env` file

Install Python dependencies:

- `pip install -r requirements.txt`

## Quick Setup Check (Optional)

Run the provided sanity check:

- `python check_setup.py`

## Run

Run the orchestrator on the sandbox directory:

- `python main.py --target_dir ./sandbox`

The orchestrator stops when either:

- All tests pass, or
- The maximum number of iterations is reached (default: 10)

## Final Validation (No LLM Calls)

To validate the submission artifacts (log file + pytest + pylint) without calling any LLM:

- `python -m src.utils.final_check --target_dir ./sandbox`

## Project Structure

- [main.py](main.py): orchestrates the multi-agent loop
- [src/agents/](src/agents/): Auditor, Fixer, Judge
- [src/tools/](src/tools/): wrappers for pylint/pytest + sandbox-safe file operations
- [src/utils/](src/utils/): logging, quota management, final checks
- [ARCHITECTURE.md](ARCHITECTURE.md): detailed architecture documentation
