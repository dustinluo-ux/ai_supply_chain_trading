# Task 001 — Fix Gemini rotation model list in llm_bridge.py
type: fix
priority: medium
context_files: src/signals/llm_bridge.py
spec: |
  The following was architected by Claude Code. Execute exactly as defined.
  Reference docs/INDEX.md and maintain Evidence Discipline for this task.

  In src/signals/llm_bridge.py, locate the module-level constant `_ROTATION_MODELS`.
  It currently contains models that no longer exist on the project's Google API key:

    _ROTATION_MODELS = [
        "gemini-2.0-flash",
        "gemini-1.5-flash",        # 404 NOT_FOUND on this API key
        "gemini-1.5-flash-8b",     # 404 NOT_FOUND on this API key
    ]

  Replace it with the three models confirmed available via client.models.list():

    _ROTATION_MODELS = [
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ]

  No other changes. The rotation logic in `_call_gemini` is correct and must not be touched.

acceptance_criteria: |
  - _ROTATION_MODELS in src/signals/llm_bridge.py contains exactly:
      ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
  - No other lines in llm_bridge.py are modified
  - File is valid Python (no syntax errors)
output_file: handoffs/RESULT_001.md
