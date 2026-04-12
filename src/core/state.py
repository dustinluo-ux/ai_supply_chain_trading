"""
Pipeline-wide state (vendor events, scores, orders). No LangChain/LangGraph.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional


@dataclass
class VendorEvent:
    ticker: str
    vendor: str  # "csv" | "marketaux" | "yfinance" | "alphavantage"
    success: bool
    error: Optional[str] = None
    latency_ms: Optional[float] = None


@dataclass
class PipelineState:
    run_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    vendor_events: list[VendorEvent] = field(default_factory=list)
    tickers_requested: list[str] = field(default_factory=list)
    tickers_loaded: list[str] = field(default_factory=list)
    signal_scores: dict[str, Decimal] = field(default_factory=dict)
    regime: Optional[str] = None
    nav: Optional[Decimal] = None
    target_weights: dict[str, Decimal] = field(default_factory=dict)
    orders_submitted: int = 0
    orders_filled: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_vendor_event(
        self,
        ticker: str,
        vendor: str,
        success: bool,
        error: Optional[str] = None,
        latency_ms: Optional[float] = None,
    ) -> None:
        self.vendor_events.append(
            VendorEvent(
                ticker=ticker,
                vendor=vendor,
                success=success,
                error=error,
                latency_ms=latency_ms,
            )
        )

    def fallback_count(self) -> int:
        """Tickers with more than one vendor attempt (i.e. at least one fallback)."""
        by_ticker: dict[str, int] = {}
        for ev in self.vendor_events:
            by_ticker[ev.ticker] = by_ticker.get(ev.ticker, 0) + 1
        return sum(1 for _t, n in by_ticker.items() if n > 1)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe: Decimal → str, datetime → isoformat, nested dataclasses → dicts."""

        def _convert(obj: Any) -> Any:
            if isinstance(obj, Decimal):
                return str(obj)
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, VendorEvent):
                return {
                    "ticker": obj.ticker,
                    "vendor": obj.vendor,
                    "success": obj.success,
                    "error": obj.error,
                    "latency_ms": obj.latency_ms,
                }
            if isinstance(obj, dict):
                return {str(k): _convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert(v) for v in obj]
            return obj

        raw = asdict(self)
        return _convert(raw)

    def save(self, path: Path | str) -> None:
        """Atomic JSON write: .tmp → validate non-empty → replace."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / (path.name + ".tmp")
        payload = self.to_dict()
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        if not text or not text.strip():
            raise ValueError("PipelineState.to_dict() produced empty JSON")
        tmp.write_text(text, encoding="utf-8")
        if tmp.stat().st_size == 0:
            raise ValueError("atomic write temp file is empty")
        tmp.replace(path)


def new_pipeline_state(
    tickers_requested: Optional[list[str]] = None,
    *,
    run_id: Optional[str] = None,
    started_at: Optional[datetime] = None,
) -> PipelineState:
    """Convenience factory (optional; callers may construct PipelineState directly)."""
    return PipelineState(
        run_id=run_id or uuid.uuid4().hex,
        started_at=started_at or datetime.now(timezone.utc),
        tickers_requested=list(tickers_requested or []),
    )
