# The Refactoring Swarm – Architecture

Multi-agent autonomous repair loop for Python code.

IGL Module Practical Session – Academic Year 2025–2026

## 1) Goal

The system takes a directory of Python code (typically a “buggy” exercise) and attempts to:

- Identify root-cause defects and risky edge cases.
- Apply minimal, targeted code fixes.
- Validate correctness by running unit tests.
- Track the full scientific trace of prompts/responses and system events in a structured log.

The entrypoint is [main.py](main.py).

## 2) High-Level Design

The architecture is a deterministic orchestration loop around three LLM-powered agents:

1. **Auditor**: analyzes code and produces a structured refactoring plan (no edits).
2. **Fixer**: applies minimal edits for the issues in the plan (writes only inside the target directory).
3. **Judge**: runs tests + pylint, summarizes failures, and provides feedback for the next iteration.

The Orchestrator coordinates the flow:

```
			  +---------------------+
			  |     Orchestrator    |
			  | (main.py / run())   |
			  +----------+----------+
							 |
							 v
		  +-------------+--------------+
		  |         AuditorAgent        |
		  | (static + LLM analysis)     |
		  +-------------+--------------+
							 |
							 v
		  +-------------+--------------+
		  |          FixerAgent         |
		  |   (minimal code changes)   |
		  +-------------+--------------+
							 |
							 v
		  +-------------+--------------+
		  |          JudgeAgent         |
		  | (pytest + pylint + debug)  |
		  +-------------+--------------+
							 |
							 v
					PASS / RETRY
```

## 3) Repository Layout (What Lives Where)

- [main.py](main.py): Orchestrator (Auditor → Fixer → Judge loop), environment validation, start/stop conditions.
- [check_setup.py](check_setup.py): quick sanity check (Python version, `.env` presence, logs folder).
- [requirements.txt](requirements.txt): runtime dependencies.

Core packages:

- [src/agents/auditor.py](src/agents/auditor.py): `AuditorAgent`, `RefactoringPlan`, `CodeIssue`.
- [src/agents/fixer.py](src/agents/fixer.py): `FixerAgent`, `FixResult`.
- [src/agents/judge.py](src/agents/judge.py): `JudgeAgent`, `JudgementResult`.

Shared tools:

- [src/tools/file_tools.py](src/tools/file_tools.py): sandbox-restricted file I/O (enforced safety boundary).
- [src/tools/analysis_tools.py](src/tools/analysis_tools.py): wrappers for `pylint` and `pytest`.

Shared utilities:

- [src/utils/logger.py](src/utils/logger.py): structured scientific logging to `logs/experiment_data.json`.
- [src/utils/log_validator.py](src/utils/log_validator.py): validates the log schema (teacher-facing).
- [src/utils/quota_manager.py](src/utils/quota_manager.py): bounds Gemini retry/backoff and collects lightweight call stats.
- [src/utils/final_check.py](src/utils/final_check.py): runs log validation + pytest + pylint without LLM calls.

## 4) Runtime Configuration

### Environment Variables

- `GOOGLE_API_KEY`: required. Loaded from `.env` via `python-dotenv`.

The orchestrator refuses to run if the key is missing or still set to the placeholder value.

### Execution Parameters

- `--target_dir`: required CLI arg (directory containing the code to repair).

### Iteration Controls

In [main.py](main.py) the orchestrator runs up to:

- `MAX_ITERATIONS = 10`

and stops early when tests pass.

> Note: `MIN_PYLINT_SCORE` exists but is not currently used as a stop condition; pylint is tracked and logged.

## 5) Agents (Responsibilities and Contracts)

### 5.1 AuditorAgent (Code Analysis)

Location: [src/agents/auditor.py](src/agents/auditor.py)

Responsibilities:

- Discover Python files under the target directory.
- Run pylint for context (not as a strict gate).
- Ask the LLM to find logic bugs, edge cases, and runtime hazards.
- Produce a **structured** `RefactoringPlan` containing a list of `CodeIssue` items.

Key outputs:

- `RefactoringPlan.files_analyzed`: relative paths.
- `RefactoringPlan.issues`: list of `CodeIssue(file, line, issue_type, description, suggested_fix)`.
- `RefactoringPlan.priority_order`: file repair order.

Important constraint:

- The Auditor never writes files.

