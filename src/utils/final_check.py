"""Final checks before submission.

Run:
  python -m src.utils.final_check --target_dir ./sandbox

This will:
- validate logs/experiment_data.json structure
- run pytest on the target directory
- run pylint on the target directory

It does NOT call the LLM.
"""

from __future__ import annotations

import argparse
import sys

from src.tools.analysis_tools import run_pylint, run_pytest
from src.utils.log_validator import validate_log_file


def run_final_checks(target_dir: str) -> bool:
    print("=" * 60)
    print("🔍 FINAL VALIDATION CHECKS")
    print("=" * 60)

    ok = True

    print("\n1️⃣ Log validation")
    valid, err = validate_log_file()
    if valid:
        print("   ✅ logs/experiment_data.json is valid")
    else:
        print(f"   ❌ Log validation failed: {err}")
        ok = False

    print("\n2️⃣ Pytest")
    pytest_result = run_pytest(target_dir)
    print(f"   Passed: {pytest_result.passed}, Failed: {pytest_result.failed}, Errors: {pytest_result.errors}")
    if not pytest_result.success or pytest_result.failed != 0 or pytest_result.errors != 0:
        print("   ❌ Pytest is not fully passing")
        ok = False
    else:
        print("   ✅ All tests passed")

    print("\n3️⃣ Pylint")
    pylint_result = run_pylint(target_dir)
    print(f"   Score: {pylint_result.score}/10")
    if pylint_result.errors != 0:
        print("   ❌ Pylint has errors")
        ok = False
    else:
        print("   ✅ No pylint errors")

    print("\n" + "=" * 60)
    if ok:
        print("🎉 ALL CHECKS PASSED")
    else:
        print("❌ SOME CHECKS FAILED")
    print("=" * 60)

    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Final TP validation checks")
    parser.add_argument(
        "--target_dir",
        type=str,
        default="./sandbox",
        help="Directory to run pytest/pylint against (default: ./sandbox)",
    )
    args = parser.parse_args()

    success = run_final_checks(args.target_dir)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
