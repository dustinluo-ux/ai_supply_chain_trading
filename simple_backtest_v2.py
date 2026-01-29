"""Simple Standalone Backtest - Modular News + Technical Signals"""
import pandas as pd
import numpy as np
import argparse
import yaml
from pathlib import Path
from datetime import datetime, timedelta

from src.signals.technical_analyzer import TechnicalAnalyzer
from src.signals.news_analyzer import NewsAnalyzer
from src.signals.signal_combiner import SignalCombiner

# Parse command line arguments
parser = argparse.ArgumentParser(description='Run backtest with modular signal system')
parser.add_argument('--technical-only', action='store_true', help='Use only technical signals (skip news)')
parser.add_argument('--news-only', action='store_true', help='Use only news signals (skip technical)')
parser.add_argument('--universe-size', type=int, default=50, help='Maximum number of tickers to include (default: 50)')
parser.add_argument('--data-dir', type=str, default=None, help='Override data directory from config')
parser.add_argument('--top-n', type=int, default=10, help='Number of top stocks to select each week (default: 10)')
args = parser.parse_args()

# Load signal weights from config
config_path = Path("config/signal_weights.yaml")
if config_path.exists():
    with open(config_path, 'r') as f:
        signal_config = yaml.safe_load(f)
    weights = signal_config.get('signal_weights', {})
    tech_config = signal_config.get('technical_indicators', {})
    news_config = signal_config.get('news_analysis', {})
else:
    # Defaults if config not found
    weights = {'supply_chain': 0.4, 'sentiment': 0.3, 'momentum': 0.2, 'volume': 0.1}
    tech_config = {'momentum_period': 20, 'volume_period': 30, 'rsi_period': 14}
    news_config = {'enabled': True, 'lookback_days': 7, 'min_articles': 1}

# Adjust weights based on flags - CRITICAL: Create NEW dicts to avoid reference issues
if args.technical_only:
    # Technical-only: momentum + volume + RSI (normalized to sum to 1.0)
    weights = {'supply_chain': 0.0, 'sentiment': 0.0, 'momentum': 0.5, 'volume': 0.3, 'rsi': 0.2}
    news_config = news_config.copy()  # Create copy to avoid modifying original
    news_config['enabled'] = False
    print("[WARNING] Technical-only mode: News analysis disabled", flush=True)
    print(f"[DEBUG] Technical-only weights set: {weights}", flush=True)
elif args.news_only:
    # News-only: supply chain + sentiment (normalized to sum to 1.0)
    weights = {'supply_chain': 0.5, 'sentiment': 0.5, 'momentum': 0.0, 'volume': 0.0, 'rsi': 0.0}
    print("[WARNING] News-only mode: Technical signals disabled", flush=True)
    print(f"[DEBUG] News-only weights set: {weights}", flush=True)
else:
    # Normalize weights to sum to 1.0
    total = sum(weights.values())
    if total > 0:
        weights = {k: v / total for k, v in weights.items()}
    print(f"[DEBUG] Combined mode weights (normalized): {weights}", flush=True)

# DEBUG: Print weights being used
print(f"\n[DEBUG] Signal weights: {weights}", flush=True)
print(f"[DEBUG] News enabled: {news_config.get('enabled', True)}", flush=True)
print(f"[DEBUG] Mode: {'TECHNICAL-ONLY' if args.technical_only else 'NEWS-ONLY' if args.news_only else 'COMBINED'}", flush=True)

# CRITICAL: Verify weights are actually different
if args.technical_only:
    assert weights['supply_chain'] == 0.0 and weights['sentiment'] == 0.0, "Technical-only weights not set correctly!"
    assert weights['momentum'] > 0 or weights['volume'] > 0, "Technical-only has no technical weights!"
elif args.news_only:
    assert weights['momentum'] == 0.0 and weights['volume'] == 0.0, "News-only weights not set correctly!"
    assert weights['supply_chain'] > 0 or weights['sentiment'] > 0, "News-only has no news weights!"


# Load universe using UniverseLoader
print("\n[0/6] Loading stock universe...", flush=True)
from src.data.universe_loader import UniverseLoader

