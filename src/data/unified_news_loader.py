from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.eodhd_news_loader import load_eodhd_news_signals

logger = logging.getLogger(__name__)


class UnifiedNewsLoader:
    TIINGO_CUTOFF = date(2025, 1, 1)

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.news_dir = self.data_dir / "news"

    def load(
        self,
        tickers,
        start_date,
        end_date,
    ) -> dict[str, dict[str, dict[str, float]]]:
        try:
            tickers_clean = [str(t).strip() for t in (tickers or []) if str(t).strip()]
            if not tickers_clean:
                logger.warning("[UNIFIED_NEWS] Empty ticker list.")
                return {}

            start_d = self._to_date(start_date)
            end_d = self._to_date(end_date)
            if start_d is None or end_d is None or start_d > end_d:
                logger.warning("[UNIFIED_NEWS] Invalid date range: start=%s end=%s", start_date, end_date)
                return {}

            pre_start = start_d
            pre_end = min(end_d, self.TIINGO_CUTOFF - timedelta(days=1))
            post_start = max(start_d, self.TIINGO_CUTOFF)
            post_end = end_d

            pre_out: dict[str, dict[str, dict[str, float]]] = {}
            post_out: dict[str, dict[str, dict[str, float]]] = {}

            if pre_start <= pre_end:
                pre_out = self._load_pre_cutoff_eodhd(tickers_clean, pre_start, pre_end)

            if post_start <= post_end:
                post_out = self._load_post_cutoff_tiingo_or_fallback(tickers_clean, post_start, post_end)

            merged = self._merge_with_post_priority(pre_out, post_out)
            if not merged:
                logger.warning(
                    "[UNIFIED_NEWS] No data from either window for %s..%s.",
                    start_d.isoformat(),
                    end_d.isoformat(),
                )
            return merged
        except Exception as exc:
            logger.warning("[UNIFIED_NEWS] Unexpected loader failure: %s", exc)
            return {}

    @staticmethod
    def _to_date(value) -> date | None:
        try:
            if isinstance(value, date):
                return value
            return pd.to_datetime(value).date()
        except Exception:
            return None

    def _load_pre_cutoff_eodhd(
        self,
        tickers: list[str],
        start_d: date,
        end_d: date,
    ) -> dict[str, dict[str, dict[str, float]]]:
        try:
            eodhd_path = self.news_dir / "eodhd_global_backfill.parquet"
            if not eodhd_path.exists():
                logger.warning("[UNIFIED_NEWS] EODHD parquet missing for pre-cutoff window: %s", eodhd_path)
                return {}
            eodhd_out, _ = load_eodhd_news_signals(
                tickers,
                start_d.isoformat(),
                end_d.isoformat(),
                parquet_path=eodhd_path,
            )
            return self._with_supply_chain(eodhd_out)
        except Exception as exc:
            logger.warning("[UNIFIED_NEWS] Pre-cutoff EODHD load failed: %s", exc)
            return {}

    def _load_post_cutoff_tiingo_or_fallback(
        self,
        tickers: list[str],
        start_d: date,
        end_d: date,
    ) -> dict[str, dict[str, dict[str, float]]]:
        try:
            tiingo_files = self._tiingo_files_for_window(start_d, end_d)
            if not tiingo_files:
                logger.warning("[UNIFIED_NEWS] No Tiingo parquets found; falling back to EODHD for post-cutoff.")
                return self._load_post_fallback_eodhd(tickers, start_d, end_d)

            frames: list[pd.DataFrame] = []
            for fp in tiingo_files:
                try:
                    df = pd.read_parquet(fp, engine="fastparquet")
                    frames.append(df)
                except Exception as exc:
                    logger.warning("[UNIFIED_NEWS] Failed reading Tiingo parquet %s: %s", fp, exc)

            if not frames:
                logger.warning("[UNIFIED_NEWS] Tiingo files unreadable; falling back to EODHD for post-cutoff.")
                return self._load_post_fallback_eodhd(tickers, start_d, end_d)

            raw = pd.concat(frames, ignore_index=True)
            required = {"Date", "Ticker", "Sentiment"}
            if not required.issubset(set(raw.columns)):
                logger.warning("[UNIFIED_NEWS] Tiingo parquet schema missing required columns.")
                return self._load_post_fallback_eodhd(tickers, start_d, end_d)

            raw = raw.copy()
            raw["Date"] = pd.to_datetime(raw["Date"], errors="coerce").dt.date
            raw["Ticker"] = raw["Ticker"].astype(str)
            raw["Sentiment"] = pd.to_numeric(raw["Sentiment"], errors="coerce")
            raw = raw[
                raw["Ticker"].isin(tickers)
                & raw["Date"].notna()
                & raw["Sentiment"].notna()
                & (raw["Date"] >= start_d)
                & (raw["Date"] <= end_d)
            ]
            if raw.empty:
                logger.warning("[UNIFIED_NEWS] Tiingo had no rows after ticker/date filtering.")
                return {}

            by_date_ticker = raw.groupby(["Date", "Ticker"], as_index=False)["Sentiment"].mean()
            out: dict[str, dict[str, dict[str, float]]] = {}
            for dt_val, grp in by_date_ticker.groupby("Date", sort=False):
                sents = grp.set_index("Ticker")["Sentiment"]
                if len(sents) <= 1:
                    for t in sents.index:
                        out.setdefault(str(t), {})[dt_val.isoformat()] = {
                            "sentiment_score": 0.5,
                            "supply_chain_score": 0.5,
                        }
                    continue
                mean_s = float(sents.mean())
                std_s = float(sents.std())
                if std_s <= 0 or np.isnan(std_s):
                    for t in sents.index:
                        out.setdefault(str(t), {})[dt_val.isoformat()] = {
                            "sentiment_score": 0.5,
                            "supply_chain_score": 0.5,
                        }
                    continue
                z = (sents - mean_s) / std_s
                rescaled = np.clip((z + 3.0) / 6.0, 0.0, 1.0)
                for t in rescaled.index:
                    out.setdefault(str(t), {})[dt_val.isoformat()] = {
                        "sentiment_score": float(rescaled[t]),
                        "supply_chain_score": 0.5,
                    }
            return out
        except Exception as exc:
            logger.warning("[UNIFIED_NEWS] Post-cutoff Tiingo path failed: %s", exc)
            return {}

    def _load_post_fallback_eodhd(
        self,
        tickers: list[str],
        start_d: date,
        end_d: date,
    ) -> dict[str, dict[str, dict[str, float]]]:
        try:
            eodhd_path = self.news_dir / "eodhd_global_backfill.parquet"
            if not eodhd_path.exists():
                logger.warning("[UNIFIED_NEWS] EODHD parquet missing for post-cutoff fallback: %s", eodhd_path)
                return {}
            out, _ = load_eodhd_news_signals(
                tickers,
                start_d.isoformat(),
                end_d.isoformat(),
                parquet_path=eodhd_path,
            )
            return self._with_supply_chain(out)
        except Exception as exc:
            logger.warning("[UNIFIED_NEWS] Post-cutoff EODHD fallback failed: %s", exc)
            return {}

    def _tiingo_files_for_window(self, start_d: date, end_d: date) -> list[Path]:
        files: list[Path] = []
        try:
            cur = date(start_d.year, start_d.month, 1)
            end_month = date(end_d.year, end_d.month, 1)
            while cur <= end_month:
                p = self.news_dir / f"tiingo_{cur.year}_{cur.month:02d}.parquet"
                if p.exists():
                    files.append(p)
                if cur.month == 12:
                    cur = date(cur.year + 1, 1, 1)
                else:
                    cur = date(cur.year, cur.month + 1, 1)
        except Exception as exc:
            logger.warning("[UNIFIED_NEWS] Failed scanning Tiingo parquet list: %s", exc)
        return files

    @staticmethod
    def _with_supply_chain(src: dict) -> dict[str, dict[str, dict[str, float]]]:
        out: dict[str, dict[str, dict[str, float]]] = {}
        for t, by_date in (src or {}).items():
            for d, payload in (by_date or {}).items():
                sent = float((payload or {}).get("sentiment_score", 0.5))
                out.setdefault(str(t), {})[str(d)] = {
                    "sentiment_score": sent,
                    "supply_chain_score": 0.5,
                }
        return out

    @staticmethod
    def _merge_with_post_priority(
        pre_out: dict[str, dict[str, dict[str, float]]],
        post_out: dict[str, dict[str, dict[str, float]]],
    ) -> dict[str, dict[str, dict[str, float]]]:
        merged: dict[str, dict[str, dict[str, float]]] = {}
        for t, by_date in (pre_out or {}).items():
            merged.setdefault(str(t), {}).update(by_date or {})
        for t, by_date in (post_out or {}).items():
            merged.setdefault(str(t), {}).update(by_date or {})
        return merged