### 5.2 FixerAgent (Targeted Repairs)

Location: [src/agents/fixer.py](src/agents/fixer.py)

Responsibilities:

- For each file in the plan’s priority order, read the current code.
- Ask the LLM to apply minimal changes to address the listed issues.
- Write back the full fixed file.

Important constraints:

- **Sandbox restriction**: writes are performed via `write_file_safe()` which rejects paths outside `--target_dir`.
- Minimality: prompts explicitly forbid large refactors and new features.

### 5.3 JudgeAgent (Validation)

Location: [src/agents/judge.py](src/agents/judge.py)

Responsibilities:

- Generate a small deterministic pytest suite under `<target_dir>/_generated_tests/`.
- Run pytest (tests + runtime correctness).
- Run pylint (static quality signal).
- If tests fail: produce actionable failure analysis for the next iteration.

Deterministic test generation (no LLM dependency):

- The Judge contains `_deterministic_generated_tests()` which creates safe unit tests.
- For potentially non-terminating calls, tests run the target function in a separate process with a short timeout.

## 6) Tools and Security Boundaries

### 6.1 File Sandbox Enforcement

Location: [src/tools/file_tools.py](src/tools/file_tools.py)

All agent file operations should be done through:

- `read_file_safe(path, sandbox_dir)`
- `write_file_safe(path, content, sandbox_dir)`

These enforce that the resolved path is **inside** the sandbox directory (`--target_dir`).
If an agent attempts to access files outside, a `SandboxSecurityError` is raised.

### 6.2 Static + Test Runners

Location: [src/tools/analysis_tools.py](src/tools/analysis_tools.py)

- `run_pylint(target_dir, check_docstrings=True)` returns `PylintResult(score, output, counts..., success)`.
- `run_pytest(target_dir, tests_dir=None, source_dir=None)` returns `PytestResult(passed, failed, errors, output, success)`.

These run as subprocesses using the current Python interpreter (`sys.executable`).

## 7) Logging (Scientific Trace)

All agent LLM calls and key system events are logged to:

- `logs/experiment_data.json`

Logger implementation: [src/utils/logger.py](src/utils/logger.py)

Each entry contains:

- `id` (UUID), `timestamp`
- `agent`, `model`, `action`, `status`
- `details` including required fields:
  - `input_prompt`
  - `output_response`

The validator [src/utils/log_validator.py](src/utils/log_validator.py) ensures the file:

- is valid JSON,
- contains entries with required keys,
- includes `input_prompt` and `output_response` in `details`.

## 8) End-to-End Execution Flow

1. **Startup** ([main.py](main.py)):
	- Load `.env` (`GOOGLE_API_KEY`).
	- Ensure `logs/` exists.
	- Run initial pylint for baseline score.
2. **Iteration loop** (up to 10):
	- Auditor produces `RefactoringPlan`.
	- Fixer applies minimal edits when issues exist.
	- Judge generates tests (deterministic), runs pytest + pylint.
	- If tests pass → stop.
	- If tests fail → feed failure summary back into the next Auditor iteration.
3. **Shutdown**:
	- Print mission status and elapsed time.
	- Logs remain in `logs/experiment_data.json`.

## 9) How to Run

1. Install dependencies:

	- `pip install -r requirements.txt`

2. Configure `.env` with your key:

	- `GOOGLE_API_KEY="..."`

3. Run the swarm on a target directory:

	- `python main.py --target_dir ./sandbox`

4. (Optional) Run final validation checks (no LLM calls):

	- `python -m src.utils.final_check --target_dir ./sandbox`

## 10) Extension Points (If You Want to Evolve It)

This template is designed so you can extend capabilities without changing the core loop:

- Add more analyzers in the Auditor (e.g., AST-based checks) while keeping the same `RefactoringPlan` contract.
- Add repair “guards” in the Fixer (e.g., syntax check before writing).
- Expand deterministic tests in the Judge for additional common modules/exercises.

## 11) Known Limitations

- The system is only as good as the tests it runs. If there are no tests, `pytest` reports “No tests found” and the run may stop without proving correctness.
- LLM calls depend on external availability and quota; [src/utils/quota_manager.py](src/utils/quota_manager.py) reduces retry/backoff so failures surface quickly.
- Pylint is used as a quality signal but not a hard acceptance gate by default.
