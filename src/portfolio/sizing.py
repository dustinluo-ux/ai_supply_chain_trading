"""
Position Sizing - Cost-aware position sizing with liquidity constraints
Ported from wealth_signal_mvp_v1/core/ta_lib/sizing.py
"""
import numpy as np
import pandas as pd
from typing import Dict
from dataclasses import dataclass


@dataclass
class Account:
    """Account parameters for position sizing."""
    nav_base: float = 100000.0
    leverage_cap: float = 2.0
    margin_util_cap: float = 0.80


@dataclass
class Costs:
    """Trading cost parameters."""
    commission_per_share: float = 0.003
    commission_per_contract: float = 1.50
    half_spread_bps: float = 1.0
    impact_C: float = 0.5
    borrow_bps_cap: float = 500.0


@dataclass
class Limits:
    """Position and risk limits."""
    max_participation: float = 0.10  # Max participation in ADV


def position_sizer(weights: pd.Series, acct: Account, asset_meta: pd.DataFrame) -> pd.DataFrame:
    """
    Convert weights to dollar positions and quantities.
    
    Args:
        weights: Target weights for each asset
        acct: Account parameters
        asset_meta: DataFrame with columns: price, multiplier, board_lot, asset_type
        
    Returns:
        DataFrame with columns: target_weight, target_exposure_dollars, price, multiplier, qty
    """
    gross = weights.abs().sum()
    gross_allowed = min(acct.leverage_cap, gross)
    scale = (gross_allowed / gross) if gross > 0 else 0.0
    w_scaled = weights * scale
    exp_dollars = w_scaled * acct.nav_base
    meta = asset_meta.loc[weights.index]
    px = meta['price'].astype(float)
    mult = meta['multiplier'].astype(float).replace(0, 1.0)
    lotsz = meta['board_lot'].astype(int).clip(lower=1)
    is_future = meta['asset_type'].str.contains('future', case=False, na=False)
    qty = pd.Series(index=weights.index, dtype=float)
    qty.loc[~is_future] = (exp_dollars.loc[~is_future] / px.loc[~is_future]).round()
    qty.loc[is_future] = (exp_dollars.loc[is_future] / (px.loc[is_future] * mult.loc[is_future])).round()
    qty = (qty / lotsz).round() * lotsz
    return pd.DataFrame({
        'target_weight': w_scaled,
        'target_exposure_dollars': exp_dollars,
        'price': px,
        'multiplier': mult,
        'qty': qty.astype(int),
    })


def no_trade_band(current_qty: pd.Series, target_qty: pd.Series,
                  asset_meta: pd.DataFrame, costs: Costs) -> pd.Series:
    """
    Apply no-trade band: filter out trades where costs exceed benefit.
    
    Args:
        current_qty: Current position quantities
        target_qty: Target position quantities
        asset_meta: DataFrame with price, multiplier, asset_type
        costs: Trading cost parameters
        
    Returns:
        Series of delta quantities (0 if trade filtered out)
    """
    meta = asset_meta.loc[target_qty.index]
    px = meta['price'].astype(float)
    mult = meta['multiplier'].astype(float).replace(0, 1.0)
    is_future = meta['asset_type'].str.contains('future', case=False, na=False)
    dqty = (target_qty - current_qty).astype(float)
    dollars = pd.Series(index=target_qty.index, dtype=float)
    dollars.loc[~is_future] = dqty.loc[~is_future].abs() * px.loc[~is_future]
    dollars.loc[is_future] = dqty.loc[is_future].abs() * px.loc[is_future] * mult.loc[is_future]
    comm = pd.Series(0.0, index=target_qty.index)
    comm.loc[~is_future] = costs.commission_per_share * dqty.loc[~is_future].abs()
    comm.loc[is_future] = costs.commission_per_contract * dqty.loc[is_future].abs()
    half_spread = (costs.half_spread_bps / 1e4) * dollars
    thresh = comm + half_spread
    passmask = dollars > thresh
    return dqty.where(passmask, 0.0).round()


def liquidity_cap(delta_qty: pd.Series, asset_meta: pd.DataFrame, limits: Limits) -> pd.Series:
    """
    Cap order size based on average daily volume (liquidity).
    
    Args:
        delta_qty: Desired change in quantity
        asset_meta: DataFrame with adv_dollars, price, multiplier, asset_type
        limits: Position limits including max_participation
        
    Returns:
        Series of capped delta quantities
    """
    meta = asset_meta.loc[delta_qty.index]
    px = meta['price'].astype(float)
    mult = meta['multiplier'].astype(float).replace(0, 1.0)
    adv = meta['adv_dollars'].clip(lower=1e-6)
    is_future = meta['asset_type'].str.contains('future', case=False, na=False)
    order_dollars = pd.Series(index=delta_qty.index, dtype=float)
    order_dollars.loc[~is_future] = delta_qty.loc[~is_future].abs() * px.loc[~is_future]
    order_dollars.loc[is_future] = delta_qty.loc[is_future].abs() * px.loc[is_future] * mult.loc[is_future]
    scale = (limits.max_participation * adv) / order_dollars
    scale = scale.clip(upper=1.0).fillna(1.0)
    return (delta_qty * scale).round()
