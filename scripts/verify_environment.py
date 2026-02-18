# Verify environment for deterministic parity + regression tests + Gemini readiness.
# Exit 0 if all critical libs present and (optional) Gemini API key check passes; exit 1 if any required check fails.
# Run from project root: python scripts/verify_environment.py
# Ref: INDEX.md, docs/GEMINI_ACTIVATION_PLAN.md; llm_bridge.py uses GOOGLE_API_KEY or GEMINI_API_KEY.
from __future__ import annotations

import os
import sys
from pathlib import Path

# Project root (script in scripts/)
_ROOT = Path(__file__).resolve().parent.parent


def _version(mod) -> str:
    return getattr(mod, "__version__", "?")


def _load_dotenv() -> None:
    """Load .env from project root if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
        env_path = _ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


def _check_gemini_api_key() -> tuple[bool, str]:
    """
    Check if Gemini API is configured (GOOGLE_API_KEY or GEMINI_API_KEY in env or .env).
    Returns (ok, message).
    """
    _load_dotenv()
    key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if key and isinstance(key, str) and key.strip() and not key.strip().lower().startswith(("your_", "xxx")):
        return True, "set (Gemini API ready)"
    return False, "not set or placeholder (set GOOGLE_API_KEY or GEMINI_API_KEY in .env for LLM bridge)"


def main() -> int:
    missing = []
    # Spine-critical: target_weight_pipeline -> SignalEngine -> technical_library, weight_model
    checks = [
        ("pandas", "pandas"),
        ("numpy", "numpy"),
        ("yaml", "PyYAML"),
        ("pandas_ta", "pandas-ta"),
        ("hmmlearn", "hmmlearn"),
    ]
    for module_name, display_name in checks:
        try:
            mod = __import__(module_name)
            print(f"  {display_name}: {_version(mod)}", flush=True)
        except ImportError as e:
            print(f"  {display_name}: MISSING ({e})", flush=True)
            missing.append(display_name)

    # Gemini-ready: google-genai and pydantic (ref: src/signals/llm_bridge.py)
    print("  ---", flush=True)
    for module_name, display_name in [("google.genai", "google-genai"), ("pydantic", "pydantic")]:
        try:
            mod = __import__(module_name)
            print(f"  {display_name}: {_version(mod)}", flush=True)
        except ImportError as e:
            print(f"  {display_name}: MISSING ({e})", flush=True)
            missing.append(display_name)

    # Gemini API key (informational; does not fail the script)
    gemini_ok, gemini_msg = _check_gemini_api_key()
    print(f"  Gemini API key (GOOGLE_API_KEY / GEMINI_API_KEY): {gemini_msg}", flush=True)

    if missing:
        print(f"\nERROR: Missing required packages: {', '.join(missing)}", flush=True)
        print("  pip install -r requirements.txt", flush=True)
        print("  For Gemini bridge: pip install google-genai pydantic", flush=True)
        print("  then re-run: python scripts/verify_environment.py", flush=True)
        return 1
    if not gemini_ok:
        print("\nEnvironment OK for parity/regression. Gemini bridge will use safety fallback until API key is set.", flush=True)
    else:
        print("\nEnvironment OK for parity, regression, and Gemini (LLM Active).", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
