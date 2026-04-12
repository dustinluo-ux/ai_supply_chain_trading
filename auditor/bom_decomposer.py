"""
Auditor — BOM Decomposer
Port of alpha_scout/src/excavation/bom_decomposer.py.
Extracts physical/technological components from bottleneck description via Gemini.
Returns list[str]; no Pydantic. Config from auditor_config.yaml.
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path

import yaml
from google import genai

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "auditor_config.yaml"


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _cfg = _load_config()
        api_key = os.environ.get(
            _cfg.get("gemini_api_key_env", "GEMINI_API_KEY"), ""
        )
        _client = genai.Client(api_key=api_key)
    return _client


_SYSTEM_PROMPT = """
You are a supply chain engineer and materials scientist.
Given a technology bottleneck description, extract the key physical components,
materials, or manufacturing subsystems required to address this bottleneck.

Return ONLY a JSON array of strings. Each string is a specific component name.
Example: ["solid-state electrolyte", "lithium metal anode", "dry-room equipment"]

Rules:
- Return 3 to 10 components
- Be specific and technically precise (no generic terms like "research" or "capital")
- Prefer materials, subsystems, and equipment names
- Return only the JSON array — no explanation, no markdown fences
"""


class BOMDecompositionError(Exception):
    """Raised when BOM decomposition fails (API, parse, or empty input)."""


def _strip_json_fences(text: str) -> str:
    """Remove optional ```json ... ``` or ``` ... ``` wrapper before parsing."""
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


async def decompose_bottleneck(bottleneck_description: str) -> list[str]:
    """
    Extract required components from a bottleneck description using Gemini.

    Args:
        bottleneck_description: Natural language description of a technology bottleneck.

    Returns:
        List of 3–10 component strings.

    Raises:
        BOMDecompositionError: On API failure, empty input, or JSON parse error.
    """
    if not bottleneck_description.strip():
        raise BOMDecompositionError("bottleneck_description is empty")

    _cfg = _load_config()
    model = _cfg.get("gemini_model", "gemini-2.0-flash")

    try:
        prompt = (
            f"{_SYSTEM_PROMPT.strip()}\n\nBottleneck:\n{bottleneck_description}"
        )
        response = await asyncio.to_thread(
            _get_client().models.generate_content,
            model=model,
            contents=prompt,
        )
        raw = response.text.strip()
        cleaned = _strip_json_fences(raw)
        components = json.loads(cleaned)
        if not isinstance(components, list) or any(
            not isinstance(c, str) for c in components
        ):
            raise BOMDecompositionError(
                "Gemini response was not a list of strings"
            )
        result = [c.strip() for c in components if c.strip()]
        logger.info(
            "decompose_bottleneck: extracted %d components for bottleneck='%.60s'",
            len(result),
            bottleneck_description,
        )
        return result
    except BOMDecompositionError:
        raise
    except Exception as exc:
        logger.error(
            "decompose_bottleneck: %s — %s",
            type(exc).__name__,
            exc,
        )
        raise BOMDecompositionError(
            f"BOM decomposition failed: {type(exc).__name__}: {exc}"
        ) from exc
