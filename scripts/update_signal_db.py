"""
Daily signal database upsert script.

Reads outputs/daily_signals.csv → upserts into outputs/trading.db (SQLite).
For prior signal dates, computes 1d / 5d / 21d forward returns from price CSVs.
Builds portfolio_daily rows: port_return, spy_return, alpha (weighted 1d return vs SPY).

Column positions in CSV are used for parsing (positional, not header-name-based) so
old 5-column rows and new 7-column rows coexist without errors.

Usage:
  python scripts/update_signal_db.py [--signals PATH] [--db PATH]

Exit 0 on success, 1 on fatal error.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    date          TEXT NOT NULL,
    ticker        TEXT NOT NULL,
    weight        REAL,
    close         REAL,
    notional      INTEGER,
    score         REAL,
    vol_triggered INTEGER,
    PRIMARY KEY (date, ticker)
);

CREATE TABLE IF NOT EXISTS forward_returns (
    signal_date TEXT NOT NULL,
    ticker      TEXT NOT NULL,
    horizon     TEXT NOT NULL,
    entry_price REAL,
    exit_price  REAL,
    return_pct  REAL,
    PRIMARY KEY (signal_date, ticker, horizon)
);

CREATE TABLE IF NOT EXISTS portfolio_daily (
    date         TEXT PRIMARY KEY,
    port_return  REAL,
    spy_return   REAL,
    alpha        REAL,
    n_positions  INTEGER,
    tickers_held TEXT
);
"""

_HORIZONS: dict[str, int] = {"1d": 1, "5d": 5, "21d": 21}


def _nth_trading_close(
    close_series: pd.Series, as_of: pd.Timestamp, n: int
) -> float | None:
    """Return the close price n trading days strictly after as_of. None if not enough data."""
    future = close_series[close_series.index > as_of]
    if len(future) < n:
        return None
    return float(future.iloc[n - 1])


