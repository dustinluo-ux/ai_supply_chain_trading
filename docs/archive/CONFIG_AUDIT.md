# Configuration Audit

**Date:** 2026-01-28  
**Purpose:** Review all config files for conflicts, defaults, documentation, and dead parameters

---

## Config Files

1. `config/data_config.yaml` - Data sources and universe selection
2. `config/model_config.yaml` - ML model configuration
3. `config/signal_weights.yaml` - Signal weights and parameters
4. `config/trading_config.yaml` - Trading mode and IB settings
5. `config/config.yaml` - (if exists, not found in scan)

---

## 1. Conflicts

### Date Ranges
- **`data_config.yaml`:** `2020-01-01` to `2024-12-31`
- **`data_config.yaml` (news):** `2023-01-01` to `2024-12-31`
- **`model_config.yaml` (training):** `2022-09-01` to `2022-11-30`
- **Status:** ✅ No conflicts - different purposes (universe selection, news data, model training)

### Lookback Days
- **`data_config.yaml`:** `lookback_days: 7`
- **`signal_weights.yaml`:** `lookback_days: 7`
- **`model_config.yaml`:** `news_lookback_days: 7`
- **Status:** ✅ Consistent across all configs

### Period Parameters
- **`signal_weights.yaml`:** `momentum_period: 20`, `volume_period: 30`, `rsi_period: 14`
- **`model_config.yaml`:** `momentum_window: 20`, `volume_window: 30`, `rsi_window: 14`
- **Status:** ✅ Consistent values, different naming (acceptable)

---

## 2. Defaults

### Sensible Defaults
- ✅ `max_tickers: 15` - Reasonable for backtest
- ✅ `min_data_points: 100` - Allows partial data
- ✅ `min_price: 1.0` - Excludes penny stocks
- ✅ `signal_weights` sum to 1.0 - Proper normalization
- ✅ `use_ml: false` - Safe default (weighted signals)

### Potentially Problematic
- ⚠️ `data_config.yaml` line 8: Hard-coded OneDrive path (not portable)
- ⚠️ `trading_config.yaml` line 30: Placeholder account `"DU123456"` (should be documented)

---

## 3. Missing Documentation

### Undocumented Parameters
- ✅ Most parameters have comments
- ⚠️ `data_config.yaml` line 8: Hard-coded path not explained
- ⚠️ `trading_config.yaml` line 30: Account format not documented

### Parameter Descriptions
- ✅ Most parameters have inline comments
- ✅ Clear purpose for each section

---

## 4. Dead Parameters

### Potentially Unused
- ⚠️ `model_config.yaml` lines 29-36: Commented model definitions (random_forest, lightgbm)
  - **Status:** Intentional placeholders for future models
  - **Action:** None (documented as placeholders)

### Config Values Not Used
- ✅ All active config values appear to be used
- ✅ `use_ml: false` means ML configs are ignored (intentional)

---

## 5. Configuration Structure

### Organization
- ✅ Well-organized by purpose
- ✅ Clear section headers
- ✅ Logical grouping

### Redundancy
- ⚠️ Some parameters duplicated across files (e.g., `lookback_days`)
- **Status:** Acceptable - different contexts (data loading vs signal weights)
- **Action:** None (intentional separation of concerns)

---

## Summary

**Conflicts:** None found

**Defaults:** All sensible except hard-coded path

**Documentation:** Good, minor gaps in path/account documentation

**Dead Parameters:** None (commented placeholders are intentional)

**Action Items:**
1. ⚠️ Replace hard-coded OneDrive path with relative path or env variable
2. ⚠️ Document account format in `trading_config.yaml`
3. ✅ All other configs are clean and well-documented

---

**Status:** Configuration files are well-structured with minor improvements needed for portability.
