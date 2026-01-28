import os
import json
from dotenv import load_dotenv
import google.generativeai as genai

from src.utils.logger import log_experiment, ActionType

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL_NAME = "models/gemini-pro"


def run_auditor(file_path: str):
    """
    Reads a Python file, analyzes it using Gemini,
    and logs the analysis for scientific evaluation.
    """

    # 1. Read source code
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()

    # 3. Build analysis prompt
    prompt = f"""
You are a static code auditor.

Return ONLY valid JSON using this structure:

{{
  "file": "{file_path}",
  "issues": [
    {{
      "type": "runtime_error | logic_error | bad_practice | style",
      "description": "Describe the issue clearly",
      "severity": "LOW | MEDIUM | HIGH"
    }}
  ]
}}

Rules:
- Do NOT fix the code
- Do NOT use markdown
- Do NOT include any text outside JSON
- Output MUST be valid JSON

CODE:
{code}
"""
    # 4. Call the LLM
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(prompt)
    raw_output = response.text.strip()

    # Parse JSON output
    try:
      json_start = raw_output.find("{")
      json_end = raw_output.rfind("}") + 1
      analysis_json = json.loads(raw_output[json_start:json_end])
      status = "SUCCESS"
    except Exception:
      analysis_json = {
        "file": file_path,
        "issues": [],
        "error": "Invalid JSON returned by LLM",
        "raw_output": raw_output
      }
      status = "FAILURE"


    # 5. Log the experiment (MANDATORY FORMAT)
    log_experiment(
        agent_name="Auditor",
        model_used="models/gemini-pro",
        action=ActionType.ANALYSIS,
        details={
            "input_prompt": prompt,
            "output_response": analysis_json
        },
        status=status
    )

    return analysis_json
