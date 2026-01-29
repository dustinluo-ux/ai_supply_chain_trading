"""
Test Gemini-based supply chain ranking on 3 sample stocks.

Test Cases:
1. AAL (American Airlines) - Should NOT score high (<0.3)
2. NVDA (NVIDIA) - Should score high (>0.8)
3. AEM (Agnico Eagle Mines) - Should NOT score high (<0.3)
"""
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.signals.supply_chain_scanner import SupplyChainScanner

def test_stock(ticker: str, expected_score_range: tuple, expected_high: bool) -> Dict:
    """
    Test a single stock's supply chain scoring.
    
    Args:
        ticker: Stock ticker
        expected_score_range: (min, max) expected score
        expected_high: True if should score high, False if should score low
        
    Returns:
        Dict with test results
    """
    print(f"\n{'='*80}")
    print(f"TESTING: {ticker}")
    print(f"{'='*80}")
    
    # Initialize scanner with Gemini
    scanner = SupplyChainScanner(
        llm_provider="gemini",
        llm_model="gemini-2.5-flash-lite",
        data_dir="data/news",
        output_dir="data"
    )
    
    # Load articles
    articles = scanner.load_articles_for_ticker(ticker)
    print(f"  Loaded {len(articles)} articles")
    
    if not articles:
        return {
            'ticker': ticker,
            'status': 'NO_ARTICLES',
            'error': 'No news articles found'
        }
    
    # Show sample headlines
    print(f"\n  Sample headlines (first 3):")
    sample_headlines = []
    for i, article in enumerate(articles[:3], 1):
        title = article.get('title', 'N/A')
        desc = article.get('description', '')[:100] if article.get('description') else ''
        print(f"    {i}. {title}")
        if desc:
            print(f"       {desc}...")
        sample_headlines.append({
            'title': title,
            'description': desc
        })
    
    # Process articles (use cache if available, but force fresh analysis)
    print(f"\n  Processing articles with Gemini...")
    extractions = scanner.process_ticker_articles(ticker, articles, use_cache=True)
    
    if not extractions:
        return {
            'ticker': ticker,
            'status': 'NO_EXTRACTIONS',
            'error': 'No extractions generated'
        }
    
    # Aggregate results
    aggregated = scanner.aggregate_supply_chain_mentions(extractions)
    
    # Calculate score
    score = scanner.calculate_supply_chain_score(aggregated)
    
    # Analyze results
    ai_related_count = sum(1 for e in extractions if e.get('ai_related', False))
    supplier_mentions = sum(1 for e in extractions if e.get('supplier') and e.get('supplier') is not None)
    customer_mentions = sum(1 for e in extractions if e.get('customer') and e.get('customer') is not None)
    
    # Show sample extractions with reasoning
    print(f"\n  Sample extractions (first 3 with AI-related=True):")
    ai_extractions = [e for e in extractions if e.get('ai_related', False)][:3]
    for i, ext in enumerate(ai_extractions, 1):
        print(f"    {i}. AI-related: {ext.get('ai_related', False)}")
        print(f"       Supplier: {ext.get('supplier', 'None')}")
        print(f"       Customer: {ext.get('customer', 'None')}")
        print(f"       Product: {ext.get('product', 'None')}")
        print(f"       Relevance: {ext.get('relevance_score', 0.0):.3f}")
    
    # Results
    result = {
        'ticker': ticker,
        'status': 'SUCCESS',
        'total_articles': len(articles),
        'total_extractions': len(extractions),
        'ai_related_count': ai_related_count,
        'ai_related_pct': (ai_related_count / len(extractions) * 100) if extractions else 0,
        'supplier_mentions': supplier_mentions,
        'customer_mentions': customer_mentions,
        'product_mentions': sum(1 for e in extractions if e.get('product') and e.get('product') is not None),
        'avg_relevance_score': aggregated['avg_relevance_score'],
        'positive_sentiment_count': aggregated['positive_sentiment_count'],
        'supply_chain_score': score,
        'expected_score_range': expected_score_range,
        'expected_high': expected_high,
        'score_in_range': expected_score_range[0] <= score <= expected_score_range[1],
        'sample_headlines': sample_headlines,
        'sample_extractions': [
            {
                'ai_related': e.get('ai_related', False),
                'supplier': e.get('supplier'),
                'customer': e.get('customer'),
                'product': e.get('product'),
                'relevance_score': e.get('relevance_score', 0.0)
            }
            for e in ai_extractions
        ]
    }
    
    # Print summary
    print(f"\n  RESULTS:")
    print(f"    Supply Chain Score: {score:.4f}")
    print(f"    Expected Range: {expected_score_range[0]:.2f} - {expected_score_range[1]:.2f}")
    print(f"    AI-Related Articles: {ai_related_count}/{len(extractions)} ({result['ai_related_pct']:.1f}%)")
    print(f"    Supplier Mentions: {supplier_mentions}")
    print(f"    Customer Mentions: {customer_mentions}")
    print(f"    Avg Relevance: {aggregated['avg_relevance_score']:.3f}")
    
    if result['score_in_range']:
        print(f"    [OK] Score is in expected range")
    else:
        print(f"    [WARNING] Score is OUTSIDE expected range!")
    
    return result


