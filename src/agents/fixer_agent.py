"""
Fixer Agent - Code Repair Specialist

The Fixer reads the Auditor's refactoring plan and applies MINIMAL fixes
to correct errors file by file. It avoids full rewrites unless absolutely necessary.
Uses ActionType.FIX for all LLM interactions.
"""

import os
import re
from typing import Dict, List, Optional
from dataclasses import dataclass

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.logger import log_experiment, ActionType
from src.utils.quota_manager import configure_gemini_retry, invoke_llm
from src.tools.file_tools import read_file_safe, write_file_safe, get_relative_path
from src.agents.auditor import RefactoringPlan, CodeIssue


@dataclass
class FixResult:
    """Result of fixing a single file."""
    file: str
    success: bool
    changes_made: int
    original_code: str
    fixed_code: str
    error_message: Optional[str] = None


class FixerAgent:
    """
    The Fixer Agent - Applies minimal fixes based on the Auditor's plan.
    
    This agent:
    1. Reads the refactoring plan from the Auditor
    2. Processes files in priority order
    3. Applies MINIMAL fixes (not full rewrites)
    4. Saves fixed code back to the sandbox
    """
    
    MODEL_NAME = "gemini-2.0-flash"
    AGENT_NAME = "Fixer_Agent"
    
    def __init__(self, sandbox_dir: str):
        """
        Initialize the Fixer Agent.
        
        Args:
            sandbox_dir: Path to the sandbox directory containing code to fix
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
        """Build the system prompt for the Fixer."""
        return """You are an expert Python Code Fixer. Your role is to apply MINIMAL, TARGETED fixes to Python code.

CRITICAL RULES:
1. Make the SMALLEST possible changes to fix the issues
2. Do NOT rewrite entire functions unless absolutely necessary
3. Preserve the original code structure and style
4. Fix only the specific issues mentioned
5. Do NOT add new features or refactor for style
6. Ensure the fixed code is syntactically correct
7. Do NOT change test files unless they have syntax errors

When fixing code:
- Fix logic errors
- Fix syntax errors
- Fix incorrect variable names or typos
- Fix incorrect operators or conditions
- Add missing imports if needed
- Fix indentation issues

OUTPUT FORMAT:
You must return ONLY the complete fixed Python code.
Do not include any explanations before or after the code.
Do not use markdown code blocks - just return the raw Python code.
The code must be complete and ready to save to a file."""
    
    def _build_fix_prompt(self, file_path: str, code: str, issues: List[CodeIssue]) -> str:
        """Build the fix prompt for a specific file."""
        relative_path = get_relative_path(file_path, self.sandbox_dir)
        
        issues_text = "\n".join([
            f"- Line {i.line or 'N/A'}: [{i.issue_type.upper()}] {i.description}\n  Suggested fix: {i.suggested_fix}"
            for i in issues
        ])
        
        return f"""Fix the following Python code based on the identified issues.

**File**: {relative_path}

**Issues to Fix**:
{issues_text}

**Original Code**:
```python
{code}
```

