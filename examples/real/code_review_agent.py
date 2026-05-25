"""Code review agent: static analysis + LLM reviewer + retry on bad output.

Real-world shape:

    1. Read a Python file from disk
    2. Run a (cheap) static analyser to extract structural data
    3. Ask the LLM to review the code, given the analysis as grounding
    4. Validate the LLM's output is well-formed JSON
    5. Retry up to 3 times if validation fails

Why Reverie matters here
------------------------

The retry loop is THE common failure mode in LLM agents — bad JSON,
content filter blocks, malformed function calls. Reverie's anomaly
detector flags retry storms automatically, and the salience scorer
gives them high importance so they show up prominently in the 3D view
even at low zoom levels.

Setup
-----

    export NVIDIA_API_KEY=<your key>
    pip install openai httpx
    python code_review_agent.py path/to/your/code.py
"""

from __future__ import annotations

import ast
import json
import os
import sys
import time
from pathlib import Path

# Make ``reverie_emit`` importable when running from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reverie_emit import ReverieClient  # noqa: E402

from openai import OpenAI  # noqa: E402

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL = "bytedance/seed-oss-36b-instruct"
MAX_REVIEW_ATTEMPTS = 3


def static_analyse(source: str) -> dict:
    """Walk the AST and extract structural facts about the file."""

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return {"syntax_error": str(exc), "functions": [], "classes": [], "imports": []}

    functions: list[str] = []
    classes: list[str] = []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    return {
        "syntax_error": None,
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "loc": source.count("\n") + 1,
    }


def call_reviewer(
    client: OpenAI,
    rev: ReverieClient,
    *,
    parent_id: str,
    source: str,
    analysis: dict,
    attempt: int,
) -> tuple[bool, dict | None, int]:
    """One reviewer call. Returns (success, parsed_dict, tokens)."""

    prompt = (
        f"Review the following Python file and respond ONLY with a JSON "
        f"object of this exact shape:\n"
        f'{{"summary": "...", "issues": [{{"line": int, "severity": "low|medium|high", "message": "..."}}], "rating": int_1_to_10}}\n\n'
        f"Static analysis says: {json.dumps(analysis)}\n\n"
        f"Source code:\n```python\n{source[:6000]}\n```"
    )

    tool_id = rev.tool_called(
        f"{MODEL}.review",
        input={"attempt": attempt, "loc": analysis.get("loc", 0)},
        parent_id=parent_id,
    )
    started = time.time()
    try:
        completion = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=900,
        )
    except Exception as exc:
        rev.tool_returned(
            f"{MODEL}.review",
            output=None,
            latency_ms=(time.time() - started) * 1000,
            success=False,
            error_message=f"{type(exc).__name__}: {exc}",
            parent_id=tool_id,
        )
        return False, None, 0

    text = (completion.choices[0].message.content or "").strip()
    tokens = (
        getattr(completion.usage, "total_tokens", 0)
        if completion.usage
        else len(text.split())
    )

    rev.tool_returned(
        f"{MODEL}.review",
        output={"raw": text[:300]},
        latency_ms=(time.time() - started) * 1000,
        token_cost=int(tokens),
        parent_id=tool_id,
    )

    # Validation: is the output a valid JSON object with the right shape?
    val_id = rev.tool_called(
        "validate_json_schema",
        input={"raw_length": len(text)},
        parent_id=tool_id,
    )
    try:
        # Strip ```json fences if the model added them.
        cleaned = text
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").lstrip("json").strip()
        parsed = json.loads(cleaned)
        ok = (
            isinstance(parsed, dict)
            and isinstance(parsed.get("summary"), str)
            and isinstance(parsed.get("issues"), list)
            and isinstance(parsed.get("rating"), int)
        )
    except Exception as exc:
        rev.tool_returned(
            "validate_json_schema",
            output={"valid": False, "error": str(exc)},
            success=False,
            error_message=str(exc),
            parent_id=val_id,
        )
        return False, None, int(tokens)

    rev.tool_returned(
        "validate_json_schema",
        output={"valid": ok, "issue_count": len(parsed.get("issues", [])) if ok else 0},
        success=ok,
        parent_id=val_id,
    )
    return ok, parsed if ok else None, int(tokens)


def run(file_path: str) -> dict | None:
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        print("error: NVIDIA_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    p = Path(file_path)
    if not p.exists():
        print(f"error: file not found: {file_path}", file=sys.stderr)
        sys.exit(1)
    source = p.read_text(encoding="utf-8")

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=api_key)
    rev = ReverieClient(agent_id="code-review-bot", runtime="nvidia-nim")
    rev.start_run(goal=f"Review {p.name}")

    goal_id = rev.goal(f"Code-review file {p.name} ({source.count(chr(10)) + 1} lines)")

    # ---- Step 1: static analysis (cheap, deterministic).
    analyse_id = rev.tool_called(
        "static_analyse",
        input={"file": p.name},
        parent_id=goal_id,
    )
    started = time.time()
    analysis = static_analyse(source)
    rev.tool_returned(
        "static_analyse",
        output=analysis,
        latency_ms=(time.time() - started) * 1000,
        success=analysis.get("syntax_error") is None,
        error_message=analysis.get("syntax_error"),
        parent_id=analyse_id,
    )

    if analysis.get("syntax_error"):
        rev.goal_failed(parent_id=goal_id, reason=analysis["syntax_error"])
        rev.complete_run(status="failed")
        print("syntax error:", analysis["syntax_error"], file=sys.stderr)
        return None

    # ---- Step 2: LLM review with retry-on-validation-failure.
    parsed: dict | None = None
    for attempt in range(1, MAX_REVIEW_ATTEMPTS + 1):
        ok, result, tokens = call_reviewer(
            client,
            rev,
            parent_id=goal_id,
            source=source,
            analysis=analysis,
            attempt=attempt,
        )
        if ok:
            parsed = result
            break
        if attempt < MAX_REVIEW_ATTEMPTS:
            rev.retry(
                reason=f"validation failed on attempt {attempt}",
                attempt=attempt + 1,
                max_attempts=MAX_REVIEW_ATTEMPTS,
                parent_id=goal_id,
            )

    if parsed is None:
        rev.goal_failed(
            parent_id=goal_id,
            reason=f"reviewer failed validation in {MAX_REVIEW_ATTEMPTS} attempts",
        )
        rev.complete_run(status="failed")
        print("error: reviewer never produced valid JSON", file=sys.stderr)
        return None

    rev.reflection(
        insight=(
            f"Review complete: rating {parsed['rating']}/10, "
            f"{len(parsed['issues'])} issues found"
        ),
        parent_id=goal_id,
    )
    rev.goal_completed(
        parent_id=goal_id, outcome=f"Rating {parsed['rating']}/10"
    )
    rev.complete_run()
    rev.close()

    print("\n========== REVIEW ==========\n")
    print(json.dumps(parsed, indent=2))
    print("\n============================\n")
    print(f"[reverie] run id: {rev.run_id}")
    print(f"[reverie] view at: http://localhost:3000/run?id={rev.run_id}")
    return parsed


if __name__ == "__main__":
    file_path = sys.argv[1] if len(sys.argv) > 1 else __file__
    run(file_path)