def validate_scores(results: List[Dict]) -> Dict:
    """
    Run validation checks on results.
    
    Returns:
        Dict with validation flags and issues
    """
    validation = {
        'flags': [],
        'issues': [],
        'pass_count': 0,
        'fail_count': 0
    }
    
    # Industry-based checks
    industry_checks = {
        'AAL': {'industry': 'Airlines', 'max_score': 0.3, 'reason': 'Airlines should not have high AI exposure'},
        'AEM': {'industry': 'Mining', 'max_score': 0.3, 'reason': 'Mining should not have high AI exposure'},
        'NVDA': {'industry': 'AI Chips', 'min_score': 0.7, 'reason': 'NVIDIA should have high AI exposure'}
    }
    
    for result in results:
        ticker = result['ticker']
        score = result['supply_chain_score']
        
        if ticker in industry_checks:
            check = industry_checks[ticker]
            
            if 'max_score' in check:
                if score > check['max_score']:
                    flag = f"{ticker} ({check['industry']}) scores {score:.3f} > {check['max_score']}: {check['reason']}"
                    validation['flags'].append(flag)
                    validation['issues'].append(flag)
                    validation['fail_count'] += 1
                else:
                    validation['pass_count'] += 1
                    
            if 'min_score' in check:
                if score < check['min_score']:
                    flag = f"{ticker} ({check['industry']}) scores {score:.3f} < {check['min_score']}: {check['reason']}"
                    validation['flags'].append(flag)
                    validation['issues'].append(flag)
                    validation['fail_count'] += 1
                else:
                    validation['pass_count'] += 1
        
        # Check for keyword contamination (ticker symbol in keywords)
        ticker_lower = ticker.lower()
        keywords = ['ai', 'artificial intelligence', 'gpu', 'semiconductor', 'datacenter']
        contamination = [kw for kw in keywords if kw in ticker_lower or ticker_lower in kw]
        if contamination:
            flag = f"{ticker}: Potential keyword contamination - ticker '{ticker}' matches keywords: {contamination}"
            validation['flags'].append(flag)
            validation['issues'].append(flag)
            validation['fail_count'] += 1
        
        # Check if supplier/customer mentions are 0 (should be >0 with Gemini)
        if result.get('supplier_mentions', 0) == 0 and result.get('customer_mentions', 0) == 0:
            if result.get('total_extractions', 0) > 0:
                flag = f"{ticker}: No supplier/customer mentions extracted (expected >0 with Gemini)"
                validation['flags'].append(flag)
                # Don't count as fail - might be legitimate if no relationships in news
    
    return validation


