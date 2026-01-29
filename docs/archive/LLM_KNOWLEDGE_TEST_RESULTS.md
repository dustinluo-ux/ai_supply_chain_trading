# LLM Supply Chain Knowledge Test Results

**Test Date:** 2026-01-25 10:32

**Model:** Gemini 2.5 Flash Lite

## Summary

- Average Supplier Accuracy: **32.7%**
- Average Competitor Accuracy: **80.0%**

## Recommendation

[!] PARTIAL - LLM knowledge has gaps

**Approach:** Should create manual database for top 50-100 stocks, use LLM as supplement

## Detailed Results

```json
{
  "AAPL": {
    "suppliers": {
      "accuracy": 0.4,
      "overlap": 2,
      "total": 5,
      "llm_found": [
        "QCOM",
        "INFY",
        "SAMS",
        "TSM",
        "BRCM"
      ],
      "truth": [
        "QCOM",
        "HON",
        "TXN",
        "TSM",
        "MU"
      ],
      "correct": [
        "QCOM",
        "TSM"
      ],
      "missed": [
        "MU",
        "TXN",
        "HON"
      ],
      "wrong": [
        "INFY",
        "SAMS",
        "BRCM"
      ]
    },
    "customers": null,
    "competitors": {
      "accuracy": 0.3333333333333333,
      "overlap": 1,
      "total": 3,
      "llm_found": [
        "MSFT",
        "GOOG",
        "AMZN"
      ],
      "truth": [
        "MSFT",
        "GOOGL",
        "SAMSUNG"
      ],
      "correct": [
        "MSFT"
      ],
      "missed": [
        "SAMSUNG",
        "GOOGL"
      ],
      "wrong": [
        "GOOG",
        "AMZN"
      ]
    },
    "llm_raw": {
      "suppliers": [
        "QCOM",
        "TSM",
        "SAMS",
        "BRCM",
        "INFY"
      ],
      "customers": [],
      "competitors": [
        "GOOG",
        "MSFT",
        "AMZN"
      ]
    }
  },
  "NVDA": {
    "suppliers": {
      "accuracy": 0.4,
      "overlap": 2,
      "total": 5,
      "llm_found": [
        "UMC",
        "AMAT",
        "ASE",
        "TSM",
        "ASML"
      ],
      "truth": [
        "SMCI",
        "TSM",
        "CDNS",
        "SNPS",
        "ASML"
      ],
      "correct": [
        "TSM",
        "ASML"
      ],
      "missed": [
        "SMCI",
        "SNPS",
        "CDNS"
      ],
      "wrong": [
        "UMC",
        "AMAT",
        "ASE"
      ]
    },
    "customers": {
      "accuracy": 0.4,
      "overlap": 2,
      "total": 5,
      "llm_found": [
        "MSFT",
        "GOOG",
        "AMZN"
      ],
      "truth": [
        "MSFT",
        "TSLA",
        "META",
        "AMZN",
        "GOOGL"
      ],
      "correct": [
        "MSFT",
        "AMZN"
      ],
      "missed": [
        "META",
        "TSLA",
        "GOOGL"
      ],
      "wrong": [
        "GOOG"
      ]
    },
    "competitors": {
      "accuracy": 1.0,
      "overlap": 2,
      "total": 2,
      "llm_found": [
        "QCOM",
        "INTC",
        "AMD"
      ],
      "truth": [
        "INTC",
        "AMD"
      ],
      "correct": [
        "INTC",
        "AMD"
      ],
      "missed": [],
      "wrong": [
        "QCOM"
      ]
    },
    "llm_raw": {
      "suppliers": [
        "TSM",
        "UMC",
        "ASE",
        "AMAT",
        "ASML"
      ],
      "customers": [
        "MSFT",
        "GOOG",
        "AMZN"
      ],
      "competitors": [
        "AMD",
        "INTC",
        "QCOM"
      ]
    }
  },
  "AMD": {
    "suppliers": {
      "accuracy": 0.5,
      "overlap": 1,
      "total": 2,
      "llm_found": [
        "UMC",
        "ASE",
        "TSM",
        "JCET",
        "SPIL"
      ],
      "truth": [
        "GFS",
        "TSM"
      ],
      "correct": [
        "TSM"
      ],
      "missed": [
        "GFS"
      ],
      "wrong": [
        "UMC",
        "ASE",
        "JCET",
        "SPIL"
      ]
    },
    "customers": {
      "accuracy": 0.5,
      "overlap": 1,
      "total": 2,
      "llm_found": [
        "MSFT",
        "DELL",
        "HPQ",
        "AMZN",
        "GOOG"
      ],
      "truth": [
        "MSFT",
        "SONY"
      ],
      "correct": [
        "MSFT"
      ],
      "missed": [
        "SONY"
      ],
      "wrong": [
        "DELL",
        "HPQ",
        "GOOG",
        "AMZN"
      ]
    },
    "competitors": {
      "accuracy": 1.0,
      "overlap": 2,
      "total": 2,
      "llm_found": [
        "NVDA",
        "INTC",
        "ARM",
        "QCOM"
      ],
      "truth": [
        "NVDA",
        "INTC"
      ],
      "correct": [
        "NVDA",
        "INTC"
      ],
      "missed": [],
      "wrong": [
        "QCOM",
        "ARM"
      ]
    },
    "llm_raw": {
      "suppliers": [
        "TSM",
        "UMC",
        "ASE",
        "SPIL",
        "JCET"
      ],
      "customers": [
        "DELL",
        "HPQ",
        "MSFT",
        "AMZN",
        "GOOG"
      ],
      "competitors": [
        "INTC",
        "NVDA",
        "QCOM",
        "ARM"
      ]
    }
  },
  "TSLA": {
    "suppliers": {
      "accuracy": 0.0,
      "overlap": 0,
      "total": 4,
      "llm_found": [
        "PANW",
        "AMD",
        "NVDA",
        "CAT",
        "LGND"
      ],
      "truth": [
        "LG",
        "PANASONIC",
        "CATL",
        "SAMSUNG"
      ],
      "correct": [],
      "missed": [
        "LG",
        "PANASONIC",
        "CATL",
        "SAMSUNG"
      ],
      "wrong": [
        "PANW",
        "AMD",
        "NVDA",
        "CAT",
        "LGND"
      ]
    },
    "customers": null,
    "competitors": {
      "accuracy": 1.0,
      "overlap": 3,
      "total": 3,
      "llm_found": [
        "GM",
        "XPENG",
        "RIVN",
        "F",
        "NIO"
      ],
      "truth": [
        "RIVN",
        "GM",
        "F"
      ],
      "correct": [
        "RIVN",
        "GM",
        "F"
      ],
      "missed": [],
      "wrong": [
        "XPENG",
        "NIO"
      ]
    },
    "llm_raw": {
      "suppliers": [
        "PANW",
        "NVDA",
        "AMD",
        "LGND",
        "CAT"
      ],
      "customers": [],
      "competitors": [
        "F",
        "GM",
        "RIVN",
        "NIO",
        "XPENG"
      ]
    }
  },
  "MSFT": {
    "suppliers": {
      "accuracy": 0.3333333333333333,
      "overlap": 1,
      "total": 3,
      "llm_found": [
        "INTEL",
        "AMD",
        "TSMC",
        "FOXCONN",
        "QUALCOMM"
      ],
      "truth": [
        "NVDA",
        "INTC",
        "AMD"
      ],
      "correct": [
        "AMD"
      ],
      "missed": [
        "NVDA",
        "INTC"
      ],
      "wrong": [
        "INTEL",
        "QUALCOMM",
        "TSMC",
        "FOXCONN"
      ]
    },
    "customers": null,
    "competitors": {
      "accuracy": 0.6666666666666666,
      "overlap": 2,
      "total": 3,
      "llm_found": [
        "ORCL",
        "IBM",
        "AAPL",
        "AMZN",
        "GOOG"
      ],
      "truth": [
        "AAPL",
        "GOOGL",
        "AMZN"
      ],
      "correct": [
        "AAPL",
        "AMZN"
      ],
      "missed": [
        "GOOGL"
      ],
      "wrong": [
        "ORCL",
        "IBM",
        "GOOG"
      ]
    },
    "llm_raw": {
      "suppliers": [
        "AMD",
        "Intel",
        "Qualcomm",
        "TSMC",
        "Foxconn"
      ],
      "customers": [
        "Accenture",
        "Deloitte",
        "EY",
        "PwC",
        "KPMG"
      ],
      "competitors": [
        "GOOG",
        "AMZN",
        "AAPL",
        "ORCL",
        "IBM"
      ]
    }
  }
}
```

