"""
Judge Agent - Test Execution and Validation Specialist

The Judge executes unit tests using pytest and evaluates code quality with pylint.
- If tests FAIL: Returns error logs for the Fixer (Self-Healing Loop)
- If tests PASS: Confirms the end of the mission

Uses ActionType.DEBUG for all analysis interactions.
"""

import os
from typing import Dict, Optional
from dataclasses import dataclass

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.logger import log_experiment, ActionType
from src.tools.analysis_tools import run_pylint, run_pytest, PylintResult, PytestResult


@dataclass
class JudgementResult:
    """Result of the Judge's evaluation."""
    tests_passed: bool
    pylint_score: float
    pytest_output: str
    pylint_output: str
    error_analysis: Optional[str]  # LLM analysis of failures
    recommendation: str  # "PASS" or "RETRY"
    summary: str


class JudgeAgent:
    """
    The Judge Agent - Executes tests and validates code quality.
    
    This agent:
    1. Runs pytest to execute unit tests
    2. Runs pylint to check code quality
    3. If tests fail, analyzes errors to help the Fixer
    4. If tests pass, confirms mission success
    """
    
    MODEL_NAME = "gemini-2.0-flash"
    AGENT_NAME = "Judge_Agent"
    
    def __init__(self, sandbox_dir: str):
        """
        Initialize the Judge Agent.
        
        Args:
            sandbox_dir: Path to the sandbox directory containing code to test
        """
        self.sandbox_dir = os.path.abspath(sandbox_dir)
        self.llm = ChatGoogleGenerativeAI(
            model=self.MODEL_NAME,
            temperature=0,  # Deterministic outputs as required
            convert_system_message_to_human=True
        )
    
    def _build_error_analysis_prompt(self, pytest_output: str, pylint_output: str) -> str:
        """Build a prompt for analyzing test failures."""
        return f"""Analyze the following test failures and provide a concise diagnosis.

**Pytest Output (Test Results)**:
```
{pytest_output[:3000]}
```

**Pylint Output (Code Quality)**:
```
{pylint_output[:2000]}
```

Based on these outputs, provide:
1. A brief summary of what went wrong
2. The most likely ROOT CAUSE of the failures
3. Specific recommendations for what the Fixer should focus on

Be concise and actionable. Focus on the MOST CRITICAL issues first."""
    
    def _analyze_failures(self, pytest_output: str, pylint_output: str) -> str:
        """
        Use LLM to analyze test failures and provide recommendations.
        
        Args:
            pytest_output: Output from pytest
            pylint_output: Output from pylint
            
        Returns:
            Analysis string with recommendations
        """
        system_prompt = """You are an expert Python debugger. Analyze test failures and code quality issues 
to provide actionable recommendations for fixing the code. Be concise and specific."""
        
        analysis_prompt = self._build_error_analysis_prompt(pytest_output, pylint_output)
        input_prompt = f"{system_prompt}\n\n{analysis_prompt}"
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=analysis_prompt)
            ]
            response = self.llm.invoke(messages)
            output_response = response.content
            
            # Log this interaction
            log_experiment(
                agent_name=self.AGENT_NAME,
                model_used=self.MODEL_NAME,
                action=ActionType.DEBUG,
                details={
                    "analysis_type": "failure_diagnosis",
                    "input_prompt": input_prompt,
                    "output_response": output_response
                },
                status="SUCCESS"
            )
            
            return output_response
            
        except Exception as e:
            log_experiment(
                agent_name=self.AGENT_NAME,
                model_used=self.MODEL_NAME,
                action=ActionType.DEBUG,
                details={
                    "analysis_type": "failure_diagnosis",
                    "input_prompt": input_prompt,
                    "output_response": f"ERROR: {str(e)}",
                    "error": str(e)
                },
                status="FAILURE"
            )
            return f"Could not analyze failures: {str(e)}"
    
    def run(self, iteration: int = 0) -> JudgementResult:
        """
        Run the complete judgement process.
        
        Args:
            iteration: Current iteration number for logging
            
        Returns:
            JudgementResult with test results and recommendations
        """
        print(f"⚖️  [JUDGE] Starting evaluation (iteration {iteration})")
        
        # Run pytest
        print("   🧪 Running pytest...")
        pytest_result = run_pytest(self.sandbox_dir)
        print(f"      Passed: {pytest_result.passed}, Failed: {pytest_result.failed}, Errors: {pytest_result.errors}")
        
        # Run pylint
        print("   📏 Running pylint...")
        pylint_result = run_pylint(self.sandbox_dir)
        print(f"      Score: {pylint_result.score}/10")
        
        # Determine if tests passed
        tests_passed = pytest_result.success and pytest_result.failed == 0 and pytest_result.errors == 0
        
        # Analyze failures if tests didn't pass
        error_analysis = None
        if not tests_passed:
            print("   🔍 Analyzing failures...")
            error_analysis = self._analyze_failures(pytest_result.output, pylint_result.output)
        
        # Determine recommendation
        if tests_passed:
            recommendation = "PASS"
            summary = (
                f"✅ All tests passed! "
                f"Pytest: {pytest_result.passed} passed. "
                f"Pylint score: {pylint_result.score}/10."
            )
        else:
            recommendation = "RETRY"
            summary = (
                f"❌ Tests failed. "
                f"Pytest: {pytest_result.passed} passed, {pytest_result.failed} failed, {pytest_result.errors} errors. "
                f"Pylint score: {pylint_result.score}/10. "
                f"Recommend another fix iteration."
            )
        
        # Log the judgement
        log_experiment(
            agent_name=self.AGENT_NAME,
            model_used=self.MODEL_NAME,
            action=ActionType.DEBUG,
            details={
                "iteration": iteration,
                "input_prompt": f"Evaluate code in {self.sandbox_dir}",
                "output_response": summary,
                "tests_passed": tests_passed,
                "pytest_passed": pytest_result.passed,
                "pytest_failed": pytest_result.failed,
                "pytest_errors": pytest_result.errors,
                "pylint_score": pylint_result.score,
                "recommendation": recommendation
            },
            status="SUCCESS" if tests_passed else "FAILURE"
        )
        
        print(f"⚖️  [JUDGE] Verdict: {recommendation}")
        
        return JudgementResult(
            tests_passed=tests_passed,
            pylint_score=pylint_result.score,
            pytest_output=pytest_result.output,
            pylint_output=pylint_result.output,
            error_analysis=error_analysis,
            recommendation=recommendation,
            summary=summary
        )
    
    def get_error_feedback(self, judgement: JudgementResult) -> Dict:
        """
        Package error feedback for the Fixer in the next iteration.
        
        Args:
            judgement: The JudgementResult from the current evaluation
            
        Returns:
            Dictionary with structured feedback for the Fixer
        """
        return {
            "needs_fix": not judgement.tests_passed,
            "pytest_output": judgement.pytest_output,
            "pylint_output": judgement.pylint_output,
            "error_analysis": judgement.error_analysis,
            "pylint_score": judgement.pylint_score,
            "focus_areas": self._extract_focus_areas(judgement)
        }
    
    def _extract_focus_areas(self, judgement: JudgementResult) -> list:
        """Extract specific areas that need attention."""
        areas = []
        
        if judgement.pytest_output:
            # Look for common error patterns
            output = judgement.pytest_output.lower()
            if 'assertionerror' in output:
                areas.append("Fix assertion failures - logic errors in code")
            if 'syntaxerror' in output:
                areas.append("Fix syntax errors - code cannot be parsed")
            if 'nameerror' in output:
                areas.append("Fix undefined variable references")
            if 'typeerror' in output:
                areas.append("Fix type mismatches in function calls")
            if 'attributeerror' in output:
                areas.append("Fix incorrect attribute access")
            if 'importerror' in output or 'modulenotfounderror' in output:
                areas.append("Fix import statements")
            if 'indentationerror' in output:
                areas.append("Fix indentation issues")
        
        if not areas:
            areas.append("Review test output for specific failure details")
        
        return areas