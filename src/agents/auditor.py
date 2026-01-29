"""
Auditor Agent - Code Analysis Specialist

The Auditor reads Python code, performs static analysis to identify:
- Logic errors
- Bad practices  
- Code smells
- Potential bugs

It produces a STRUCTURED REFACTORING PLAN but does NOT modify any code.
Uses ActionType.ANALYSIS for all LLM interactions.
"""

import os
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.logger import log_experiment, ActionType
from src.utils.quota_manager import configure_gemini_retry, invoke_llm
from src.tools.file_tools import read_file_safe, list_python_files, get_relative_path
from src.tools.analysis_tools import run_pylint


@dataclass
class CodeIssue:
    """Represents a single code issue found by the Auditor."""
    file: str
    line: Optional[int]
    issue_type: str  # "error", "warning", "convention", "refactor"
    description: str
    suggested_fix: str


@dataclass
class RefactoringPlan:
    """The structured plan produced by the Auditor."""
    files_analyzed: List[str] = field(default_factory=list)
    issues: List[CodeIssue] = field(default_factory=list)
    pylint_score_before: float = 0.0
    summary: str = ""
    priority_order: List[str] = field(default_factory=list)  # Files to fix in order


class AuditorAgent:
    """
    The Auditor Agent - Performs static analysis and produces refactoring plans.
    
    This agent:
    1. Reads all Python files in the target directory
    2. Runs pylint for initial analysis
    3. Uses Gemini LLM to understand and analyze code
    4. Produces a structured refactoring plan
    5. Does NOT modify any code
    """
    
    MODEL_NAME = "gemini-2.0-flash"
    AGENT_NAME = "Auditor_Agent"
    
    def __init__(self, sandbox_dir: str):
        """
        Initialize the Auditor Agent.
        
        Args:
            sandbox_dir: Path to the sandbox directory containing code to analyze
        """
        self.sandbox_dir = os.path.abspath(sandbox_dir)
        # Reduce long retry/backoff behavior on quota errors.
        configure_gemini_retry()
        self.llm = ChatGoogleGenerativeAI(
            model=self.MODEL_NAME,
            temperature=0,  # Deterministic outputs as required
            convert_system_message_to_human=True
        )
    
    def _build_system_prompt(self) -> str:
        """Build the system prompt for the Auditor."""
        return """You are an expert Python Code Auditor. Your role is to find ALL bugs in Python code.

Look for these common bugs:
1. **Wrong operators**: + instead of -, == instead of !=, etc.
2. **Missing edge cases**: empty list, zero, negative numbers, empty string
3. **Infinite loops**: while loops that never terminate (e.g., replacing empty string)
4. **Off-by-one errors**: wrong range bounds, wrong slice indices
5. **Missing return statements** or returning wrong values
6. **Unhandled exceptions**: division by zero, index out of range
7. **Syntax errors**: indentation, missing colons, undefined variables

You MUST output issues in this EXACT format (one per issue, separated by ---):

FILE: <filename>
LINE: <line_number or N/A>
TYPE: error
ISSUE: <description of the bug>
FIX: <exact code change needed>
---

Be AGGRESSIVE - if the code could fail for ANY input, report it as an error.
Do NOT say "no issues found" - look harder for edge cases and logic bugs."""
    
    def _build_analysis_prompt(
        self,
        file_path: str,
        code: str,
        pylint_output: str,
        extra_context: Optional[str] = None,
    ) -> str:
        """Build the analysis prompt for a specific file."""
        relative_path = get_relative_path(file_path, self.sandbox_dir)

        extra = ""
        if extra_context:
            extra = (
                "\n\n**Additional runtime/test feedback (use this to find root causes)**:\n"
                f"```\n{extra_context[:2500]}\n```\n"
            )
        
        return f"""Analyze the following Python code and identify all issues.

**File**: {relative_path}

**Pylint Output for context**:
```
{pylint_output[:2000]}  # Truncate if too long
```
{extra}

**Code to Analyze**:
```python
{code}
```

Identify ALL issues in this code. Focus on:
1. Syntax errors that would prevent execution
2. Logic bugs that would cause incorrect behavior
3. Bad practices that violate Python conventions
4. Potential runtime errors

Provide your analysis in the structured format specified."""
    
    def analyze_file(self, file_path: str, pylint_output: str, extra_context: Optional[str] = None) -> List[CodeIssue]:
        """
        Analyze a single Python file.
        
        Args:
            file_path: Path to the Python file
            pylint_output: Pylint output for context
            
        Returns:
            List of CodeIssue objects
        """
        issues = []
        
        try:
            code = read_file_safe(file_path, self.sandbox_dir)
        except Exception as e:
            return [CodeIssue(
                file=file_path,
                line=None,
                issue_type="error",
                description=f"Could not read file: {str(e)}",
                suggested_fix="Check file permissions and encoding"
            )]
        
        # Skip empty files
        if not code.strip():
            return []
        
        # Build prompts
        system_prompt = self._build_system_prompt()
        analysis_prompt = self._build_analysis_prompt(
            file_path,
            code,
            pylint_output,
            extra_context=extra_context,
        )
        
        # Call the LLM
        input_prompt = f"{system_prompt}\n\n{analysis_prompt}"
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=analysis_prompt)
            ]
            response = invoke_llm(self.llm, messages)
            output_response = response.content
            
            # Log this interaction
            log_experiment(
                agent_name=self.AGENT_NAME,
                model_used=self.MODEL_NAME,
                action=ActionType.ANALYSIS,
                details={
                    "file_analyzed": get_relative_path(file_path, self.sandbox_dir),
                    "input_prompt": input_prompt,
                    "output_response": output_response,
                    "code_length": len(code)
                },
                status="SUCCESS"
            )
            
            # Parse the response into CodeIssue objects
            issues = self._parse_llm_response(output_response, file_path)
            
        except Exception as e:
            log_experiment(
                agent_name=self.AGENT_NAME,
                model_used=self.MODEL_NAME,
                action=ActionType.ANALYSIS,
                details={
                    "file_analyzed": get_relative_path(file_path, self.sandbox_dir),
                    "input_prompt": input_prompt,
                    "output_response": f"ERROR: {str(e)}",
                    "error": str(e)
                },
                status="FAILURE"
            )
            issues = [CodeIssue(
                file=file_path,
                line=None,
                issue_type="error",
                description=f"LLM analysis failed: {str(e)}",
                suggested_fix="Retry analysis"
            )]
        
        return issues
    
    def _parse_llm_response(self, response: str, default_file: str) -> List[CodeIssue]:
        """Parse the LLM response into CodeIssue objects."""
        issues = []
        
        # Split by issue separator (handle various formats)
        issue_blocks = re.split(r'---+|\n\n(?=FILE:)', response)
        
        for block in issue_blocks:
            block = block.strip()
            if not block or 'no issues' in block.lower():
                continue
            
            # Parse each field
            file_name = default_file
            line = None
            issue_type = "error"  # Default to error to ensure Fixer acts
            description = ""
            fix = ""
            
            for line_text in block.split('\n'):
                line_text = line_text.strip()
                line_upper = line_text.upper()
                
                if line_upper.startswith('FILE:'):
                    file_name = line_text[5:].strip()
                elif line_upper.startswith('LINE:'):
                    line_str = line_text[5:].strip()
                    # Extract first number found
                    nums = re.findall(r'\d+', line_str)
                    if nums:
                        line = int(nums[0])
                elif line_upper.startswith('TYPE:'):
                    issue_type = line_text[5:].strip().lower()
                elif line_upper.startswith('ISSUE:'):
                    description = line_text[6:].strip()
                elif line_upper.startswith('FIX:'):
                    fix = line_text[4:].strip()
                elif line_upper.startswith('SUGGESTED FIX:'):
                    fix = line_text[14:].strip()
            
            # Also try to extract from unstructured text if no description found
            if not description and ('bug' in block.lower() or 'error' in block.lower()):
                description = block[:200]
                issue_type = "error"
            
            if description:  # Only add if we have a description
                issues.append(CodeIssue(
                    file=file_name,
                    line=line,
                    issue_type=issue_type,
                    description=description,
                    suggested_fix=fix
                ))
        
        return issues
    
    def run(self, extra_context: Optional[str] = None) -> RefactoringPlan:
        """
        Run the complete audit process.
        
        Returns:
            RefactoringPlan with all issues and recommendations
        """
        print(f"🔍 [AUDITOR] Starting code analysis in: {self.sandbox_dir}")
        
        # Get initial pylint score
        pylint_result = run_pylint(self.sandbox_dir)
        print(f"📊 [AUDITOR] Initial Pylint score: {pylint_result.score}/10")
        
        # List all Python files (exclude tests; we fix source, not tests)
        all_python_files = list_python_files(self.sandbox_dir)
        python_files = [f for f in all_python_files if not os.path.basename(f).startswith('test_')]

        if not python_files:
            print("⚠️ [AUDITOR] No source Python files found to analyze")
            return RefactoringPlan(
                files_analyzed=[],
                issues=[],
                pylint_score_before=pylint_result.score,
                summary="No source Python files found in the target directory",
                priority_order=[]
            )

        excluded_tests = len(all_python_files) - len(python_files)
        print(f"📁 [AUDITOR] Found {len(python_files)} source file(s) to analyze (excluding {excluded_tests} test files)")
        
        # Analyze each file
        all_issues = []
        files_analyzed = []
        
        for file_path in python_files:
            relative_path = get_relative_path(file_path, self.sandbox_dir)
            print(f"   📄 Analyzing: {relative_path}")
            
            issues = self.analyze_file(file_path, pylint_result.output, extra_context=extra_context)
            all_issues.extend(issues)
            files_analyzed.append(relative_path)
        
        # Determine priority order (files with most/critical issues first)
        file_issue_count = {}
        for issue in all_issues:
            rel_file = get_relative_path(issue.file, self.sandbox_dir)
            if rel_file not in file_issue_count:
                file_issue_count[rel_file] = {"errors": 0, "total": 0}
            file_issue_count[rel_file]["total"] += 1
            if issue.issue_type == "error":
                file_issue_count[rel_file]["errors"] += 1
        
        # Sort by errors first, then total issues
        priority_order = sorted(
            file_issue_count.keys(),
            key=lambda f: (file_issue_count[f]["errors"], file_issue_count[f]["total"]),
            reverse=True
        )
        
        # Create summary
        error_count = sum(1 for i in all_issues if i.issue_type == "error")
        warning_count = sum(1 for i in all_issues if i.issue_type == "warning")
        
        summary = (
            f"Analyzed {len(files_analyzed)} files. "
            f"Found {len(all_issues)} issues: {error_count} errors, {warning_count} warnings. "
            f"Pylint score: {pylint_result.score}/10."
        )
        
        print(f"✅ [AUDITOR] Analysis complete: {summary}")
        
        return RefactoringPlan(
            files_analyzed=files_analyzed,
            issues=all_issues,
            pylint_score_before=pylint_result.score,
            summary=summary,
            priority_order=priority_order
        )