def create_ground_truth_table(results: List[Dict]) -> List[Dict]:
    """
    Create ground truth comparison table.
    """
    ground_truth = {
        'NVDA': {'company': 'NVIDIA', 'industry': 'AI Chips', 'expected': '>0.8'},
        'AMD': {'company': 'AMD', 'industry': 'AI Chips', 'expected': '>0.7'},
        'AAL': {'company': 'American Airlines', 'industry': 'Airlines', 'expected': '<0.3'},
        'AEM': {'company': 'Agnico Eagle Mines', 'industry': 'Mining', 'expected': '<0.3'}
    }
    
    table = []
    for result in results:
        ticker = result['ticker']
        if ticker in ground_truth:
            gt = ground_truth[ticker]
            actual_score = result.get('supply_chain_score', 0.0)
            expected = gt['expected']
            
            # Parse expected (e.g., ">0.8" or "<0.3")
            if '>' in expected:
                threshold = float(expected.replace('>', ''))
                passed = actual_score > threshold
            elif '<' in expected:
                threshold = float(expected.replace('<', ''))
                passed = actual_score < threshold
            else:
                passed = False
            
            table.append({
                'company': gt['company'],
                'ticker': ticker,
                'industry': gt['industry'],
                'expected_score': expected,
                'actual_score': f"{actual_score:.4f}",
                'pass_fail': 'PASS' if passed else 'FAIL',
                'supplier_mentions': result.get('supplier_mentions', 0),
                'customer_mentions': result.get('customer_mentions', 0)
            })
    
    return table


def main():
    """Run tests on 3 stocks."""
    print("="*80)
    print("GEMINI SUPPLY CHAIN RANKING TEST - 3 STOCKS")
    print("="*80)
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Using: Gemini 2.5 Flash Lite")
    
    # Test cases
    test_cases = [
        {
            'ticker': 'AAL',
            'expected_range': (0.0, 0.3),
            'expected_high': False,
            'description': 'American Airlines - Should NOT score high'
        },
        {
            'ticker': 'NVDA',
            'expected_range': (0.7, 1.0),
            'expected_high': True,
            'description': 'NVIDIA - Should score high (AI chips)'
        },
        {
            'ticker': 'AEM',
            'expected_range': (0.0, 0.3),
            'expected_high': False,
            'description': 'Agnico Eagle Mines - Should NOT score high'
        }
    ]
    
    results = []
    
    for test_case in test_cases:
        print(f"\n{test_case['description']}")
        result = test_stock(
            test_case['ticker'],
            test_case['expected_range'],
            test_case['expected_high']
        )
        result['description'] = test_case['description']
        results.append(result)
    
    # Validation
    print(f"\n{'='*80}")
    print("VALIDATION CHECKS")
    print(f"{'='*80}")
    validation = validate_scores(results)
    
    if validation['flags']:
        print(f"\n  FLAGS RAISED ({len(validation['flags'])}):")
        for flag in validation['flags']:
            print(f"    [!] {flag}")
    else:
        print(f"\n  [OK] No validation flags raised")
    
    print(f"\n  Validation Summary:")
    print(f"    Pass: {validation['pass_count']}")
    print(f"    Fail: {validation['fail_count']}")
    
    # Ground truth table
    print(f"\n{'='*80}")
    print("GROUND TRUTH COMPARISON")
    print(f"{'='*80}")
    table = create_ground_truth_table(results)
    
    print(f"\n{'Company':<25} {'Ticker':<8} {'Industry':<15} {'Expected':<10} {'Actual':<10} {'Status':<8} {'Supp':<6} {'Cust':<6}")
    print("-" * 100)
    for row in table:
        print(f"{row['company']:<25} {row['ticker']:<8} {row['industry']:<15} {row['expected_score']:<10} "
              f"{row['actual_score']:<10} {row['pass_fail']:<8} {row['supplier_mentions']:<6} {row['customer_mentions']:<6}")
    
    # Save results
    output = {
        'test_date': datetime.now().isoformat(),
        'model': 'gemini-2.5-flash-lite',
        'test_cases': test_cases,
        'results': results,
        'validation': validation,
        'ground_truth_table': table
    }
    
    output_path = Path('outputs/gemini_ranking_test_3stocks.json')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*80}")
    print("RESULTS SAVED")
    print(f"{'='*80}")
    print(f"  Output: {output_path}")
    
    # Final recommendation
    print(f"\n{'='*80}")
    print("RECOMMENDATION")
    print(f"{'='*80}")
    
    if validation['fail_count'] == 0 and all(r.get('status') == 'SUCCESS' for r in results):
        print("  [GO] All tests passed - Safe to clear cache and re-run full backtest")
    else:
        print("  [NO-GO] Issues found - Review validation flags before proceeding")
        if validation['issues']:
            print("\n  Issues to address:")
            for issue in validation['issues']:
                print(f"    - {issue}")
    
    return output


if __name__ == '__main__':
    main()