universe_loader = UniverseLoader()
if args.data_dir:
    universe_loader.data_dir = Path(args.data_dir)
    universe_loader.config['data_sources']['data_dir'] = str(args.data_dir)
    
# Also update DATA_DIR for backward compatibility
DATA_DIR = universe_loader.data_dir

# Load tickers
ticker_metadata = universe_loader.load_universe(max_tickers=args.universe_size)
if not ticker_metadata:
    print("ERROR: No valid tickers found! Check data_config.yaml and data directory.", flush=True)
    exit(1)

# Extract ticker list and file paths
TICKERS = [t['ticker'] for t in ticker_metadata]
ticker_file_map = {t['ticker']: Path(t['file_path']) for t in ticker_metadata}

# Get summary
summary = universe_loader.get_universe_summary(ticker_metadata)
print(f"  [OK] Loaded {summary['count']} tickers", flush=True)
print(f"  News data: {summary['with_news']}/{summary['count']} tickers ({summary['news_coverage']:.1%})", flush=True)
if summary['date_range']:
    print(f"  Date range: {summary['date_range'][0].strftime('%Y-%m-%d')} to {summary['date_range'][1].strftime('%Y-%m-%d')}", flush=True)

# Set TOP_N
TOP_N = args.top_n

# WARNING: If we have fewer tickers than TOP_N, all will be selected
if len(TICKERS) <= TOP_N:
    print(f"[WARNING] Only {len(TICKERS)} tickers available but selecting top {TOP_N}!", flush=True)
    print(f"[WARNING] This means all stocks will always be selected, making all approaches identical.", flush=True)
    print(f"[WARNING] Consider: 1) Increase --universe-size, or 2) Reduce --top-n to {max(1, len(TICKERS) - 1)}", flush=True)
elif len(TICKERS) < 20:
    print(f"[WARNING] Only {len(TICKERS)} tickers available. Recommend at least 20 for meaningful backtest.", flush=True)

print("=" * 60, f"\nSIMPLE BACKTEST V2 - {len(TICKERS)} Tickers\n" + "=" * 60)
if news_config.get('enabled', True):
    print("Mode: Combined (News + Technical)", flush=True)
else:
    print("Mode: Technical Only", flush=True)

# Initialize analyzers
print("\n[1/6] Initializing analyzers...", flush=True)
tech_analyzer = TechnicalAnalyzer(
    data_dir=str(universe_loader.data_dir),
    momentum_period=tech_config.get('momentum_period', 20),
    volume_period=tech_config.get('volume_period', 30),
    rsi_period=tech_config.get('rsi_period', 14)
)

news_analyzer = None
if news_config.get('enabled', True):
    try:
        news_analyzer = NewsAnalyzer(
            news_dir="data/news",
            lookback_days=news_config.get('lookback_days', 7),
            min_articles=news_config.get('min_articles', 1)
        )
        print("  [OK] News analyzer initialized", flush=True)
    except Exception as e:
        print(f"  [WARNING] News analyzer failed: {e} (continuing without news)", flush=True)
        news_analyzer = None
        news_config['enabled'] = False

signal_combiner = SignalCombiner()
print("  [OK] Technical analyzer initialized", flush=True)
print("  [OK] Signal combiner initialized", flush=True)

# Load price data
print(f"\n[2/6] Loading price data from {len(TICKERS)} CSV files...", flush=True)
prices_dict = {}
for ticker in TICKERS:
    file_path = DATA_DIR / f"{ticker}.csv"
    try:
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)
        df = df.loc['2023-01-01':'2023-12-31']
        df.columns = [col.lower() for col in df.columns]
        if not df.empty and 'close' in df.columns:
            prices_dict[ticker] = df
            print(f"  [OK] {ticker}: {len(df)} rows", flush=True)
    except Exception as e:
        print(f"  [ERROR] {ticker}: {e}", flush=True)

if not prices_dict:
    print("ERROR: No price data loaded!")
    exit(1)

