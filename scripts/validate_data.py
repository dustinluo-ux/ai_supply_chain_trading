"""
Data validation script - run this after any backtest
Checks for common anomalies and data quality issues
"""

import re
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Optional
import statistics


class BacktestLogValidator:
    """Validates backtest log files for anomalies"""
    
    def __init__(self, log_file: str):
        self.log_file = Path(log_file)
        self.content = self._load_log()
        self.issues = []
        self.warnings = []
        self.critical = []
        
    def _load_log(self) -> str:
        """Load log file content"""
        if not self.log_file.exists():
            raise FileNotFoundError(f"Log file not found: {self.log_file}")
        with open(self.log_file, 'r', encoding='utf-8') as f:
            return f.read()
    
    def validate_all(self) -> Dict:
        """Run all validation checks"""
        results = {
            'score_distribution': self.check_score_distribution(),
            'data_consistency': self.check_data_consistency(),
            'calculation_verification': self.check_calculations(),
            'pattern_detection': self.check_patterns(),
            'llm_quality': self.check_llm_responses(),
            'code_data_mismatch': self.check_mismatches(),
            'critical_issues': self.identify_critical_issues()
        }
        
        return {
            'status': 'PASS' if not self.critical else 'FAIL',
            'critical_count': len(self.critical),
            'warning_count': len(self.warnings),
            'issues_count': len(self.issues),
            'results': results,
            'critical': self.critical,
            'warnings': self.warnings,
            'issues': self.issues
        }
    
    def check_score_distribution(self) -> Dict:
        """Check score distributions for anomalies"""
        issues = []
        
        # Extract supply chain and sentiment scores
        supply_chain_scores = []
        sentiment_scores = []
        
        # Pattern: supply_chain_score': X, 'sentiment_score': Y
        pattern = r"'supply_chain_score':\s*([-\d.]+).*?'sentiment_score':\s*([-\d.]+)"
        matches = re.findall(pattern, self.content)
        
        if not matches:
            issues.append("No supply_chain/sentiment scores found in log")
            return {'status': 'UNKNOWN', 'issues': issues}
        
        for sc, sent in matches:
            try:
                supply_chain_scores.append(float(sc))
                sentiment_scores.append(float(sent))
            except ValueError:
                continue
        
        if not supply_chain_scores:
            issues.append("Could not parse any scores")
            return {'status': 'UNKNOWN', 'issues': issues}
        
        # Check if scores are identical
        identical_count = sum(1 for sc, sent in zip(supply_chain_scores, sentiment_scores) if abs(sc - sent) < 1e-6)
        if identical_count == len(supply_chain_scores) and len(supply_chain_scores) > 0:
            self.critical.append({
                'type': 'IDENTICAL_SCORES',
                'message': f'CRITICAL: Supply chain and sentiment scores are identical for all {len(supply_chain_scores)} weeks. This indicates a bug where sentiment_score is assigned from supply_chain_health_score instead of a separate sentiment field.',
                'location': 'gemini_news_analyzer.py:510',
                'fix': 'Update LLM prompt to request sentiment_score and parse it separately in line 510'
            })
            issues.append(f"All {identical_count} score pairs are identical (CRITICAL BUG)")
        
        # Calculate statistics
        sc_stats = self._calculate_stats(supply_chain_scores, 'supply_chain')
        sent_stats = self._calculate_stats(sentiment_scores, 'sentiment')
        
        # Check variance
        if sc_stats['std'] < 0.01:
            issues.append(f"Supply chain scores have very low variance (std={sc_stats['std']:.6f})")
        
        if sent_stats['std'] < 0.01:
            issues.append(f"Sentiment scores have very low variance (std={sent_stats['std']:.6f})")
        
        return {
            'status': 'FAIL' if identical_count == len(supply_chain_scores) else 'PASS',
            'supply_chain': sc_stats,
            'sentiment': sent_stats,
            'identical_count': identical_count,
            'total_count': len(supply_chain_scores),
            'issues': issues
        }
    
    def _calculate_stats(self, values: List[float], name: str) -> Dict:
        """Calculate statistics for a list of values"""
        if not values:
            return {'min': None, 'max': None, 'mean': None, 'median': None, 'std': None, 'unique': 0}
        
        return {
            'min': min(values),
            'max': max(values),
            'mean': statistics.mean(values),
            'median': statistics.median(values),
            'std': statistics.stdev(values) if len(values) > 1 else 0.0,
            'unique': len(set(values))
        }
    
    def check_data_consistency(self) -> Dict:
        """Check data consistency (weeks, articles, dates)"""
        issues = []
        
        # Count weeks processed
        week_pattern = r'\[ITERATION \d+\].*?(\d{4}-\d{2}-\d{2})'
        weeks = re.findall(week_pattern, self.content)
        unique_weeks = set(weeks)
        
        if len(unique_weeks) == 0:
            issues.append("No weeks found in log")
        elif len(unique_weeks) < 4:
            issues.append(f"Only {len(unique_weeks)} unique weeks found (expected 4+)")
        
        # Count articles
        article_pattern = r'Articles in range.*?:\s*(\d+)'
        article_counts = [int(x) for x in re.findall(article_pattern, self.content)]
        
        if article_counts:
            if min(article_counts) == 0:
                issues.append(f"Found week with 0 articles")
            if max(article_counts) > 10000:
                issues.append(f"Found week with {max(article_counts)} articles (suspiciously high)")
        
        # Check for date gaps (basic check)
        if len(unique_weeks) > 1:
            sorted_weeks = sorted(unique_weeks)
            # Simple check: if weeks are not consecutive, flag
            # (This is a simplified check - full implementation would parse dates)
        
        return {
            'status': 'PASS' if not issues else 'WARN',
            'weeks_found': len(unique_weeks),
            'article_counts': article_counts,
            'issues': issues
        }
    
    def check_calculations(self) -> Dict:
        """Verify calculations are correct (sample checks)"""
        issues = []
        
        # Check if combined scores are logged
        combined_pattern = r'score=([\d.]+)'
        combined_scores = [float(x) for x in re.findall(combined_pattern, self.content) if '.' in x]
        
        if not combined_scores:
            issues.append("No combined scores found in log")
        
        # Check if scores are in valid range (0-1 for combined)
        out_of_range = [s for s in combined_scores if s < 0 or s > 1]
        if out_of_range:
            issues.append(f"Found {len(out_of_range)} combined scores outside 0-1 range")
        
        return {
            'status': 'PASS' if not issues else 'WARN',
            'combined_scores_found': len(combined_scores),
            'out_of_range': len(out_of_range),
            'issues': issues
        }
    
    def check_patterns(self) -> Dict:
        """Detect suspicious patterns"""
        issues = []
        critical = []
        
        # Pattern 1: Check if all relationships are the same
        relationship_pattern = r"'relationship':\s*'(\w+)'"
        relationships = re.findall(relationship_pattern, self.content)
        if relationships:
            unique_rels = set(relationships)
            if len(unique_rels) == 1:
                issues.append(f"All relationships are '{relationships[0]}' (may be suspicious)")
        
        # Pattern 2: Check if all backtest results are identical
        sharpe_pattern = r'Sharpe=?\s*([\d.]+)'
        sharpe_values = [float(x) for x in re.findall(sharpe_pattern, self.content)]
        if sharpe_values and len(set(sharpe_values)) == 1:
            critical.append({
                'type': 'IDENTICAL_RESULTS',
                'message': f'All backtests return identical Sharpe ratio: {sharpe_values[0]}',
                'location': 'test_signals.py - backtest execution'
            })
        
        # Pattern 3: Check rebalance dates
        rebalance_pattern = r'Rebalance dates:\s*(\d+)'
        rebalance_matches = re.findall(rebalance_pattern, self.content)
        if rebalance_matches:
            rebalance_count = int(rebalance_matches[0])
            if rebalance_count == 0:
                issues.append("Zero rebalance dates detected (transaction costs may not be applied)")
        
        return {
            'status': 'FAIL' if critical else ('WARN' if issues else 'PASS'),
            'relationships': list(set(relationships)) if relationships else [],
            'sharpe_values': list(set(sharpe_values)) if sharpe_values else [],
            'rebalance_count': int(rebalance_matches[0]) if rebalance_matches else None,
            'issues': issues,
            'critical': critical
        }
    
    def check_llm_responses(self) -> Dict:
        """Check LLM response quality"""
        issues = []
        
        # Count list vs dict responses
        list_response_pattern = r'LLM returned list with (\d+) items'
        list_responses = len(re.findall(list_response_pattern, self.content))
        
        dict_response_pattern = r'RETURNING.*?type.*?dict'
        dict_responses = len(re.findall(dict_response_pattern, self.content, re.IGNORECASE))
        
        # Check reasoning uniqueness
        reasoning_pattern = r"'reasoning':\s*'([^']+)'"
        reasonings = re.findall(reasoning_pattern, self.content)
        unique_reasonings = len(set(reasonings))
        
        if len(reasonings) > 0 and unique_reasonings / len(reasonings) < 0.5:
            issues.append(f"Only {unique_reasonings}/{len(reasonings)} unique reasonings (may be repetitive)")
        
        return {
            'status': 'PASS' if not issues else 'WARN',
            'list_responses': list_responses,
            'dict_responses': dict_responses,
            'total_reasonings': len(reasonings),
            'unique_reasonings': unique_reasonings,
            'issues': issues
        }
    
    def check_mismatches(self) -> Dict:
        """Check for code-data mismatches"""
        issues = []
        
        # Check if sentiment score is assigned from supply_chain_health_score
        # This is a code check - we can't do it from log, but we can check if scores are identical
        # (already done in score_distribution check)
        
        # Check score ranges
        score_pattern = r"'supply_chain_score':\s*([-\d.]+)"
        scores = [float(x) for x in re.findall(score_pattern, self.content)]
        
        if scores:
            out_of_range = [s for s in scores if s < -1.0 or s > 1.0]
            if out_of_range:
                issues.append(f"Found {len(out_of_range)} supply chain scores outside [-1, 1] range")
        
        return {
            'status': 'PASS' if not issues else 'WARN',
            'issues': issues
        }
    
    def identify_critical_issues(self) -> List[Dict]:
        """Identify and prioritize critical issues"""
        # Critical issues are already collected in self.critical during checks
        return self.critical