def _safe_float(v) -> float | None:
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def _safe_int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _read_signals_csv(path: Path) -> list[dict]:
    """
    Read daily_signals.csv using positional column access.

    Column order (fixed by generate_daily_weights.py):
      0: date  1: ticker  2: target_weight  3: latest_close  4: notional_units
      5: score (may be absent in old rows)
      6: vol_triggered (may be absent in old rows)

    Skips the header row automatically.
    """
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        # Detect header row by checking if first cell is 'date' (case-insensitive)
        if header and header[0].strip().lower() == "date":
            pass  # header consumed
        else:
            # No header or unexpected — treat first row as data
            if header:
                _row = header
                rows.append({
                    "date": _row[0] if len(_row) > 0 else None,
                    "ticker": _row[1] if len(_row) > 1 else None,
                    "target_weight": _row[2] if len(_row) > 2 else None,
                    "latest_close": _row[3] if len(_row) > 3 else None,
                    "notional_units": _row[4] if len(_row) > 4 else None,
                    "score": _row[5] if len(_row) > 5 else None,
                    "vol_triggered": _row[6] if len(_row) > 6 else None,
                })

        for row in reader:
            if len(row) < 2:
                continue
            rows.append({
                "date": row[0] if len(row) > 0 else None,
                "ticker": row[1] if len(row) > 1 else None,
                "target_weight": row[2] if len(row) > 2 else None,
                "latest_close": row[3] if len(row) > 3 else None,
                "notional_units": row[4] if len(row) > 4 else None,
                "score": row[5] if len(row) > 5 else None,
                "vol_triggered": row[6] if len(row) > 6 else None,
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Upsert signal DB and compute forward returns")
    parser.add_argument("--signals", type=str, default=None, help="Path to daily_signals.csv")
    parser.add_argument("--db", type=str, default=None, help="Path to trading.db")
    args = parser.parse_args()

    signals_path = (
        Path(args.signals) if args.signals else ROOT / "outputs" / "daily_signals.csv"
    )
    db_path = Path(args.db) if args.db else ROOT / "outputs" / "trading.db"

    if not signals_path.exists():
        print(f"ERROR: signals CSV not found: {signals_path}", flush=True)
        return 1

    # --- Read CSV ---
    try:
        signal_rows = _read_signals_csv(signals_path)
    except Exception as e:
        print(f"ERROR: Failed to read signals CSV: {e}", flush=True)
        return 1

    if not signal_rows:
        print("INFO: signals CSV is empty, nothing to do.", flush=True)
        return 0

    # --- Open / init DB ---
    db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        con = sqlite3.connect(str(db_path))
    except Exception as e:
        print(f"ERROR: Cannot open DB at {db_path}: {e}", flush=True)
        return 1

    with con:
        con.executescript(_DB_SCHEMA)

    # --- Upsert signals rows ---
    upsert_rows = []
    for r in signal_rows:
        date_str = str(r["date"] or "")[:10]
        ticker = str(r["ticker"] or "").strip()
        if not date_str or not ticker or ticker.lower() == "ticker":
            continue  # skip malformed or header-as-data rows
        upsert_rows.append((
            date_str,
            ticker,
            _safe_float(r["target_weight"]),
            _safe_float(r["latest_close"]),
            _safe_int(r["notional_units"]),
            _safe_float(r["score"]),
            _safe_int(r["vol_triggered"]),
        ))

    with con:
        con.executemany(
            """INSERT OR REPLACE INTO signals
               (date, ticker, weight, close, notional, score, vol_triggered)
               VALUES (?,?,?,?,?,?,?)""",
            upsert_rows,
        )
    print(f"INFO: Upserted {len(upsert_rows)} signal rows.", flush=True)

    # --- Load prices ---
    try:
        from src.data.csv_provider import load_data_config, load_prices
    except Exception as e:
        print(f"ERROR: Failed to import csv_provider: {e}", flush=True)
        con.close()
        return 1

    data_cfg = load_data_config()
    data_dir = data_cfg["data_dir"]
    all_tickers = list({r["ticker"] for r in signal_rows if r["ticker"]})
    if "SPY" not in all_tickers:
        all_tickers.append("SPY")

    print(f"INFO: Loading prices for {len(all_tickers)} tickers...", flush=True)
    prices_dict = load_prices(data_dir, all_tickers)
    if not prices_dict:
        print("WARN: No price data loaded; skipping forward return computation.", flush=True)
        con.close()
        return 0

    # --- Compute forward returns for signal dates not yet populated ---
    cur = con.cursor()
    cur.execute("SELECT DISTINCT date FROM signals ORDER BY date")
    all_signal_dates = [r[0] for r in cur.fetchall()]

    for sig_date_str in all_signal_dates:
        # Check if already computed (idempotent — skip if any rows exist for this date)
        cur.execute(
            "SELECT COUNT(*) FROM forward_returns WHERE signal_date = ?",
            (sig_date_str,),
        )
        if cur.fetchone()[0] > 0:
            continue

        sig_date = pd.Timestamp(sig_date_str)

        # Active tickers: weight > 0 on this date
        cur.execute(
            "SELECT ticker, weight, close FROM signals WHERE date = ? AND weight > 0",
            (sig_date_str,),
        )
        active = cur.fetchall()  # [(ticker, weight, entry_close), ...]
        if not active:
            continue

        fr_rows: list[tuple] = []
        for ticker, weight, entry_close in active:
            if ticker not in prices_dict:
                continue
            close_series = prices_dict[ticker]["close"]

            # Entry price: use stored close; fall back to asof lookup
            entry_price = _safe_float(entry_close)
            if entry_price is None:
                asof_val = (
                    close_series.asof(sig_date) if hasattr(close_series, "asof") else None
                )
                if asof_val is None or pd.isna(asof_val):
                    continue
                entry_price = float(asof_val)

            for horizon_name, n_days in _HORIZONS.items():
                exit_price = _nth_trading_close(close_series, sig_date, n_days)
                if exit_price is None or entry_price <= 0:
                    ret_pct = None
                else:
                    ret_pct = exit_price / entry_price - 1.0
                fr_rows.append(
                    (sig_date_str, ticker, horizon_name, entry_price, exit_price, ret_pct)
                )

        if fr_rows:
            with con:
                con.executemany(
                    """INSERT OR REPLACE INTO forward_returns
                       (signal_date, ticker, horizon, entry_price, exit_price, return_pct)
                       VALUES (?,?,?,?,?,?)""",
                    fr_rows,
                )
            print(
                f"INFO: {sig_date_str}: wrote {len(fr_rows)} forward_return rows.", flush=True
            )

    # --- Build portfolio_daily from 1d forward returns ---
    cur.execute(
        "SELECT DISTINCT signal_date FROM forward_returns WHERE horizon = '1d' ORDER BY signal_date"
    )
    fr_dates = [r[0] for r in cur.fetchall()]

    pd_rows_written = 0
    for fr_date_str in fr_dates:
        cur.execute("SELECT 1 FROM portfolio_daily WHERE date = ?", (fr_date_str,))
        if cur.fetchone():
            continue  # Already computed

        # Weighted portfolio return for this date
        cur.execute(
            """SELECT s.ticker, s.weight, f.return_pct
               FROM signals s
               JOIN forward_returns f
                 ON s.date = f.signal_date AND s.ticker = f.ticker
               WHERE s.date = ? AND f.horizon = '1d' AND s.weight > 0""",
            (fr_date_str,),
        )
        active_fr = cur.fetchall()  # [(ticker, weight, return_pct), ...]
        if not active_fr:
            continue

        port_return = sum(
            float(w) * float(r)
            for _, w, r in active_fr
            if w is not None and r is not None
        )
        n_positions = len(active_fr)
        tickers_held = ",".join(t for t, _, _ in active_fr)

        # SPY 1d return
        spy_return: float | None = None
        if "SPY" in prices_dict:
            spy_date = pd.Timestamp(fr_date_str)
            spy_series = prices_dict["SPY"]["close"]
            spy_close = spy_series.asof(spy_date) if hasattr(spy_series, "asof") else None
            if spy_close is not None and not pd.isna(spy_close) and float(spy_close) > 0:
                spy_next = _nth_trading_close(spy_series, spy_date, 1)
                if spy_next is not None:
                    spy_return = spy_next / float(spy_close) - 1.0

        alpha = (port_return - spy_return) if spy_return is not None else None

        with con:
            con.execute(
                """INSERT OR REPLACE INTO portfolio_daily
                   (date, port_return, spy_return, alpha, n_positions, tickers_held)
                   VALUES (?,?,?,?,?,?)""",
                (fr_date_str, port_return, spy_return, alpha, n_positions, tickers_held),
            )
        pd_rows_written += 1

    if pd_rows_written:
        print(f"INFO: Wrote {pd_rows_written} portfolio_daily rows.", flush=True)
    else:
        print("INFO: portfolio_daily: no new rows (forward prices not yet available or already computed).", flush=True)

    con.close()
    print("Done.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
