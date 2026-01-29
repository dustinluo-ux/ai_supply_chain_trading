# Defensive Coding Guide

## Overview

The pipeline now includes comprehensive defensive coding to prevent silent hangs and provide detailed error messages.

## Features

### 1. **File Operation Wrappers**
All file operations are wrapped with try-except and detailed error messages:
- `safe_read_parquet()` - Read parquet files
- `safe_write_parquet()` - Write parquet files
- `safe_read_csv()` - Read CSV files
- `safe_write_csv()` - Write CSV files
- `safe_read_json()` - Read JSON files
- `safe_write_json()` - Write JSON files
- `safe_read_yaml()` - Read YAML files
- `safe_write_yaml()` - Write YAML files

**Example:**
```python
from src.utils.defensive import safe_read_parquet

# Instead of: df = pd.read_parquet("data/prices/AAPL.parquet")
df = safe_read_parquet("data/prices/AAPL.parquet")
# Automatically handles FileNotFoundError, PermissionError, etc.
```

### 2. **Timeout Decorators**
All long-running operations have 5-minute timeouts:

```python
from src.utils.defensive import with_timeout

@with_timeout(timeout_seconds=300, operation_name="Generate Signals")
def generate_signals():
    # This will timeout after 5 minutes if it hangs
    ...
```

### 3. **Progress Logging**
Progress is logged every 10 seconds for long-running operations:

```python
from src.utils.defensive import ProgressLogger

progress = ProgressLogger(interval_seconds=10, operation_name="Processing Tickers")
progress.start(total_items=len(tickers))

for idx, ticker in enumerate(tickers, 1):
    progress.update(ticker, current_index=idx, total=len(tickers))
    # Process ticker...

progress.finish()
```

**Output:**
```
[PROGRESS] Still processing Processing Tickers: AAPL (5/31) - 45.2s elapsed
[PROGRESS] Still processing Processing Tickers: MSFT (10/31) - 95.8s elapsed
```

### 4. **Debug Mode**
Enable verbose logging with `--debug` flag:

```bash
python run_technical_backtest.py --debug
```

**Debug mode shows:**
- All file operations (read/write)
- Function arguments and return values
- Detailed tracebacks
- Progress updates every operation

### 5. **Error Handling**
All errors include:
- Detailed error messages
- Full tracebacks
- Context (file paths, function names, etc.)
- No silent failures

## Usage

### Running with Debug Mode

```bash
# Normal mode
python run_technical_backtest.py

# Debug mode (verbose)
python run_technical_backtest.py --debug
```

### Example Error Output

**Without defensive coding:**
```
Error: File not found
```

**With defensive coding:**
```
[ERROR] File not found in read parquet (safe_read_parquet): data/prices/AAPL.parquet
[ERROR] Full path attempted: C:\Users\...\data\prices\AAPL.parquet
[ERROR] Traceback:
  File "...", line X, in safe_read_parquet
    return pd.read_parquet(file_path, **kwargs)
  ...
```

### Timeout Example

If an operation hangs:
```
[TIMEOUT] Starting Generate Signals (max 300s)
[ERROR] Generate Signals exceeded timeout of 300s (elapsed: 300.0s)
[ERROR] Function: generate_signals
[ERROR] Traceback: ...
TimeoutError: Generate Signals exceeded timeout of 300s
```

## Implementation Status

### ✅ Completed
- `src/utils/defensive.py` - Core defensive utilities
- `run_technical_backtest.py` - Updated with defensive coding
- File operation wrappers
- Timeout decorators
- Progress logging
- Debug mode support

### 🔄 To Be Updated
- `run_phase2_pipeline.py` - Add defensive coding
- `run_phase3_backtest.py` - Add defensive coding
- `run_strategy.py` - Add defensive coding
- All signal generation modules
- All data loading modules

## Best Practices

1. **Always use safe file operations:**
   ```python
   # ❌ Bad
   df = pd.read_parquet("data/file.parquet")
   
   # ✅ Good
   from src.utils.defensive import safe_read_parquet
   df = safe_read_parquet("data/file.parquet")
   ```

2. **Add timeouts to long-running functions:**
   ```python
   # ❌ Bad
   def process_data():
       # Could hang forever
       ...
   
   # ✅ Good
   @with_timeout(timeout_seconds=300, operation_name="Process Data")
   def process_data():
       ...
   ```

3. **Add progress logging for loops:**
   ```python
   # ❌ Bad
   for item in items:
       process(item)
   
   # ✅ Good
   progress = ProgressLogger(interval_seconds=10, operation_name="Processing")
   progress.start(total_items=len(items))
   for idx, item in enumerate(items, 1):
       progress.update(item, current_index=idx, total=len(items))
       process(item)
   progress.finish()
   ```

4. **Enable debug mode when troubleshooting:**
   ```bash
   python run_technical_backtest.py --debug
   ```

## Testing

To test defensive coding:

1. **Test file operations:**
   - Try reading non-existent file
   - Check error messages are detailed

2. **Test timeouts:**
   - Add infinite loop in function
   - Verify timeout after 5 minutes

3. **Test progress logging:**
   - Run long operation
   - Verify progress logs every 10 seconds

4. **Test debug mode:**
   - Run with `--debug` flag
   - Verify verbose logging

## Next Steps

1. Update remaining pipeline scripts
2. Add defensive coding to all data loaders
3. Add defensive coding to all signal generators
4. Add unit tests for defensive utilities
