"""
Test Gemini's knowledge of supplier-customer-competitor relationships.

This determines if we can trust LLM to identify supply chain relationships
or if we need to build a manual database.
"""

import google.generativeai as genai
import json
import os
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Ground truth - manually verified relationships for major tech stocks
# Sources: Company 10-Ks, Bloomberg, Reuters, Wikipedia
GROUND_TRUTH = {
    'AAPL': {
        'suppliers': ['TSM', 'HON', 'QCOM', 'MU', 'TXN'],  # TSMC (TSM), Foxconn (HON), Qualcomm, Micron, Texas Instruments
        'customers': [],  # B2C company
        'competitors': ['GOOGL', 'MSFT', 'SAMSUNG']
    },
    'NVDA': {
        'suppliers': ['TSM', 'ASML', 'SNPS', 'CDNS', 'SMCI'],  # TSMC, ASML, Synopsys, Cadence, Super Micro
        'customers': ['MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA'],  # Cloud providers, AI companies
        'competitors': ['AMD', 'INTC']
    },
    'AMD': {
        'suppliers': ['TSM', 'GFS'],  # TSMC, GlobalFoundries
        'customers': ['MSFT', 'SONY'],  # Xbox, PlayStation chips
        'competitors': ['NVDA', 'INTC']
    },
    'TSLA': {
        'suppliers': ['PANASONIC', 'LG', 'CATL', 'SAMSUNG'],  # Battery suppliers
        'customers': [],  # B2C
        'competitors': ['F', 'GM', 'RIVN']
    },
    'MSFT': {
        'suppliers': ['NVDA', 'AMD', 'INTC'],  # Buys GPUs/CPUs for Azure datacenter
        'customers': [],  # B2B/B2C mix
        'competitors': ['GOOGL', 'AMZN', 'AAPL']
    }
}

