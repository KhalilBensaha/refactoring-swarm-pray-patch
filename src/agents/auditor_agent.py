from langchain_google_genai import ChatGoogleGenerativeAI
from src.utils.logger import log_experiment, ActionType

def run_auditor(file_path: str):
    """
    Reads a Python file, analyzes it using Gemini,
    and logs the analysis for scientific evaluation.
    """

    # 1. Read source code
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()

    # 2. Initialize LLM (deterministic)
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=0
    )

    # 3. Build analysis prompt
    prompt = f"""
You are a software auditor.
Analyze the following Python code.

Your task:
- Identify bugs and logical errors
- Identify bad practices
- Identify potential runtime risks

Do NOT fix the code.
Do NOT generate new code.

Return a clear, structured analysis.

CODE:
{code}
"""

    # 4. Call the LLM
    response = llm.invoke(prompt)
    analysis_result = response.content

    # 5. Log the experiment (MANDATORY FORMAT)
    log_experiment(
        agent_name="Auditor",
        model_used="gemini-2.0-flash",
        action=ActionType.ANALYSIS,
        details={
            "input_prompt": prompt,
            "output_response": analysis_result
        },
        status="SUCCESS"
    )

    return analysis_result
