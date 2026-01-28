"""
Analysis Tools - Interfaces for pylint and pytest.
Manages the interfaces to the analysis (pylint) and testing (pytest) tools.
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class PylintResult:
    """Result from pylint analysis."""
    score: float
    output: str
    errors: int
    warnings: int
    conventions: int
    refactors: int
    success: bool


@dataclass
class PytestResult:
    """Result from pytest execution."""
    passed: int
    failed: int
    errors: int
    output: str
    success: bool


def run_pylint(target_dir: str) -> PylintResult:
    """
    Run pylint on all Python files in the target directory.
    
    Args:
        target_dir: Directory containing Python files to analyze
        
    Returns:
        PylintResult with score and details
    """
    target_path = Path(target_dir).resolve()
    
    if not target_path.exists():
        return PylintResult(
            score=0.0,
            output=f"Directory not found: {target_dir}",
            errors=0,
            warnings=0,
            conventions=0,
            refactors=0,
            success=False
        )
    
    # Find all Python files (excluding test files for code quality check)
    py_files = [str(f) for f in target_path.rglob("*.py") if not f.name.startswith("test_")]
    
    if not py_files:
        return PylintResult(
            score=10.0,
            output="No Python files to analyze",
            errors=0,
            warnings=0,
            conventions=0,
            refactors=0,
            success=True
        )
    
    try:
        # Run pylint with parseable output
        result = subprocess.run(
            [
                sys.executable, "-m", "pylint",
                "--output-format=text",
                "--score=y",
                "--disable=C0114,C0115,C0116",  # Disable missing docstring warnings
                *py_files
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(target_path)
        )
        
        output = result.stdout + result.stderr
        
        # Parse the score from output
        score = 0.0
        errors = warnings = conventions = refactors = 0
        
        for line in output.split('\n'):
            if 'Your code has been rated at' in line:
                try:
                    # Extract score like "Your code has been rated at 7.50/10"
                    score_part = line.split('rated at')[1].split('/')[0].strip()
                    score = float(score_part)
                except (IndexError, ValueError):
                    score = 0.0
            elif line.startswith('E:') or ': E' in line:
                errors += 1
            elif line.startswith('W:') or ': W' in line:
                warnings += 1
            elif line.startswith('C:') or ': C' in line:
                conventions += 1
            elif line.startswith('R:') or ': R' in line:
                refactors += 1
        
        return PylintResult(
            score=score,
            output=output,
            errors=errors,
            warnings=warnings,
            conventions=conventions,
            refactors=refactors,
            success=True
        )
        
    except subprocess.TimeoutExpired:
        return PylintResult(
            score=0.0,
            output="Pylint timed out",
            errors=0,
            warnings=0,
            conventions=0,
            refactors=0,
            success=False
        )
    except Exception as e:
        return PylintResult(
            score=0.0,
            output=f"Pylint error: {str(e)}",
            errors=0,
            warnings=0,
            conventions=0,
            refactors=0,
            success=False
        )


def run_pytest(target_dir: str) -> PytestResult:
    """
    Run pytest on the target directory.
    
    Args:
        target_dir: Directory containing test files
        
    Returns:
        PytestResult with pass/fail counts and output
    """
    target_path = Path(target_dir).resolve()
    
    if not target_path.exists():
        return PytestResult(
            passed=0,
            failed=0,
            errors=1,
            output=f"Directory not found: {target_dir}",
            success=False
        )
    
    # Check if there are any test files
    test_files = list(target_path.rglob("test_*.py"))
    if not test_files:
        return PytestResult(
            passed=0,
            failed=0,
            errors=0,
            output="No test files found (test_*.py)",
            success=True  # No tests means nothing failed
        )
    
    try:
        # Run pytest with verbose output
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                str(target_path),
                "-v",
                "--tb=short",
                "-q"
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(target_path)
        )
        
        output = result.stdout + result.stderr
        
        # Parse pytest output for pass/fail counts
        passed = failed = errors = 0
        
        for line in output.split('\n'):
            line_lower = line.lower()
            # Look for summary line like "5 passed, 2 failed"
            if 'passed' in line_lower or 'failed' in line_lower or 'error' in line_lower:
                parts = line.split()
                for i, part in enumerate(parts):
                    if 'passed' in part.lower() and i > 0:
                        try:
                            passed = int(parts[i-1])
                        except ValueError:
                            pass
                    elif 'failed' in part.lower() and i > 0:
                        try:
                            failed = int(parts[i-1])
                        except ValueError:
                            pass
                    elif 'error' in part.lower() and i > 0:
                        try:
                            errors = int(parts[i-1])
                        except ValueError:
                            pass
        
        # Check return code for overall success
        all_passed = result.returncode == 0
        
        return PytestResult(
            passed=passed,
            failed=failed,
            errors=errors,
            output=output,
            success=all_passed
        )
        
    except subprocess.TimeoutExpired:
        return PytestResult(
            passed=0,
            failed=0,
            errors=1,
            output="Pytest timed out after 120 seconds",
            success=False
        )
    except Exception as e:
        return PytestResult(
            passed=0,
            failed=0,
            errors=1,
            output=f"Pytest error: {str(e)}",
            success=False
        )


def get_code_quality_summary(target_dir: str) -> Dict:
    """
    Get a comprehensive code quality summary.
    
    Args:
        target_dir: Directory to analyze
        
    Returns:
        Dictionary with pylint and pytest results
    """
    pylint_result = run_pylint(target_dir)
    pytest_result = run_pytest(target_dir)
    
    return {
        "pylint": {
            "score": pylint_result.score,
            "errors": pylint_result.errors,
            "warnings": pylint_result.warnings,
            "success": pylint_result.success
        },
        "pytest": {
            "passed": pytest_result.passed,
            "failed": pytest_result.failed,
            "errors": pytest_result.errors,
            "success": pytest_result.success
        },
        "overall_success": pytest_result.success and pylint_result.score >= 5.0
    }
