# The Refactoring Swarm – Architecture

## Goal
The goal of this system is to automatically maintain Python code.
It takes buggy and badly written Python files as input and produces
a corrected version that passes unit tests without human intervention.

## Agents

### 1. Auditor Agent
The Auditor reads the source code and analyzes it.
It identifies bugs, bad practices, and potential risks.
It produces a refactoring plan but does not modify the code.

### 2. Fixer Agent
The Fixer reads the refactoring plan produced by the Auditor.
It applies minimal changes to the code to correct the detected issues.
All modifications are restricted to the sandbox directory.

### 3. Judge Agent
The Judge validates the corrected code.
It runs static analysis and unit tests.
If tests fail, it sends feedback to the Fixer.
If tests pass, the execution stops.

## Execution Flow
1. The system starts by reading Python files from the target directory.
2. The Auditor analyzes the code.
3. The Fixer applies corrections.
4. The Judge runs tests.
5. The process repeats until tests pass or the maximum number of iterations is reached.

## Stopping Conditions
- All tests pass successfully.
- The maximum number of iterations (10) is reached.