# Generate weekly signals (Mondays)
print("\n[3/6] Generating weekly signals...", flush=True)
# Start from later in January to ensure we have enough historical data for calculations
# Need at least 30 days for volume, 20 for momentum
mondays = pd.date_range('2023-02-01', '2023-12-31', freq='W-MON')
print(f"[DEBUG] Generating signals for {len(mondays)} Mondays starting from {mondays[0].strftime('%Y-%m-%d')}", flush=True)
signals_df = pd.DataFrame(0.0, index=mondays, columns=list(prices_dict.keys()))

# DEBUG: Track scores for first week to show differences
debug_scores = {}
debug_mode = ""

for idx, monday in enumerate(mondays, 1):
    if idx % 5 == 0:
        print(f"  Processing week {idx}/{len(mondays)}...", flush=True)
    
    date_str = monday.strftime("%Y-%m-%d")
    lookback_start = (monday - timedelta(days=news_config.get('lookback_days', 7))).strftime("%Y-%m-%d")
    
    scores = {}
    for ticker in prices_dict.keys():
        try:
            # Get technical signals
            # CRITICAL: Use the same data that's in prices_dict to ensure consistency
            # Calculate signals directly from prices_dict instead of reloading from CSV
            ticker_df = prices_dict[ticker]
            date_dt = pd.to_datetime(date_str)
            df_filtered = ticker_df[ticker_df.index <= date_dt]
            
            # DEBUG: Print data availability for first few tickers
            if idx == 1 and ticker in list(prices_dict.keys())[:3]:
                print(f"    [DEBUG] {ticker} on {date_str}: df_filtered has {len(df_filtered)} rows (need >= {tech_config.get('momentum_period', 20)} for momentum)", flush=True)
                if not df_filtered.empty:
                    print(f"      Date range: {df_filtered.index[0]} to {df_filtered.index[-1]}", flush=True)
                    print(f"      Close values: first={df_filtered['close'].iloc[0]:.2f}, last={df_filtered['close'].iloc[-1]:.2f}", flush=True)
            
            if df_filtered.empty or len(df_filtered) < 5:
                tech_signals = {'momentum_score': 0.0, 'volume_score': 1.0, 'rsi_score': 0.5}
                if idx == 1 and ticker in list(prices_dict.keys())[:3]:
                    print(f"      [WARNING] {ticker} insufficient data: {len(df_filtered)} rows", flush=True)
            else:
                # Calculate momentum directly
                close = df_filtered['close']
                momentum_period = tech_config.get('momentum_period', 20)
                if len(close) >= momentum_period:
                    close_short = close.iloc[-5] if len(close) >= 5 else close.iloc[-1]
                    close_long = close.iloc[-momentum_period]
                    momentum = (close_short - close_long) / (close_long + 1e-8)
                    # DEBUG: Verify momentum varies
                    if idx == 1 and ticker in list(prices_dict.keys())[:3]:
                        print(f"      [DEBUG] {ticker} momentum calc: short={close_short:.2f}, long={close_long:.2f}, momentum={momentum:.6f}", flush=True)
                else:
                    momentum = 0.0
                    if idx == 1 and ticker in list(prices_dict.keys())[:3]:
                        print(f"      [WARNING] {ticker} insufficient data for momentum: need {momentum_period}, have {len(close)}", flush=True)
                
                # Calculate volume ratio directly
                if 'volume' in df_filtered.columns:
                    volume = df_filtered['volume']
                    volume_period = tech_config.get('volume_period', 30)
                    if len(volume) >= volume_period:
                        volume_mean = volume.rolling(volume_period, min_periods=1).mean().iloc[-1]
                        volume_latest = volume.iloc[-1]
                        volume_ratio = volume_latest / volume_mean if volume_mean > 0 else 1.0
                        # DEBUG: Verify volume varies
                        if idx == 1 and ticker in list(prices_dict.keys())[:3]:
                            print(f"      [DEBUG] {ticker} volume calc: latest={volume_latest:.0f}, mean={volume_mean:.0f}, ratio={volume_ratio:.6f}", flush=True)
                    else:
                        volume_ratio = 1.0
                        if idx == 1 and ticker in list(prices_dict.keys())[:3]:
                            print(f"      [WARNING] {ticker} insufficient data for volume: need {volume_period}, have {len(volume)}", flush=True)
                else:
                    volume_ratio = 1.0
                    if idx == 1 and ticker in list(prices_dict.keys())[:3]:
                        print(f"      [WARNING] {ticker} no 'volume' column in data", flush=True)
                
                # Calculate RSI directly
                if 'close' in df_filtered.columns:
                    close = df_filtered['close']
                    delta = close.diff()
                    gain = (delta.where(delta > 0, 0)).rolling(tech_config.get('rsi_period', 14), min_periods=1).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(tech_config.get('rsi_period', 14), min_periods=1).mean()
                    if len(gain) > 0 and len(loss) > 0:
                        rs = gain.iloc[-1] / (loss.iloc[-1] + 1e-8)
                        rsi = 100 - (100 / (1 + rs))
                        rsi_score = ((rsi - 30) / 40).clip(0, 1)
                    else:
                        rsi_score = 0.5
                else:
                    rsi_score = 0.5
                
                tech_signals = {
                    'momentum_score': float(momentum),
                    'volume_score': float(volume_ratio),
                    'rsi_score': float(rsi_score)
                }
            
            # OLD: tech_signals = tech_analyzer.calculate_technical_signals(ticker, date_str)
            
            # DEBUG: Print raw technical signals for first week to see if they're different
            # Also check the actual price data to verify it's different
            if idx == 1 and ticker in list(prices_dict.keys())[:5]:
                print(f"    [DEBUG] {ticker} raw tech signals: momentum={tech_signals.get('momentum_score', 0):.6f}, volume={tech_signals.get('volume_score', 0):.6f}, rsi={tech_signals.get('rsi_score', 0):.6f}", flush=True)
                # Check actual price data for this ticker
                ticker_df = prices_dict[ticker]
                if len(ticker_df) >= 20:
                    close_vals = ticker_df['close'].iloc[-20:]
                    close_short = ticker_df['close'].iloc[-5] if len(ticker_df) >= 5 else ticker_df['close'].iloc[-1]
                    close_long = ticker_df['close'].iloc[-20]
                    manual_momentum = (close_short - close_long) / close_long
                    print(f"      [DEBUG] {ticker} price check: close[-5]={close_short:.2f}, close[-20]={close_long:.2f}, manual_momentum={manual_momentum:.6f}", flush=True)
                    if 'volume' in ticker_df.columns:
                        vol_latest = ticker_df['volume'].iloc[-1]
                        vol_mean = ticker_df['volume'].rolling(30, min_periods=1).mean().iloc[-1]
                        manual_volume = vol_latest / vol_mean if vol_mean > 0 else 1.0
                        print(f"      [DEBUG] {ticker} volume check: latest={vol_latest:.0f}, mean={vol_mean:.0f}, ratio={manual_volume:.6f}", flush=True)
            
            # Get news signals (if enabled)
            if news_config.get('enabled', True) and news_analyzer:
                news_signals = news_analyzer.analyze_news_for_ticker(ticker, lookback_start, date_str)
                # DEBUG: Check if news signals are actually being calculated
                if idx == 1 and ticker in list(prices_dict.keys())[:3]:
                    print(f"    [DEBUG] {ticker} news signals: supply_chain={news_signals.get('supply_chain_score', 0):.6f}, sentiment={news_signals.get('sentiment_score', 0):.6f}, confidence={news_signals.get('confidence', 0):.6f}", flush=True)
            else:
                news_signals = {'supply_chain_score': 0.0, 'sentiment_score': 0.0, 'confidence': 0.0}
                if idx == 1 and ticker in list(prices_dict.keys())[:3]:
                    print(f"    [DEBUG] {ticker} news disabled or analyzer unavailable", flush=True)
            
            # DEBUG: Check if news signals are all zero (indicates no news data)
            if idx == 1 and ticker in list(prices_dict.keys())[:3]:
                print(f"    [DEBUG] {ticker} news signals: {news_signals}", flush=True)
            
            # Prepare technical signals for combiner
            tech_for_combiner = {
                'momentum_score': tech_signals.get('momentum_score', 0.0),
                'volume_score': tech_signals.get('volume_score', 1.0),
                'rsi_score': tech_signals.get('rsi_score', 0.5)
            }
            
            # For technical-only mode, we need to handle RSI separately since combine_signals_direct doesn't use it
            # Instead, combine momentum and RSI before passing to combiner
            if args.technical_only:
                momentum = tech_for_combiner['momentum_score']
                rsi = tech_for_combiner['rsi_score']
                momentum_weight = weights.get('momentum', 0.5)
                rsi_weight = weights.get('rsi', 0.2)
                volume_weight = weights.get('volume', 0.3)
                total_tech = momentum_weight + rsi_weight + volume_weight
                
                if total_tech > 0:
                    # Normalize weights
                    momentum_weight_norm = momentum_weight / total_tech
                    rsi_weight_norm = rsi_weight / total_tech
                    volume_weight_norm = volume_weight / total_tech
                    
                    # Combine momentum and RSI into a single momentum score
                    combined_momentum = (momentum * momentum_weight_norm + rsi * rsi_weight_norm) / (momentum_weight_norm + rsi_weight_norm) if (momentum_weight_norm + rsi_weight_norm) > 0 else momentum
                    
                    tech_for_combiner['momentum_score'] = combined_momentum
                    # Adjust weights for combiner (momentum now includes RSI)
                    combiner_weights = {
                        'supply_chain': 0.0,
                        'sentiment': 0.0,
                        'momentum': momentum_weight_norm + rsi_weight_norm,
                        'volume': volume_weight_norm
                    }
                else:
                    combiner_weights = weights
            elif args.news_only:
                # News-only: set technical weights to 0
                combiner_weights = {
                    'supply_chain': weights.get('supply_chain', 0.5),
                    'sentiment': weights.get('sentiment', 0.5),
                    'momentum': 0.0,
                    'volume': 0.0
                }
            else:
                # Combined mode: use all weights, but RSI is not in combine_signals_direct
                # So we combine momentum and RSI first
                momentum = tech_for_combiner['momentum_score']
                rsi = tech_for_combiner['rsi_score']
                momentum_weight = weights.get('momentum', 0.2)
                rsi_weight = weights.get('rsi', 0.0)  # RSI not in default weights
                
                if rsi_weight > 0 and momentum_weight > 0:
                    # Combine momentum and RSI
                    total_momentum_rsi = momentum_weight + rsi_weight
                    combined_momentum = (momentum * momentum_weight + rsi * rsi_weight) / total_momentum_rsi
                    tech_for_combiner['momentum_score'] = combined_momentum
                    combiner_weights = {
                        'supply_chain': weights.get('supply_chain', 0.4),
                        'sentiment': weights.get('sentiment', 0.3),
                        'momentum': total_momentum_rsi,
                        'volume': weights.get('volume', 0.1)
                    }
                else:
                    combiner_weights = weights
            
            # DEBUG: Store first week's data for ALL tickers to compare
            if idx == 1:
                debug_scores[ticker] = {
                    'tech': tech_for_combiner.copy(),
                    'news': news_signals.copy(),
                    'weights': combiner_weights.copy(),
                    'combined_score': 0.0  # Will be set below
                }
            
            # DEBUG: Print before combination for first ticker of first week
            if idx == 1 and ticker == list(prices_dict.keys())[0]:
                print(f"\n[DEBUG] Combining signals for {ticker} on {date_str}:", flush=True)
                print(f"  Mode: {'TECHNICAL-ONLY' if args.technical_only else 'NEWS-ONLY' if args.news_only else 'COMBINED'}", flush=True)
                print(f"  Tech signals: {tech_for_combiner}", flush=True)
                print(f"  News signals: {news_signals}", flush=True)
                print(f"  Weights: {combiner_weights}", flush=True)
                print(f"  Weight sum: {sum(combiner_weights.values()):.3f}", flush=True)
                
                # CRITICAL: Verify weights are correct for this mode
                mode_name = 'TECHNICAL-ONLY' if args.technical_only else 'NEWS-ONLY' if args.news_only else 'COMBINED'
                if args.technical_only:
                    assert combiner_weights.get('supply_chain', -1) == 0.0, f"Technical-only mode but supply_chain weight is {combiner_weights.get('supply_chain')}"
                    assert combiner_weights.get('sentiment', -1) == 0.0, f"Technical-only mode but sentiment weight is {combiner_weights.get('sentiment')}"
                    assert combiner_weights.get('momentum', 0) > 0, f"Technical-only mode but momentum weight is {combiner_weights.get('momentum')}"
                    print(f"  [OK] Technical-only weights verified", flush=True)
                elif args.news_only:
                    assert combiner_weights.get('momentum', -1) == 0.0, f"News-only mode but momentum weight is {combiner_weights.get('momentum')}"
                    assert combiner_weights.get('volume', -1) == 0.0, f"News-only mode but volume weight is {combiner_weights.get('volume')}"
                    assert combiner_weights.get('supply_chain', 0) > 0 or combiner_weights.get('sentiment', 0) > 0, f"News-only mode but both news weights are 0: {combiner_weights}"
                    print(f"  [OK] News-only weights verified", flush=True)
                else:
                    assert combiner_weights.get('supply_chain', 0) > 0 or combiner_weights.get('sentiment', 0) > 0, f"Combined mode but both news weights are 0: {combiner_weights}"
                    assert combiner_weights.get('momentum', 0) > 0 or combiner_weights.get('volume', 0) > 0, f"Combined mode but both tech weights are 0: {combiner_weights}"
                    print(f"  [OK] Combined mode weights verified", flush=True)
            
            # CRITICAL FIX: If news-only mode and news signals are all 0.0, use technical signals as fallback
            # Otherwise all stocks get score 0.0 and selection is arbitrary, making results identical
            # Use DIFFERENT weights than technical-only to ensure different results
            if args.news_only:
                news_total = abs(news_signals.get('supply_chain_score', 0.0)) + abs(news_signals.get('sentiment_score', 0.0))
                if news_total < 0.001:  # All news signals are essentially 0
                    # Fallback: use technical signals with DIFFERENT weights than technical-only
                    # Technical-only uses: momentum*0.7 + volume*0.3 (after RSI combination)
                    # News-only fallback uses: momentum*0.4 + volume*0.6 to ensure different ranking
                    # Use the same normalization as combine_signals_direct for consistency
                    momentum = tech_for_combiner['momentum_score']
                    volume = tech_for_combiner['volume_score']
                    import numpy as np
                    if momentum != 0:
                        tech_momentum_norm = 1 / (1 + np.exp(-momentum * 10))
                    else:
                        tech_momentum_norm = 0.5
                    tech_volume_norm = min(1.0, max(0.0, (volume - 0.5) / 2.5)) if volume > 0 else 0.5
                    # Use different weights: 0.4 momentum, 0.6 volume (vs tech-only: 0.7 momentum+RSI, 0.3 volume)
                    combined_score = tech_momentum_norm * 0.4 + tech_volume_norm * 0.6
                    if idx == 1 and ticker == list(prices_dict.keys())[0]:
                        print(f"  [WARNING] News-only mode but no news data! Using technical fallback with weights (0.4, 0.6).", flush=True)
                        print(f"  Fallback score: {combined_score:.6f} (should differ from tech-only)", flush=True)
                else:
                    # News signals exist, use normal combination
                    combined_score = signal_combiner.combine_signals_direct(
                        tech_for_combiner, news_signals, combiner_weights
                    )
            else:
                # Technical-only or combined mode: use normal combination
                combined_score = signal_combiner.combine_signals_direct(
                    tech_for_combiner, news_signals, combiner_weights
                )
            
            # Store combined score in debug
            if idx == 1:
                debug_scores[ticker]['combined_score'] = combined_score
            
            scores[ticker] = combined_score
        except Exception as e:
            print(f"    [WARNING] Error processing {ticker} on {date_str}: {e}", flush=True)
            continue
    
    if scores:
        # DEBUG: Print score statistics for first week
        if idx == 1:
            score_values = list(scores.values())
            unique_scores = len(set(score_values))
            print(f"\n[DEBUG] First week score stats: min={min(score_values):.6f}, max={max(score_values):.6f}, mean={np.mean(score_values):.6f}, std={np.std(score_values):.6f}, unique={unique_scores}/{len(score_values)}", flush=True)
            print(f"[DEBUG] Top 10 tickers with scores (RANKING):", flush=True)
            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            for rank, (ticker, score) in enumerate(sorted_scores[:10], 1):
                print(f"  {rank}. {ticker}: {score:.6f}", flush=True)
            
            # Check if all scores are identical (would indicate a bug)
            if unique_scores == 1:
                print(f"[ERROR] All scores are identical! This indicates a bug in signal combination.", flush=True)
            elif np.std(score_values) < 0.01:
                print(f"[WARNING] Scores have very low variance (std={np.std(score_values):.6f}). Rankings may be arbitrary.", flush=True)
        
        top_tickers = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:TOP_N]
        
        # Calculate weights: proportional to scores (normalized to sum to 1.0)
        # Higher score = larger position weight
        if top_tickers:
            # Extract scores
            ticker_scores = {t: s for t, s in top_tickers}
            total_score = sum(ticker_scores.values())
            
            if total_score > 0:
                # Proportional weighting: weight = score / sum(all scores)
                weights_dict = {t: s / total_score for t, s in ticker_scores.items()}
            else:
                # Fallback to equal weights if all scores are 0
                equal_weight = 1.0 / len(top_tickers)
                weights_dict = {t: equal_weight for t, _ in top_tickers}
        else:
            weights_dict = {}
        
        # DEBUG: Print selected tickers for first week
        if idx == 1:
            print(f"[DEBUG] Selected top {TOP_N} tickers for week 1 (proportional weighting):", flush=True)
            for rank, (ticker, score) in enumerate(top_tickers, 1):
                weight = weights_dict.get(ticker, 0.0)
                print(f"  {rank}. {ticker}: {score:.6f} (weight={weight:.4f})", flush=True)
        
        # Assign proportional weights
        for ticker, weight in weights_dict.items():
            signals_df.loc[monday, ticker] = weight