def main():
    """Main validation function"""
    import sys
    
    if len(sys.argv) < 2:
        # Find latest log file
        log_dir = Path("outputs")
        if not log_dir.exists():
            print("ERROR: outputs/ directory not found")
            return
        
        log_files = sorted(log_dir.glob("backtest_log_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not log_files:
            print("ERROR: No backtest log files found in outputs/")
            return
        
        log_file = log_files[0]
        print(f"Using latest log file: {log_file}")
    else:
        log_file = sys.argv[1]
    
    print(f"\n{'='*60}")
    print("BACKTEST DATA VALIDATION")
    print(f"{'='*60}\n")
    
    try:
        validator = BacktestLogValidator(log_file)
        results = validator.validate_all()
        
        # Print summary
        print(f"Status: {results['status']}")
        print(f"Critical Issues: {results['critical_count']}")
        print(f"Warnings: {results['warning_count']}")
        print(f"Issues: {results['issues_count']}\n")
        
        # Print critical issues
        if results['critical']:
            print("CRITICAL ISSUES:")
            for issue in results['critical']:
                print(f"  [{issue['type']}] {issue['message']}")
                print(f"    Location: {issue.get('location', 'Unknown')}\n")
        
        # Print warnings
        if results['warnings']:
            print("WARNINGS:")
            for warning in results['warnings']:
                print(f"  - {warning}\n")
        
        # Print detailed results
        print("\nDETAILED RESULTS:")
        print(f"  Score Distribution: {results['results']['score_distribution'].get('status', 'UNKNOWN')}")
        print(f"  Data Consistency: {results['results']['data_consistency'].get('status', 'UNKNOWN')}")
        print(f"  Pattern Detection: {results['results']['pattern_detection'].get('status', 'UNKNOWN')}")
        print(f"  LLM Quality: {results['results']['llm_quality'].get('status', 'UNKNOWN')}")
        
        # Save detailed report
        report_file = Path("outputs") / f"validation_report_{Path(log_file).stem}.json"
        with open(report_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nDetailed report saved to: {report_file}")
        
        return 0 if results['status'] == 'PASS' else 1
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
