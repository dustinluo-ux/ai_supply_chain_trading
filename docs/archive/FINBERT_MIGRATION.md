# Migration to FinBERT Only

## Changes Made

The system has been updated to use **FinBERT only** (local, free) instead of Claude API. This eliminates the need for ANTHROPIC_API_KEY and reduces costs.

### Updated Files

1. **config/config.yaml**
   - Changed default provider from "anthropic" to "finbert"
   - Removed Claude-specific model configuration

2. **src/signals/llm_analyzer.py**
   - Removed Claude API support
   - Default provider is now "finbert"
   - Removed `_extract_with_claude()` method (kept for reference but not used)

3. **src/signals/supply_chain_scanner.py**
   - Default provider changed to "finbert"
   - Removed Claude API rate limiting

4. **requirements.txt**
   - Removed `anthropic` package dependency

5. **setup_env.py**
   - Removed ANTHROPIC_API_KEY from template

6. **Documentation**
   - Updated README.md, QUICKSTART.md, and other docs to reflect FinBERT-only approach

### What FinBERT Provides

✅ **Sentiment Analysis**: High-quality financial sentiment scoring (positive/negative/neutral)
✅ **AI Relevance Detection**: Keyword-based detection of AI supply chain mentions
✅ **Free & Local**: No API costs, no rate limits
✅ **Fast Processing**: Runs locally, no network latency

### Limitations

⚠️ **Supply Chain Extraction**: FinBERT cannot extract structured relationships (supplier, customer, product) like Claude can. The system now uses keyword-based detection for AI relevance.

⚠️ **Extraction Quality**: For supply chain relationships, the system relies on:
- Keyword matching for AI relevance
- Sentiment scoring for article tone
- Aggregation of mentions across articles

### Impact on Strategy

The signal generation still works effectively because:
1. **Supply Chain Score**: Based on aggregated AI-related mentions (keyword-based)
2. **Sentiment**: High-quality FinBERT sentiment analysis
3. **Technical Indicators**: Unchanged (price momentum, volume, RSI)
4. **Composite Signal**: All components still contribute to ranking

The strategy will still identify AI supply chain beneficiaries, but relies more on:
- Volume of AI-related mentions (keyword matching)
- Sentiment momentum (FinBERT)
- Technical indicators (unchanged)

### No Action Required

If you were using Claude API:
- ✅ System now uses FinBERT automatically
- ✅ No code changes needed
- ✅ Remove ANTHROPIC_API_KEY from .env (optional cleanup)

If you were already using FinBERT:
- ✅ No changes needed
- ✅ System continues to work as before

### Testing

Run the test to verify FinBERT is working:
```bash
python run_phase1_test.py
```

The LLM analyzer test will use FinBERT and should complete successfully.