print(f"  [OK] Generated signals for {len(mondays)} Mondays", flush=True)

# DEBUG: Print diagnostic information for ALL tickers
if debug_scores:
    print("\n[DEBUG] Signals for first week (all tickers):", flush=True)
    print(f"  Mode: {'Technical-only' if args.technical_only else 'News-only' if args.news_only else 'Combined'}", flush=True)
    
    # Show statistics
    all_combined_scores = [d['combined_score'] for d in debug_scores.values()]
    all_news_supply = [d['news']['supply_chain_score'] for d in debug_scores.values()]
    all_news_sentiment = [d['news']['sentiment_score'] for d in debug_scores.values()]
    all_tech_momentum = [d['tech']['momentum_score'] for d in debug_scores.values()]
    all_tech_volume = [d['tech']['volume_score'] for d in debug_scores.values()]
    
    print(f"  Combined scores: min={min(all_combined_scores):.6f}, max={max(all_combined_scores):.6f}, mean={sum(all_combined_scores)/len(all_combined_scores):.6f}, unique={len(set(all_combined_scores))}", flush=True)
    print(f"  News supply_chain: min={min(all_news_supply):.6f}, max={max(all_news_supply):.6f}, mean={sum(all_news_supply)/len(all_news_supply):.6f}", flush=True)
    print(f"  News sentiment: min={min(all_news_sentiment):.6f}, max={max(all_news_sentiment):.6f}, mean={sum(all_news_sentiment)/len(all_news_sentiment):.6f}", flush=True)
    print(f"  Tech momentum: min={min(all_tech_momentum):.6f}, max={max(all_tech_momentum):.6f}, mean={sum(all_tech_momentum)/len(all_tech_momentum):.6f}", flush=True)
    
    # Show first 5 tickers' combined scores for comparison
    print(f"\n  [DEBUG] First week combined scores (top 5 by score):", flush=True)
    sorted_debug = sorted(debug_scores.items(), key=lambda x: x[1]['combined_score'], reverse=True)[:5]
    for ticker, data in sorted_debug:
        print(f"    {ticker}: {data['combined_score']:.6f} (tech_mom={data['tech']['momentum_score']:.4f}, tech_vol={data['tech']['volume_score']:.4f}, news_supply={data['news']['supply_chain_score']:.4f}, news_sent={data['news']['sentiment_score']:.4f}, weights={data['weights']})", flush=True)
    print(f"  Tech volume: min={min(all_tech_volume):.6f}, max={max(all_tech_volume):.6f}, mean={sum(all_tech_volume)/len(all_tech_volume):.6f}", flush=True)
    
    # Show first 5 tickers in detail
    print(f"\n  First 5 tickers detail:", flush=True)
    for i, (ticker, data) in enumerate(list(debug_scores.items())[:5]):
        print(f"    {ticker}: score={data['combined_score']:.6f}, tech_mom={data['tech']['momentum_score']:.3f}, tech_vol={data['tech']['volume_score']:.3f}, news_sc={data['news']['supply_chain_score']:.3f}, news_sent={data['news']['sentiment_score']:.3f}", flush=True)
        print(f"      Weights: {data['weights']}", flush=True)