## Analysis

### Supplier Accuracy Breakdown

**AAPL:** 40.0%
- Correct: ['QCOM', 'TSM']
- Missed: ['MU', 'TXN', 'HON']
- Wrong: ['INFY', 'SAMS', 'BRCM']

**NVDA:** 40.0%
- Correct: ['TSM', 'ASML']
- Missed: ['SMCI', 'SNPS', 'CDNS']
- Wrong: ['UMC', 'AMAT', 'ASE']

**AMD:** 50.0%
- Correct: ['TSM']
- Missed: ['GFS']
- Wrong: ['UMC', 'ASE', 'JCET', 'SPIL']

**TSLA:** 0.0%
- Correct: []
- Missed: ['LG', 'PANASONIC', 'CATL', 'SAMSUNG']
- Wrong: ['PANW', 'AMD', 'NVDA', 'CAT', 'LGND']

**MSFT:** 33.3%
- Correct: ['AMD']
- Missed: ['NVDA', 'INTC']
- Wrong: ['INTEL', 'QUALCOMM', 'TSMC', 'FOXCONN']

### Error Patterns

**Systematic Errors:**
1. **Ticker Format Issues:**
   - LLM uses "GOOG" instead of "GOOGL" (Alphabet)
   - LLM uses "INTEL" instead of "INTC" (Intel)
   - LLM uses company names instead of tickers (e.g., "TSMC" vs "TSM", "Qualcomm" vs "QCOM")

