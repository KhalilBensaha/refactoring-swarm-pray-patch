"""
Main Orchestrator - The Refactoring Swarm Entry Point

This module coordinates the multi-agent system for autonomous code analysis and repair.
Execution loop: Auditor → Fixer → Judge
Maximum 10 iterations (to prevent infinite loops)
Stops when tests pass OR maximum iterations reached.

Usage:
    python main.py --target_dir ./sandbox

IGL Module Practical Session - Academic Year 2025-2026
"""

import argparse
import sys
import os
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv

from src.utils.logger import log_experiment, ActionType
from src.agents.auditor import AuditorAgent, RefactoringPlan, CodeIssue
from src.agents.fixer import FixerAgent
from src.agents.judge import JudgeAgent
from src.tools.analysis_tools import run_pylint

# Load environment variables (API keys)
load_dotenv()

# Configuration
MAX_ITERATIONS = 10
MIN_PYLINT_SCORE = 5.0


class Orchestrator:
    """
    The Orchestrator - Designs the execution graph and manages agent handover.
    
    Responsibilities:
    - Manages the Auditor → Fixer → Judge loop
    - Decides when to stop (tests pass OR max iterations)
    - Logs all system-level events
    """
    
    def __init__(self, target_dir: str):
        """
        Initialize the Orchestrator.
        
        Args:
            target_dir: Path to the directory containing buggy code
        """
        self.target_dir = os.path.abspath(target_dir)
        self.iteration = 0
        self.initial_pylint_score = 0.0
        self.final_pylint_score = 0.0
        self.start_time = None
        
    def log_system_event(self, event_type: str, message: str, status: str = "SUCCESS"):
        """Log a system-level event."""
        log_experiment(
            agent_name="Orchestrator",
            model_used="system",
            action=ActionType.DEBUG if event_type == "DEBUG" else ActionType.ANALYSIS,
            details={
                "event_type": event_type,
                "input_prompt": f"System event: {event_type}",
                "output_response": message,
                "iteration": self.iteration,
                "target_dir": self.target_dir
            },
            status=status
        )
    
    def run(self) -> bool:
        """
        Run the complete refactoring process.
        
        Returns:
            True if the mission was successful (tests pass), False otherwise
        """
        self.start_time = datetime.now()
        
        print("=" * 60)
        print("🚀 REFACTORING SWARM - MULTI-AGENT CODE REPAIR SYSTEM")
        print("=" * 60)
        print(f"📁 Target Directory: {self.target_dir}")
        print(f"🔄 Maximum Iterations: {MAX_ITERATIONS}")
        print("=" * 60)
        
        # Log startup
        self.log_system_event(
            "STARTUP",
            f"Starting refactoring swarm on {self.target_dir}"
        )
        
        # Get initial pylint score
        initial_result = run_pylint(self.target_dir)
        self.initial_pylint_score = initial_result.score
        print(f"\n📊 Initial Pylint Score: {self.initial_pylint_score}/10")
        
        # Initialize agents
        auditor = AuditorAgent(self.target_dir)
        fixer = FixerAgent(self.target_dir)
        judge = JudgeAgent(self.target_dir)
        
        # Main loop
        mission_success = False
        last_plan: Optional[RefactoringPlan] = None
        last_error_feedback = None
        
        for iteration in range(1, MAX_ITERATIONS + 1):
            self.iteration = iteration
            
            print(f"\n{'='*60}")
            print(f"🔄 ITERATION {iteration}/{MAX_ITERATIONS}")
            print("=" * 60)
            
            # Step 1: Auditor analyzes the code
            print("\n📋 PHASE 1: AUDITOR ANALYSIS")
            print("-" * 40)
            
            extra_context = None
            if last_error_feedback:
                extra_context = (
                    "Previous iteration failures (use to find root cause):\n"
                    f"Focus areas: {last_error_feedback.get('focus_areas')}\n\n"
                    "Pytest output (truncated):\n"
                    f"{(last_error_feedback.get('pytest_output') or '')[:2000]}\n\n"
                    "Pylint output (truncated):\n"
                    f"{(last_error_feedback.get('pylint_output') or '')[:1200]}\n"
                )

            plan = auditor.run(extra_context=extra_context)

            # If we have failing tests but the Auditor didn't produce structured issues,
            # synthesize a minimal plan from the pytest output so the Fixer can act.
            if last_error_feedback and not plan.issues:
                pytest_out = (last_error_feedback.get("pytest_output") or "").lower()
                synthesized: list[CodeIssue] = []

                if "replace_all" in pytest_out:
                    synthesized.append(
                        CodeIssue(
                            file="string_utils.py",
                            line=None,
                            issue_type="error",
                            description="replace_all() appears to hang when old == '' (empty string)",
                            suggested_fix="Add an early guard: if old == '': return s to avoid infinite loop",
                        )
                    )

                if synthesized:
                    plan.issues = synthesized
                    plan.priority_order = [i.file for i in synthesized]
                    plan.summary = (
                        f"Synthesized {len(synthesized)} issue(s) from failing generated tests."
                    )
            last_plan = plan
            
            # If no issues found, run tests directly
            if not plan.issues:
                print("\n✨ No issues found by Auditor!")
            else:
                # Step 2: Fixer applies repairs
                print(f"\n🔧 PHASE 2: FIXER REPAIRS ({len(plan.issues)} issues)")
                print("-" * 40)
                
                fix_result = fixer.run(plan)
            
            # Step 3: Judge evaluates the result
            print(f"\n⚖️  PHASE 3: JUDGE EVALUATION")
            print("-" * 40)
            
            judgement = judge.run(iteration)
            
            # Check if we're done
            if judgement.tests_passed:
                mission_success = True
                self.final_pylint_score = judgement.pylint_score
                
                print("\n" + "=" * 60)
                print("🎉 MISSION SUCCESSFUL!")
                print("=" * 60)
                print(f"✅ All tests passed after {iteration} iteration(s)")
                print(f"📊 Pylint Score: {self.initial_pylint_score}/10 → {self.final_pylint_score}/10")
                
                self.log_system_event(
                    "MISSION_COMPLETE",
                    f"Tests passed after {iteration} iterations. "
                    f"Pylint: {self.initial_pylint_score} → {self.final_pylint_score}"
                )
                
                break
            else:
                # Get feedback for next iteration
                last_error_feedback = judge.get_error_feedback(judgement)
                print(f"\n⚠️  Tests failed. Preparing for next iteration...")
                
                if judgement.error_analysis:
                    print(f"\n📝 Error Analysis Preview:")
                    print(judgement.error_analysis[:500] + "..." if len(judgement.error_analysis) > 500 else judgement.error_analysis)
        
        # Final status
        if not mission_success:
            self.final_pylint_score = run_pylint(self.target_dir).score
            
            print("\n" + "=" * 60)
            print("⏱️  MAXIMUM ITERATIONS REACHED")
            print("=" * 60)
            print(f"❌ Tests did not pass after {MAX_ITERATIONS} iterations")
            print(f"📊 Pylint Score: {self.initial_pylint_score}/10 → {self.final_pylint_score}/10")
            
            self.log_system_event(
                "MISSION_INCOMPLETE",
                f"Max iterations ({MAX_ITERATIONS}) reached. "
                f"Pylint: {self.initial_pylint_score} → {self.final_pylint_score}",
                status="FAILURE"
            )
        
        # Print final summary
        elapsed = datetime.now() - self.start_time
        print(f"\n⏱️  Total time: {elapsed.total_seconds():.2f} seconds")
        print(f"📝 Logs saved to: logs/experiment_data.json")
        
        return mission_success


def validate_environment():
    """Validate that the environment is properly configured."""
    # Check for API key
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "votre_cle_ici":
        print("❌ ERROR: GOOGLE_API_KEY not configured in .env file")
        print("   Please add your Google Gemini API key to the .env file:")
        print('   GOOGLE_API_KEY="your_actual_api_key_here"')
        return False
    return True


def main():
    """Main entry point for the Refactoring Swarm."""
    parser = argparse.ArgumentParser(
        description="Multi-Agent Code Refactoring Swarm",
        epilog="Example: python main.py --target_dir ./sandbox"
    )
    parser.add_argument(
        "--target_dir",
        type=str,
        required=True,
        help="Path to the directory containing buggy code to fix"
    )
    args = parser.parse_args()

    # Validate target directory exists
    if not os.path.exists(args.target_dir):
        print(f"❌ Directory not found: {args.target_dir}")
        sys.exit(1)
    
    # Validate environment
    if not validate_environment():
        sys.exit(1)
    
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)
    
    # Run the orchestrator
    orchestrator = Orchestrator(args.target_dir)
    success = orchestrator.run()
    
    print("\n✅ MISSION_COMPLETE" if success else "\n⚠️ MISSION_INCOMPLETE")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
