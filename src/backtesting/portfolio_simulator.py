"""
Portfolio Simulator - Multi-asset portfolio simulation
Ported from wealth_signal_mvp_v1/core/simulation/portfolio_simulator.py
"""
import numpy as np
import pandas as pd
from typing import Dict, List


def simulate_portfolio(
    assets: List[str],
    weights: np.ndarray,
    price_data: Dict[str, pd.Series],
    initial_capital: float = 100000
) -> Dict:
    """
    Simulate a multi-asset portfolio with rebalancing.
    
    Args:
        assets: List of asset tickers
        weights: Target weights for each asset (numpy array)
        price_data: Dict of asset -> pd.Series (price history)
        initial_capital: Starting capital
        
    Returns:
        Dict with portfolio metrics and history:
        - initial_capital: Starting capital
        - final_value: Final portfolio value
        - portfolio_return: Total return
        - volatility: Portfolio volatility
        - sharpe_ratio: Sharpe ratio
        - portfolio_value_history: List of daily portfolio values
        - drawdown_history: List of daily drawdowns
        - daily_pnl: List of daily PnL
        - dates: List of dates
        - asset_returns: Dict of per-asset returns
    """
    n_assets = len(assets)
    min_len = min([len(price_data[a]) for a in assets if a in price_data and not price_data[a].empty])
    dates = price_data[assets[0]].index[:min_len] if min_len > 0 else []
    portfolio_values = []
    daily_pnl = []
    
    for i in range(min_len):
        prices = np.array([price_data[a].iloc[i] if a in price_data and not price_data[a].empty else 1.0 for a in assets])
        if i == 0:
            prev_prices = prices
            value = initial_capital
        else:
            prev_prices = np.array([price_data[a].iloc[i-1] if a in price_data and not price_data[a].empty else 1.0 for a in assets])
            value = portfolio_values[-1]
        returns = (prices - prev_prices) / prev_prices
        pnl = np.dot(weights, returns) * value
        value = value + pnl
        portfolio_values.append(value)
        daily_pnl.append(pnl)
    
    portfolio_values = np.array(portfolio_values)
    daily_pnl = np.array(daily_pnl)
    
    # Drawdown
    running_max = np.maximum.accumulate(portfolio_values)
    drawdown = (portfolio_values - running_max) / running_max
    
    # Final metrics
    final_value = portfolio_values[-1] if len(portfolio_values) > 0 else initial_capital
    total_return = (final_value - initial_capital) / initial_capital
    volatility = np.std(daily_pnl)
    sharpe = total_return / (volatility + 1e-8)
    
    # Calculate per-asset returns for diagnostics
    asset_returns = {}
    for i, asset in enumerate(assets):
        if asset in price_data and not price_data[asset].empty:
            asset_prices = price_data[asset]
            if len(asset_prices) > 1:
                asset_ret = asset_prices.pct_change().fillna(0.0)
                # Align with portfolio dates
                if len(asset_ret) >= min_len:
                    asset_returns[asset] = asset_ret.iloc[:min_len]
                else:
                    # Pad with zeros if needed
                    asset_ret_padded = pd.Series(0.0, index=dates[:len(asset_ret)])
                    asset_ret_padded.iloc[:len(asset_ret)] = asset_ret
                    asset_returns[asset] = asset_ret_padded
            else:
                asset_returns[asset] = pd.Series(0.0, index=dates[:min_len])
        else:
            asset_returns[asset] = pd.Series(0.0, index=dates[:min_len])
    
    result = {
        'initial_capital': initial_capital,
        'final_value': final_value,
        'portfolio_return': total_return,
        'volatility': volatility,
        'sharpe_ratio': sharpe,
        'portfolio_value_history': portfolio_values.tolist(),
        'drawdown_history': drawdown.tolist(),
        'daily_pnl': daily_pnl.tolist(),
        'dates': [str(d) for d in dates],
        'asset_returns': asset_returns,
    }
    return result