def test_llm_knowledge():
    """
    Test Gemini's knowledge against ground truth.
    Returns accuracy scores and recommendations.
    """
    
    # Configure Gemini
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash-lite')
    
    results = {}
    
    print("="*60)
    print("TESTING GEMINI SUPPLY CHAIN KNOWLEDGE")
    print("="*60)
    
    for company, truth in GROUND_TRUTH.items():
        print(f"\n[Testing {company}]")
        
        # Construct prompt
        prompt = f"""Identify the supply chain relationships for {company}.

Provide:
1. Top 5 SUPPLIERS (companies that sell TO {company})
2. Top 3 CUSTOMERS (companies that buy FROM {company}, if B2B)
3. Top 3 COMPETITORS

Return ONLY as JSON (no markdown, no explanation):
{{
  "suppliers": ["TICKER1", "TICKER2", ...],
  "customers": ["TICKER1", "TICKER2", ...],
  "competitors": ["TICKER1", "TICKER2", ...]
}}

Use stock tickers when possible. If not publicly traded or don't know ticker, use company name.
Be specific - only include relationships you're confident about.
If {company} is B2C (sells to consumers), customers array should be empty.
"""
        
        try:
            # Call LLM
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=500,
                    response_mime_type="application/json"
                )
            )
            response_text = response.text.strip()
            
            # Parse JSON (handle markdown code blocks if present)
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()
            
            llm_answer = json.loads(response_text)
            
            # Calculate accuracy for each relationship type
            def calc_accuracy(llm_list, truth_list):
                if not truth_list:
                    return None  # No ground truth to compare
                
                llm_set = set([s.upper() for s in llm_list])
                truth_set = set([s.upper() for s in truth_list])
                
                overlap = len(llm_set & truth_set)
                accuracy = overlap / len(truth_set)
                
                return {
                    'accuracy': accuracy,
                    'overlap': overlap,
                    'total': len(truth_set),
                    'llm_found': list(llm_set),
                    'truth': list(truth_set),
                    'correct': list(llm_set & truth_set),
                    'missed': list(truth_set - llm_set),
                    'wrong': list(llm_set - truth_set)
                }
            
            supplier_result = calc_accuracy(
                llm_answer.get('suppliers', []), 
                truth['suppliers']
            )
            customer_result = calc_accuracy(
                llm_answer.get('customers', []),
                truth['customers']
            ) if truth['customers'] else None
            competitor_result = calc_accuracy(
                llm_answer.get('competitors', []),
                truth['competitors']
            )
            
            results[company] = {
                'suppliers': supplier_result,
                'customers': customer_result,
                'competitors': competitor_result,
                'llm_raw': llm_answer
            }
            
            # Print results
            if supplier_result:
                print(f"  Suppliers: {supplier_result['accuracy']:.1%} ({supplier_result['overlap']}/{supplier_result['total']})")
                print(f"    [OK] Correct: {supplier_result['correct']}")
                if supplier_result['wrong']:
                    print(f"    [X] Incorrect: {supplier_result['wrong']}")
                if supplier_result['missed']:
                    print(f"    [!] Missed: {supplier_result['missed']}")
            
            if customer_result:
                print(f"  Customers: {customer_result['accuracy']:.1%} ({customer_result['overlap']}/{customer_result['total']})")
                print(f"    [OK] Correct: {customer_result['correct']}")
                if customer_result['wrong']:
                    print(f"    [X] Incorrect: {customer_result['wrong']}")
                if customer_result['missed']:
                    print(f"    [!] Missed: {customer_result['missed']}")
            
            if competitor_result:
                print(f"  Competitors: {competitor_result['accuracy']:.1%} ({competitor_result['overlap']}/{competitor_result['total']})")
                print(f"    [OK] Correct: {competitor_result['correct']}")
                if competitor_result['wrong']:
                    print(f"    [X] Incorrect: {competitor_result['wrong']}")
                if competitor_result['missed']:
                    print(f"    [!] Missed: {competitor_result['missed']}")
            
        except Exception as e:
            print(f"  [ERROR] {e}")
            import traceback
            traceback.print_exc()
            results[company] = {'error': str(e)}
    
    # Calculate overall statistics
    print("\n" + "="*60)
    print("OVERALL RESULTS")
    print("="*60)
    
    supplier_accuracies = [
        r['suppliers']['accuracy'] 
        for r in results.values() 
        if 'suppliers' in r and r['suppliers'] and 'error' not in r
    ]
    competitor_accuracies = [
        r['competitors']['accuracy']
        for r in results.values()
        if 'competitors' in r and r['competitors'] and 'error' not in r
    ]
    
    avg_supplier = sum(supplier_accuracies) / len(supplier_accuracies) if supplier_accuracies else 0
    avg_competitor = sum(competitor_accuracies) / len(competitor_accuracies) if competitor_accuracies else 0
    
    print(f"\nAverage Supplier Accuracy: {avg_supplier:.1%}")
    print(f"Average Competitor Accuracy: {avg_competitor:.1%}")
    
    # Recommendation
    print("\n" + "="*60)
    print("RECOMMENDATION")
    print("="*60)
    
    if avg_supplier >= 0.6:
        recommendation = "[OK] GOOD - LLM knowledge is sufficient"
        approach = "Can rely on LLM to identify relationships from news articles"
    elif avg_supplier >= 0.3:
        recommendation = "[!] PARTIAL - LLM knowledge has gaps"
        approach = "Should create manual database for top 50-100 stocks, use LLM as supplement"
    else:
        recommendation = "[X] POOR - LLM knowledge is unreliable"
        approach = "Must build comprehensive manual relationship database, don't trust LLM"
    
    print(f"\n{recommendation}")
    print(f"Approach: {approach}")
    
    # Save detailed results
    output_path = Path('docs/LLM_KNOWLEDGE_TEST_RESULTS.md')
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, 'w') as f:
        f.write("# LLM Supply Chain Knowledge Test Results\n\n")
        f.write(f"**Test Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"**Model:** Gemini 2.5 Flash Lite\n\n")
        f.write(f"## Summary\n\n")
        f.write(f"- Average Supplier Accuracy: **{avg_supplier:.1%}**\n")
        f.write(f"- Average Competitor Accuracy: **{avg_competitor:.1%}**\n\n")
        f.write(f"## Recommendation\n\n")
        f.write(f"{recommendation}\n\n")
        f.write(f"**Approach:** {approach}\n\n")
        f.write(f"## Detailed Results\n\n")
        f.write("```json\n")
        f.write(json.dumps(results, indent=2))
        f.write("\n```\n\n")
        
        # Add analysis section
        f.write("## Analysis\n\n")
        f.write("### Supplier Accuracy Breakdown\n\n")
        for company, result in results.items():
            if 'suppliers' in result and result['suppliers'] and 'error' not in result:
                f.write(f"**{company}:** {result['suppliers']['accuracy']:.1%}\n")
                f.write(f"- Correct: {result['suppliers']['correct']}\n")
                if result['suppliers']['missed']:
                    f.write(f"- Missed: {result['suppliers']['missed']}\n")
                if result['suppliers']['wrong']:
                    f.write(f"- Wrong: {result['suppliers']['wrong']}\n")
                f.write("\n")
        
        f.write("### Next Steps\n\n")
        if avg_supplier >= 0.6:
            f.write("1. [OK] LLM can be trusted for relationship identification\n")
            f.write("2. Implement network propagation using LLM-extracted relationships\n")
            f.write("3. Add validation layer to catch obvious errors\n")
        elif avg_supplier >= 0.3:
            f.write("1. [!] Build manual database for top 50-100 stocks\n")
            f.write("2. Use LLM as supplement for less common relationships\n")
            f.write("3. Implement confidence scoring (high confidence = manual DB, low = LLM)\n")
        else:
            f.write("1. [X] Build comprehensive manual relationship database\n")
            f.write("2. Use LLM only for validation, not primary source\n")
            f.write("3. Consider using structured data sources (Bloomberg, FactSet APIs)\n")
    
    print(f"\n[OK] Detailed results saved to: {output_path}")
    
    return {
        'avg_supplier_accuracy': avg_supplier,
        'avg_competitor_accuracy': avg_competitor,
        'recommendation': recommendation,
        'approach': approach,
        'details': results
    }

if __name__ == '__main__':
    results = test_llm_knowledge()