Apply MINIMAL fixes to address the issues listed above.
Return ONLY the complete fixed Python code, nothing else.
Do not include markdown code blocks or explanations."""
    
    def fix_file(self, file_path: str, issues: List[CodeIssue]) -> FixResult:
        """
        Fix a single Python file based on the issues identified.
        
        Args:
            file_path: Path to the Python file
            issues: List of issues to fix in this file
            
        Returns:
            FixResult with the outcome
        """
        relative_path = get_relative_path(file_path, self.sandbox_dir)
        
        try:
            original_code = read_file_safe(file_path, self.sandbox_dir)
        except Exception as e:
            return FixResult(
                file=relative_path,
                success=False,
                changes_made=0,
                original_code="",
                fixed_code="",
                error_message=f"Could not read file: {str(e)}"
            )
        
        # If no issues, skip
        if not issues:
            return FixResult(
                file=relative_path,
                success=True,
                changes_made=0,
                original_code=original_code,
                fixed_code=original_code,
                error_message=None
            )
        
        # Build prompts
        system_prompt = self._build_system_prompt()
        fix_prompt = self._build_fix_prompt(file_path, original_code, issues)
        input_prompt = f"{system_prompt}\n\n{fix_prompt}"
        
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=fix_prompt)
            ]
            response = invoke_llm(self.llm, messages)
            fixed_code = response.content
            
            # Clean up the response (remove markdown if present)
            fixed_code = self._clean_code_response(fixed_code)
            
            # Validate that we got actual Python code
            if not fixed_code.strip():
                raise ValueError("Empty response from LLM")
            
            # Log this interaction
            log_experiment(
                agent_name=self.AGENT_NAME,
                model_used=self.MODEL_NAME,
                action=ActionType.FIX,
                details={
                    "file_fixed": relative_path,
                    "input_prompt": input_prompt,
                    "output_response": fixed_code,
                    "issues_addressed": len(issues),
                    "original_length": len(original_code),
                    "fixed_length": len(fixed_code)
                },
                status="SUCCESS"
            )
            
            # Write the fixed code
            write_file_safe(file_path, fixed_code, self.sandbox_dir)
            
            # Count changes (simple line-by-line comparison)
            original_lines = set(original_code.strip().split('\n'))
            fixed_lines = set(fixed_code.strip().split('\n'))
            changes_made = len(original_lines.symmetric_difference(fixed_lines))
            
            return FixResult(
                file=relative_path,
                success=True,
                changes_made=changes_made,
                original_code=original_code,
                fixed_code=fixed_code,
                error_message=None
            )
            
        except Exception as e:
            log_experiment(
                agent_name=self.AGENT_NAME,
                model_used=self.MODEL_NAME,
                action=ActionType.FIX,
                details={
                    "file_fixed": relative_path,
                    "input_prompt": input_prompt,
                    "output_response": f"ERROR: {str(e)}",
                    "error": str(e)
                },
                status="FAILURE"
            )
            
            return FixResult(
                file=relative_path,
                success=False,
                changes_made=0,
                original_code=original_code,
                fixed_code=original_code,
                error_message=str(e)
            )
    
    def _clean_code_response(self, response: str) -> str:
        """Clean up the LLM response to extract pure Python code."""
        code = response.strip()
        
        # Remove markdown code blocks if present
        if code.startswith("```python"):
            code = code[9:]
        elif code.startswith("```"):
            code = code[3:]
        
        if code.endswith("```"):
            code = code[:-3]
        
        # Remove any leading/trailing explanation text
        lines = code.split('\n')
        
        # Find the first line that looks like Python code
        start_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if (stripped.startswith(('import ', 'from ', 'def ', 'class ', '#', '@', "'", '"')) or
                stripped == '' or
                '=' in stripped or
                stripped.startswith(('if ', 'for ', 'while ', 'try:', 'with '))):
                start_idx = i
                break
        
        return '\n'.join(lines[start_idx:]).strip()
    
    def run(self, plan: RefactoringPlan) -> Dict:
        """
        Run the complete fix process based on the Auditor's plan.
        
        Args:
            plan: The RefactoringPlan from the Auditor
            
        Returns:
            Dictionary with fix results
        """
        print(f"🔧 [FIXER] Starting code repairs based on {len(plan.issues)} identified issues")
        
        if not plan.issues:
            print("✅ [FIXER] No issues to fix!")
            return {
                "files_fixed": 0,
                "total_changes": 0,
                "results": [],
                "success": True
            }
        
        # Group issues by file
        issues_by_file = {}
        for issue in plan.issues:
            # Normalize the file path
            if os.path.isabs(issue.file):
                file_key = issue.file
            else:
                file_key = os.path.join(self.sandbox_dir, issue.file)
            
            if file_key not in issues_by_file:
                issues_by_file[file_key] = []
            issues_by_file[file_key].append(issue)
        
        # Process files in priority order
        results = []
        files_fixed = 0
        total_changes = 0
        
        for file_path in plan.priority_order:
            # Normalize path
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.sandbox_dir, file_path)
            
            if file_path not in issues_by_file:
                continue
            
            issues = issues_by_file[file_path]
            relative_path = get_relative_path(file_path, self.sandbox_dir)
            
            print(f"   🔨 Fixing: {relative_path} ({len(issues)} issues)")
            
            result = self.fix_file(file_path, issues)
            results.append(result)
            
            if result.success:
                files_fixed += 1
                total_changes += result.changes_made
                print(f"      ✅ Fixed with {result.changes_made} changes")
            else:
                print(f"      ❌ Failed: {result.error_message}")
        
        print(f"✅ [FIXER] Repair complete: {files_fixed} files fixed, {total_changes} total changes")
        
        return {
            "files_fixed": files_fixed,
            "total_changes": total_changes,
            "results": results,
            "success": files_fixed > 0 or len(plan.issues) == 0
        }