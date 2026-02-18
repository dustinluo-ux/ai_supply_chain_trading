"""
Gemini Intelligence Bridge — gated deep analysis for NewsEngine.

Uses Google Gemini (google-genai) for sentiment, category, and upstream/downstream
entity extraction. API key from GOOGLE_API_KEY (or GEMINI_API_KEY). No imports from legacy/.
Design: docs/GEMINI_BRIDGE_DESIGN.md
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Literal

logger = logging.getLogger(__name__)

# Optional: pydantic for structured output
try:
    from pydantic import BaseModel

    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    BaseModel = None  # type: ignore

# Optional: google-genai (new SDK)
try:
    from google import genai
    from google.genai import types

    GENAI_AVAILABLE = True
except ImportError:
    genai = None
    types = None
    GENAI_AVAILABLE = False
    logger.warning(
        "google-genai not installed. LLM bridge will return None. Run: pip install google-genai"
    )


# ---------------------------------------------------------------------------
# Pydantic output schema (canonical contract)
# ---------------------------------------------------------------------------
if HAS_PYDANTIC and BaseModel is not None:

    class DeepAnalysisOutput(BaseModel):
        sentiment: float  # -1.0 to 1.0
        category: Literal[
            "SUPPLY_CHAIN_DISRUPTION",
            "DEMAND_SHOCK",
            "M&A",
            "MACRO",
        ]
        relationships: dict[str, list[str]]  # "upstream": [...], "downstream": [...]
        reasoning: str

else:
    DeepAnalysisOutput = None  # type: ignore


class GeminiAnalyzer:
    """
    Bridge to Google Gemini for gated deep analysis (sentiment, category, upstream/downstream).
    API key from arg or GOOGLE_API_KEY / GEMINI_API_KEY env. Model from arg or config.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        if not GENAI_AVAILABLE or genai is None:
            raise ImportError(
                "google-genai is required for GeminiAnalyzer. pip install google-genai"
            )
        if not HAS_PYDANTIC or DeepAnalysisOutput is None:
            raise ImportError("pydantic is required for GeminiAnalyzer. pip install pydantic")

        self._api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not self._api_key:
            raise ValueError(
                "Gemini API key not found. Set GOOGLE_API_KEY or GEMINI_API_KEY in .env"
            )

        self._model = model or self._model_from_config()
        self._client = genai.Client(api_key=self._api_key)
        logger.info("GeminiAnalyzer initialized with model=%s", self._model)

    def _model_from_config(self) -> str:
        try:
            from src.utils.config_manager import get_config

            return str(
                get_config().get_param("strategy_params.llm_analysis.model", "gemini-2.0-flash")
            )
        except Exception:
            return "gemini-2.0-flash"

    def _build_prompt(self, headline: str, text: str) -> str:
        """
        Build prompt for sentiment, category, upstream/downstream entities, and reasoning.
        Adapted from legacy gemini_news_analyzer _create_supply_chain_prompt; extended
        with upstream/downstream entity lists per GEMINI_BRIDGE_DESIGN.md.
        """
        combined = f"Headline: {headline}\n\n{text}".strip()
        if len(combined) > 12000:
            combined = combined[:12000] + "..."
        return f"""You are a Supply Chain Quant. Analyze this news and return ONLY valid JSON.

{combined}

Extract:
1. sentiment: float from -1.0 (negative) to 1.0 (positive), 0 = neutral.
2. category: one of "SUPPLY_CHAIN_DISRUPTION", "DEMAND_SHOCK", "M&A", "MACRO".
3. relationships: two lists — "upstream" (suppliers, input providers) and "downstream" (customers, output recipients). Use company or product names mentioned in the article. Empty list if none.
4. reasoning: brief explanation (max 20 words).

Return ONLY this JSON object, no markdown:
{{
  "sentiment": 0.0,
  "category": "MACRO",
  "relationships": {{ "upstream": [], "downstream": [] }},
  "reasoning": ""
}}"""

    def _call_gemini(self, prompt: str) -> str:
        """Call Gemini with JSON response; return raw JSON string. Proxy bypass per legacy."""
        proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
        saved = {v: os.environ.pop(v, None) for v in proxy_vars}
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                    max_output_tokens=1024,
                ),
            )
            out = getattr(response, "text", None) or ""
            if not out and getattr(response, "candidates", None):
                cand = response.candidates[0] if response.candidates else None
                if cand and getattr(cand, "content", None) and getattr(cand.content, "parts", None) and cand.content.parts:
                    out = getattr(cand.content.parts[0], "text", None) or ""
            out = (out or "").strip()
            return out
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def deep_analyze(self, headline: str, text: str) -> DeepAnalysisOutput | None:
        """
        Run deep analysis on headline + text. Returns Pydantic-validated output or None on failure.
        """
        if not GENAI_AVAILABLE or not HAS_PYDANTIC or DeepAnalysisOutput is None:
            return None
        prompt = self._build_prompt(headline, text)
        try:
            raw = self._call_gemini(prompt)
        except Exception as e:
            logger.warning("Gemini API call failed: %s", e)
            return None
        if not raw:
            return None
        # Strip markdown code blocks if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
        raw = raw.strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("Gemini JSON parse failed: %s", e)
            return None
        if not isinstance(data, dict):
            return None
        # Normalize relationships to always have upstream/downstream lists
        rel = data.get("relationships") or {}
        if not isinstance(rel, dict):
            rel = {}
        data["relationships"] = {
            "upstream": list(rel.get("upstream", [])) if isinstance(rel.get("upstream"), list) else [],
            "downstream": list(rel.get("downstream", [])) if isinstance(rel.get("downstream"), list) else [],
        }
        # Clamp sentiment to [-1, 1]
        s = data.get("sentiment", 0.0)
        try:
            data["sentiment"] = max(-1.0, min(1.0, float(s)))
        except (TypeError, ValueError):
            data["sentiment"] = 0.0
        # Validate category
        allowed = ("SUPPLY_CHAIN_DISRUPTION", "DEMAND_SHOCK", "M&A", "MACRO")
        data["category"] = data.get("category") if data.get("category") in allowed else "MACRO"
        data["reasoning"] = str(data.get("reasoning", ""))[:500]
        try:
            return DeepAnalysisOutput(**data)
        except Exception as e:
            logger.warning("DeepAnalysisOutput validation failed: %s", e)
            return None
