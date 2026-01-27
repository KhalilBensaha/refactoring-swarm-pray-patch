import argparse
import sys
import os
from dotenv import load_dotenv

from src.agents.auditor_agent import run_auditor
from src.agents.fixer_agent import fixer_agent

load_dotenv()

def list_python_files(target_dir):
    return [
        os.path.join(target_dir, f)
        for f in os.listdir(target_dir)
        if f.endswith(".py")
    ]

def main():
    parser = argparse.ArgumentParser(description="Refactoring Swarm")
    parser.add_argument("--target_dir", type=str, required=True)
    args = parser.parse_args()

    if not os.path.exists(args.target_dir):
        print(f"❌ Dossier {args.target_dir} introuvable.")
        sys.exit(1)

    python_files = list_python_files(args.target_dir)

    if not python_files:
        print("⚠️ No Python files found.")
        sys.exit(0)

    print("🚀 Starting Refactoring Swarm")
    print("Python files detected:")
    for file in python_files:
        print("-", file)

    print("\n🔍 Running Auditor on first file...\n")
    analysis_result = run_auditor(python_files[0])
    print(analysis_result)

    print("\n🛠 Running Fixer...\n")
    fixer_agent(analysis_result, args.target_dir)

    print("\n✅ Refactoring Swarm completed")

if __name__ == "__main__":
    main()
