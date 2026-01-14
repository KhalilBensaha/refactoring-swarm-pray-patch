import argparse
import sys
import os
from dotenv import load_dotenv
##from src.utils.logger import log_experiment
from src.agents.auditor_agent import run_auditor

load_dotenv()

def parse_arguments():
    parser = argparse.ArgumentParser(description="Refactoring Swarm")
    parser.add_argument(
        "--target_dir",
        type=str,
        required=True,
        help="Directory containing Python files"
    )
    return parser.parse_args()

def list_python_files(target_dir):
    python_files = []
    for filename in os.listdir(target_dir):
        if filename.endswith(".py"):
            python_files.append(os.path.join(target_dir, filename))
    return python_files

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target_dir", type=str, required=True)
    args = parser.parse_args()

    if not os.path.exists(args.target_dir):
        print(f"❌ Dossier {args.target_dir} introuvable.")
        sys.exit(1)

    print(f"🚀 DEMARRAGE SUR : {args.target_dir}")
    ##log_experiment("System", "STARTUP", f"Target: {args.target_dir}", "INFO")
    print("✅ MISSION_COMPLETE")

    python_files = list_python_files(args.target_dir)

    if not python_files:
        print("⚠️ No Python files found.")
        sys.exit(0)

    

    print("🚀 Starting Refactoring Swarm")
    print("Python files detected:")
    for file in python_files:
        print("-", file)

    print("\n🔍 Running Auditor on first file...\n")
    result = run_auditor(python_files[0])
    print(result)


if __name__ == "__main__":
    main()