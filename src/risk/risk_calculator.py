"""
Risk Calculator - VaR and margin monitoring
Ported from wealth_signal_mvp_v1/core/utils/risk_calculator.py
"""
from typing import Union
import numpy as np


def calculate_position_risk(
    price: float,
    quantity: int,
    volatility: float,
    point_value: float = 1.0,
    confidence_level: float = 0.95
) -> float:
    """
    Calculate position risk using Value at Risk (VaR) methodology.
    
    Args:
        price: Current price of the instrument
        quantity: Position size in contracts
        volatility: Annualized volatility as decimal (e.g. 0.25 for 25%)
        point_value: Dollar value of one point move (default 1.0 for stocks)
        confidence_level: Confidence level for VaR calculation (default 95%)
        
    Returns:
        Value at Risk in dollars
    """
    # Convert annual volatility to daily
    daily_vol = volatility / np.sqrt(252)
    
    # Calculate position value
    position_value = price * abs(quantity) * point_value
    
    # Calculate VaR using normal distribution approximation
    # For 95% confidence, z-score ≈ 1.645
    from scipy.stats import norm
    z_score = abs(norm.ppf(1 - confidence_level))
    var = position_value * daily_vol * z_score
    
    return float(var)


def calculate_portfolio_risk(
    positions: list,
    correlation_matrix: Union[np.ndarray, None] = None,
    confidence_level: float = 0.95
) -> float:
    """
    Calculate portfolio-level risk using correlation-aware VaR.
    
    Args:
        positions: List of dictionaries with position details
                  Each dict needs: {'var': position_var}
        correlation_matrix: Correlation matrix for positions (numpy array)
        confidence_level: Confidence level for VaR calculation
        
    Returns:
        Portfolio VaR in dollars
    """
    if not positions:
        return 0.0
        
    # Extract individual VaRs
    vars = np.array([p['var'] for p in positions])
    
    if correlation_matrix is None or len(positions) == 1:
        # Without correlations, use simple sum of VaRs (conservative)
        return float(np.sum(vars))
        
    # With correlations, use matrix multiplication
    # Portfolio variance = w' * Σ * w
    portfolio_var = np.sqrt(
        vars.T @ correlation_matrix @ vars
    )
    
    return float(portfolio_var)


def calculate_margin_utilization(
    current_margin: float,
    total_margin: float,
    warning_threshold: float = 0.8
) -> tuple:
    """
    Calculate margin utilization and check warning levels.
    
    Args:
        current_margin: Currently used margin
        total_margin: Total available margin
        warning_threshold: Level to trigger warning (default 80%)
        
    Returns:
        Tuple of (utilization_ratio, warning_flag)
    """
    if total_margin <= 0:
        return (1.0, True)
        
    utilization = current_margin / total_margin
    warning = utilization >= warning_threshold
    
    return (utilization, warning)