2. **Supplier Knowledge Gaps:**
   - **TSLA (0% accuracy):** LLM completely missed battery suppliers (LG, Panasonic, CATL, Samsung)
   - LLM confused suppliers with other relationships (e.g., TSLA suppliers listed as PANW, AMD, NVDA - these are tech suppliers, not battery suppliers)
   - LLM often lists semiconductor foundries (TSM, UMC, ASE) even when not applicable

3. **Customer Knowledge:**
   - LLM struggles with B2B customer relationships
   - Often lists indirect customers or partners instead of direct customers
   - Example: MSFT customers listed as consulting firms (Accenture, Deloitte) instead of actual product customers

4. **Competitor Accuracy (80%):**
   - LLM is much better at identifying competitors
   - Main issue: Ticker format (GOOG vs GOOGL)
   - Sometimes includes adjacent competitors (e.g., QCOM for NVDA/AMD - not direct competitors)

**Random Errors:**
- Some relationships are simply wrong (e.g., INFY, SAMS, BRCM for AAPL suppliers)
- LLM sometimes includes companies from adjacent industries

### Key Findings

1. **Supplier Accuracy: 32.7%** - POOR
   - Cannot rely on LLM for supplier relationships
   - Many critical suppliers missed (e.g., TSLA battery suppliers completely missed)
   - High false positive rate (wrong suppliers listed)

2. **Competitor Accuracy: 80.0%** - GOOD
   - LLM is reliable for competitor identification
   - Main issue is ticker format, not knowledge
   - Can use LLM for competitors with ticker normalization

3. **Customer Accuracy: ~40%** - PARTIAL
   - LLM struggles with B2B customer relationships
   - Often confuses partners/consultants with customers
   - Better for well-known B2B relationships (e.g., NVDA → MSFT, AMZN)

### Recommendations

**For Supply Chain Network Propagation (#2):**

1. **Build Manual Database (Priority 1):**
   - Create manual database for top 50-100 stocks in universe
   - Focus on supplier relationships (LLM is weakest here)
   - Sources: 10-K filings, Bloomberg, Reuters, company websites
   - Format: JSON/CSV with ticker → {suppliers: [], customers: [], competitors: []}

2. **Use LLM as Supplement (Priority 2):**
   - Use LLM for competitor relationships (80% accuracy, just need ticker normalization)
   - Use LLM for validation of manual database
   - Use LLM for less common stocks (outside top 50-100) with low confidence scores

3. **Implement Confidence Scoring:**
   - High confidence: Manual database relationships
   - Medium confidence: LLM-extracted competitors (with ticker normalization)
   - Low confidence: LLM-extracted suppliers/customers (use sparingly)

4. **Ticker Normalization:**
   - Create mapping: GOOG → GOOGL, INTEL → INTC, TSMC → TSM, etc.
   - Normalize all LLM responses before comparison
   - This alone would improve competitor accuracy to ~90%

5. **Validation Layer:**
   - Cross-check LLM responses against manual database
   - Flag relationships that seem wrong (e.g., TSLA suppliers = PANW, AMD, NVDA)
   - Use industry knowledge to filter obvious errors

### Implementation Plan

**Phase 1: Manual Database (Week 1-2)**
- Build database for top 50 stocks
- Focus on supplier relationships
- Include customers and competitors for completeness

**Phase 2: LLM Integration (Week 3)**
- Use LLM for competitor relationships (with normalization)
- Use LLM for validation
- Implement confidence scoring

**Phase 3: Network Propagation (Week 4)**
- Implement propagation logic using manual database
- Add LLM supplement for stocks not in database
- Test with news articles to verify propagation works

### Conclusion

**LLM cannot be trusted as primary source for supplier relationships.** The 32.7% accuracy is too low for production use. However, LLM is reliable for competitors (80% accuracy) and can be used as a supplement with proper validation.

**Recommended Approach:**
- Manual database for top 50-100 stocks (suppliers, customers, competitors)
- LLM for competitor relationships (with ticker normalization)
- LLM for validation and less common stocks
- Confidence scoring to weight relationships appropriately