# Align prices and forward-fill signals
print("\n[4/6] Aligning data...", flush=True)
all_dates = sorted(set().union(*[df.index for df in prices_dict.values()]))
prices_df = pd.DataFrame({t: prices_dict[t]['close'] for t in prices_dict.keys()}, index=all_dates)
positions_df = pd.DataFrame(0.0, index=prices_df.index, columns=prices_df.columns)

for monday in mondays:
    if monday not in signals_df.index:
        continue
    next_days = prices_df.index[prices_df.index >= monday]
    if len(next_days) == 0:
        continue
    start_idx = prices_df.index.get_loc(next_days[0])
    next_monday = mondays[mondays > monday]
    end_idx = len(prices_df) if len(next_monday) == 0 else prices_df.index.get_loc(prices_df.index[prices_df.index < next_monday[0]][-1]) + 1
    for ticker in positions_df.columns:
        if ticker in signals_df.columns:
            positions_df.iloc[start_idx:end_idx, positions_df.columns.get_loc(ticker)] = signals_df.loc[monday, ticker]

print(f"  [OK] Aligned {len(prices_df)} trading days", flush=True)

# Run backtest
print("\n[5/6] Running backtest...", flush=True)
returns = prices_df.pct_change()
portfolio_returns = (positions_df.shift(1) * returns).sum(axis=1).fillna(0)
rebalance_dates = positions_df.diff().abs().sum(axis=1) > 0.01
portfolio_returns[rebalance_dates] -= 0.001
cumulative = (1 + portfolio_returns).cumprod()
total_return = cumulative.iloc[-1] - 1
sharpe = (portfolio_returns.mean() * 252) / (portfolio_returns.std() * np.sqrt(252)) if portfolio_returns.std() > 0 else 0.0
max_dd = ((cumulative - cumulative.expanding().max()) / cumulative.expanding().max()).min()

print("\n" + "=" * 60, "\nBACKTEST RESULTS\n" + "=" * 60)
print(f"Total Return:    {total_return:.2%}")
print(f"Sharpe Ratio:    {sharpe:.2f}")
print(f"Max Drawdown:    {max_dd:.2%}")

# DEBUG: Show final signal statistics
print("\n[DEBUG] Final Signal Statistics:", flush=True)
all_scores = []
for monday in mondays:
    if monday in signals_df.index:
        for ticker in signals_df.columns:
            score = signals_df.loc[monday, ticker]
            if score > 0:
                all_scores.append(score)

if all_scores:
    print(f"  Score range: {min(all_scores):.4f} to {max(all_scores):.4f}", flush=True)
    print(f"  Mean score: {np.mean(all_scores):.4f}", flush=True)
    print(f"  Non-zero signals: {len(all_scores)} out of {len(mondays) * len(signals_df.columns)}", flush=True)

print("=" * 60, "\n[SUCCESS] Backtest complete!")
