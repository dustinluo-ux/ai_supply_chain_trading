# Gemini 2.0 Flash Migration Guide

## Overview

The system now supports **Gemini 2.0 Flash** for news analysis, replacing FinBERT/Claude API. Gemini provides better supply chain extraction with structured JSON output.

## Setup

### 1. Install Library

```bash
pip install google-generativeai
```

### 2. Get API Key

1. Go to: https://aistudio.google.com/app/apikey
2. Create a free API key
3. Add to `.env` file:
   ```
   GEMINI_API_KEY=your_key_here
   ```

### 3. Update Configuration

Edit `config/config.yaml`:
```yaml
llm:
  provider: "gemini"  # Changed from "finbert"
  model: "gemini-2.0-flash-exp"
```

## Features

### Gemini 2.0 Flash Advantages

✅ **Better Extraction**: Extracts supplier, customer_type, product relationships
✅ **Structured Output**: Native JSON mode ensures valid responses
✅ **Free Tier**: Generous free tier available
✅ **Fast**: Optimized for speed (Flash model)
✅ **Accurate**: Better understanding of supply chain relationships

### Output Format

Gemini returns:
```json
{
  "supplier": "Western Digital",
  "customer_type": "hyperscaler",
  "product": "storage solutions",
  "ai_related": true,
  "sentiment": "positive",
  "relevance_score": 0.85
}
```

This is automatically mapped to the standard format used by the pipeline.

## Integration

The Gemini analyzer integrates seamlessly with the existing framework:

1. **Modular Design**: `src/signals/gemini_analyzer.py` - standalone analyzer
2. **LLM Analyzer Wrapper**: `src/signals/llm_analyzer.py` - supports both FinBERT and Gemini
3. **Supply Chain Scanner**: Automatically uses configured provider
4. **No Code Changes**: Just change `config.yaml` to switch providers

## Usage

### Switch to Gemini

1. Set `llm.provider: "gemini"` in `config.yaml`
2. Add `GEMINI_API_KEY` to `.env`
3. Run pipeline as normal:
   ```bash
   python run_phase2_pipeline.py
   ```

### Switch Back to FinBERT

1. Set `llm.provider: "finbert"` in `config.yaml`
2. No API key needed
3. Run pipeline as normal

## Rate Limiting

Gemini free tier limits:
- **15 requests per minute** (RPM)
- **1,500 requests per day** (RPD)

The analyzer includes:
- Automatic rate limiting (0.5s delay between calls)
- Retry logic (3 attempts with 2s delay)
- Progress logging every 10 articles

## Error Handling

The analyzer includes comprehensive error handling:
- **API Errors**: Retries up to 3 times
- **JSON Parse Errors**: Falls back to default extraction
- **Rate Limit Errors**: Automatic retry with backoff
- **Network Errors**: Graceful degradation

## Testing

Test the Gemini analyzer:

```bash
python src/signals/gemini_analyzer.py
```

This will test with a sample article and show the extraction result.

## Comparison

| Feature | FinBERT | Gemini 2.0 Flash |
|---------|---------|------------------|
| **Cost** | Free (local) | Free tier available |
| **Setup** | Install transformers/torch | Install google-generativeai |
| **Speed** | Fast (local) | Fast (API) |
| **Extraction** | Sentiment only | Full supply chain extraction |
| **Accuracy** | Good for sentiment | Better for relationships |
| **Dependencies** | Heavy (torch) | Light (API client) |

## Migration Checklist

- [x] Created `src/signals/gemini_analyzer.py`
- [x] Updated `src/signals/llm_analyzer.py` to support Gemini
- [x] Updated `config/config.yaml` with Gemini option
- [x] Updated `requirements.txt` with google-generativeai
- [x] Updated `setup_env.py` with GEMINI_API_KEY
- [x] Integrated with existing supply chain scanner
- [ ] Test with real news articles
- [ ] Verify JSON output format
- [ ] Test rate limiting

## Next Steps

1. Install: `pip install google-generativeai`
2. Add API key to `.env`
3. Set `provider: "gemini"` in `config.yaml`
4. Run pipeline: `python run_phase2_pipeline.py`

The system is ready to use Gemini 2.0 Flash for news analysis!
