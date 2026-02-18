"""
Supply Chain Sentiment Propagation Engine

Propagates news sentiment from a primary ticker to related companies
(suppliers, customers, competitors) based on supply chain relationships.

Uses a directed graph approach with decay factors based on relationship strength.
"""

import re
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from collections import deque
import logging

from src.data.supply_chain_manager import SupplyChainManager

logger = logging.getLogger(__name__)


@dataclass
class PropagatedSignal:
    """
    Represents a propagated sentiment signal for a related company.
    """
    ticker: str
    source_ticker: str  # Original ticker that generated the news
    sentiment_score: float  # Propagated sentiment (-1.0 to 1.0)
    supply_chain_score: float  # Propagated supply chain score (-1.0 to 1.0)
    relationship_type: str  # 'supplier', 'customer', 'competitor'
    relationship_tier: int  # 1 = direct, 2 = indirect (2 degrees)
    propagation_weight: float  # Weight applied (0.0 to 1.0)
    source_type: str  # 'direct' or 'propagated'
    confidence: float  # Confidence in the relationship (0.0 to 1.0)
    reasoning: str  # Explanation of propagation path


@dataclass
class NewsItem:
    """
    Input news item with sentiment scores.
    """
    ticker: str
    sentiment_score: float  # -1.0 to 1.0
    supply_chain_score: float  # -1.0 to 1.0
    confidence: float  # 0.0 to 1.0
    relationship: str  # 'Supplier', 'Buyer', 'Neutral'
    reasoning: str  # Original reasoning from LLM


class SentimentPropagator:
    """
    Propagates sentiment signals through supply chain relationships.
    
    Algorithm:
    1. Start with primary ticker (Tier 0)
    2. Find all direct relationships (Tier 1): suppliers, customers, competitors
    3. For each Tier 1, find their relationships (Tier 2)
    4. Apply decay factors based on relationship strength
    5. Return propagated signals for all related tickers
    """
    
    def __init__(
        self,
        db_path: str = 'data/supply_chain_relationships.json',
        tier1_weight: float = 0.5,
        tier2_weight: float = 0.2,
        max_degrees: int = 2
    ):
        """
        Initialize the sentiment propagator.
        
        Args:
            db_path: Path to supply chain relationships database
            tier1_weight: Default weight for direct relationships (Tier 1)
            tier2_weight: Default weight for indirect relationships (Tier 2)
            max_degrees: Maximum degrees of separation (default: 2)
        """
        self.manager = SupplyChainManager(db_path)
        self.tier1_weight = tier1_weight
        self.tier2_weight = tier2_weight
        self.max_degrees = max_degrees
        
        logger.info(f"SentimentPropagator initialized (max_degrees={max_degrees})")
    
    def calculate_relationship_weight(
        self,
        relationship: Dict,
        relationship_type: str
    ) -> float:
        """
        Calculate propagation weight based on relationship strength.
        
        Args:
            relationship: Relationship dict from database
            relationship_type: 'supplier', 'customer', or 'competitor'
            
        Returns:
            Weight between 0.0 and 1.0
        """
        # If revenue concentration data available, use it
        if relationship_type == 'customer' and 'concentration_pct' in relationship:
            # Higher concentration = higher weight
            # 20% revenue = 0.8 weight, 10% = 0.5 weight, 5% = 0.3 weight
            pct = relationship['concentration_pct']
            if pct >= 20:
                return 0.8
            elif pct >= 10:
                return 0.5
            elif pct >= 5:
                return 0.3
            else:
                return 0.2
        
        # Use confidence level if available
        confidence = relationship.get('confidence', 'medium')
        if confidence == 'high':
            return 0.7
        elif confidence == 'medium':
            return 0.5
        elif confidence == 'low':
            return 0.3
        else:
            return 0.5  # Default
    
    def propagate(
        self,
        news_item: NewsItem,
        discovered_links: Optional[List[Dict]] = None,
        valid_tickers: Optional[Set[str]] = None,
    ) -> List[PropagatedSignal]:
        """
        Propagate sentiment from primary ticker to related companies.

        Args:
            news_item: NewsItem with ticker and sentiment scores
            discovered_links: Optional list from LLM (e.g. [{"direction": "upstream", "target_entity": "X"}, ...]).
                Used only for the primary ticker; treated as Tier 1 (suppliers/customers).
            valid_tickers: Optional set of ticker symbols (e.g. from prices_dict) for resolving
                entity names to tickers; used in _get_relationships when processing discovered_links.

        Returns:
            List of PropagatedSignal objects for related tickers
        """
        primary_ticker = news_item.ticker.upper()
        propagated_signals = []
        links_for_primary = discovered_links if discovered_links else None
        valid_set: Optional[Set[str]] = None
        if valid_tickers is not None:
            valid_set = {t.upper() for t in valid_tickers}

        # Track visited tickers to avoid cycles
        visited = {primary_ticker: 0}  # ticker -> tier

        # BFS queue: (ticker, tier, source_ticker, path_weight)
        queue = deque([(primary_ticker, 0, primary_ticker, 1.0)])

        logger.debug("Propagating sentiment from %s (sentiment=%.3f)", primary_ticker, news_item.sentiment_score)

        while queue:
            current_ticker, current_tier, source_ticker, cumulative_weight = queue.popleft()

            # Skip if we've exceeded max degrees
            if current_tier >= self.max_degrees:
                continue

            # Get relationships for current ticker (merge discovered_links for primary only)
            use_discovered = links_for_primary if (current_ticker == primary_ticker) else None
            relationships = self._get_relationships(
                current_ticker, discovered_links=use_discovered, valid_tickers=valid_set
            )
            
            if not relationships:
                continue
            
            # Process each relationship type
            for rel_type in ['suppliers', 'customers', 'competitors']:
                rel_list = relationships.get(rel_type, [])
                
                for rel in rel_list:
                    related_ticker = rel.get('ticker', '').upper()
                    
                    # Skip if ticker is invalid or same as primary
                    if not related_ticker or related_ticker == primary_ticker:
                        continue
                    
                    # Skip if already visited at same or lower tier
                    if related_ticker in visited and visited[related_ticker] <= current_tier + 1:
                        continue
                    
                    # Calculate relationship weight
                    if current_tier == 0:
                        # Direct relationship (Tier 1)
                        base_weight = self.calculate_relationship_weight(rel, rel_type[:-1])  # Remove 's' from 'suppliers'
                        if base_weight == 0.5:  # Use default if not calculated
                            base_weight = self.tier1_weight
                    else:
                        # Indirect relationship (Tier 2+)
                        base_weight = self.tier2_weight
                    
                    # Apply cumulative decay
                    final_weight = cumulative_weight * base_weight
                    
                    # Calculate propagated scores
                    propagated_sentiment = news_item.sentiment_score * final_weight
                    propagated_supply_chain = news_item.supply_chain_score * final_weight
                    
                    # Determine relationship type for output
                    if rel_type == 'suppliers':
                        rel_type_str = 'supplier'
                    elif rel_type == 'customers':
                        rel_type_str = 'customer'
                    else:
                        rel_type_str = 'competitor'
                    
                    # Create propagated signal
                    signal = PropagatedSignal(
                        ticker=related_ticker,
                        source_ticker=primary_ticker,
                        sentiment_score=propagated_sentiment,
                        supply_chain_score=propagated_supply_chain,
                        relationship_type=rel_type_str,
                        relationship_tier=current_tier + 1,
                        propagation_weight=final_weight,
                        source_type='propagated',
                        confidence=rel.get('confidence', 'medium') == 'high' and 0.7 or 0.5,
                        reasoning=f"Propagated from {source_ticker} via {rel_type_str} relationship (Tier {current_tier + 1})"
                    )
                    
                    propagated_signals.append(signal)
                    
                    # Mark as visited
                    visited[related_ticker] = current_tier + 1
                    
                    # Add to queue for further propagation (if within max_degrees)
                    if current_tier + 1 < self.max_degrees:
                        queue.append((
                            related_ticker,
                            current_tier + 1,
                            primary_ticker,  # Keep original source
                            final_weight  # Cumulative weight
                        ))
                    
                    logger.debug(
                        f"  Propagated to {related_ticker} (Tier {current_tier + 1}, "
                        f"weight={final_weight:.3f}, sentiment={propagated_sentiment:.3f})"
                    )
        
        logger.info(f"Generated {len(propagated_signals)} propagated signals from {primary_ticker}")
        return propagated_signals
    
    @staticmethod
    def _normalize_entity_name(entity: str) -> str:
        """Remove common suffixes and punctuation for fuzzy ticker matching."""
        s = (entity or "").strip().upper()
        for suffix in (" INC.", " INC", ", INC.", ", INC", " CORP.", " CORP", ", CORP.", ", CORP", " CO.", " CO", ", LLC", " LLC", "."):
            if s.endswith(suffix):
                s = s[: -len(suffix)].strip()
        s = re.sub(r"[,.\-]+$", "", s).strip()
        return s

    @staticmethod
    def _resolve_entity_to_ticker(
        entity: str,
        valid_tickers: Optional[Set[str]] = None,
    ) -> str:
        """
        Resolve an entity name to a ticker symbol. Uses config map then valid_tickers.
        Returns uppercase ticker; if no match, returns normalized entity (caller may filter by CSV).
        """
        try:
            from src.utils.config_manager import get_config
            cfg = get_config()
            entity_map = cfg.get_param("strategy_params.llm_analysis.entity_ticker_map", None) or {}
        except Exception:
            entity_map = {}
        normalized = SentimentPropagator._normalize_entity_name(entity)
        if not normalized:
            return ""
        # Config map: key can be normalized name or original-style
        resolved = entity_map.get(normalized) or entity_map.get(normalized.title()) or entity_map.get(entity.strip())
        if isinstance(resolved, str) and resolved.strip():
            return resolved.strip().upper()
        if valid_tickers and normalized.upper() in valid_tickers:
            return normalized.upper()
        # Leave as normalized so caller can filter by CSV; often same as ticker (e.g. TSM)
        return normalized.upper()

    def _get_relationships(
        self,
        ticker: str,
        discovered_links: Optional[List[Dict]] = None,
        valid_tickers: Optional[Set[str]] = None,
    ) -> Dict:
        """
        Get all relationships for a ticker. Optionally merge discovered_links (LLM)
        as Tier 1: upstream -> suppliers, downstream -> customers. Entity names are
        normalized and resolved to tickers when possible (config map + valid_tickers).
        """
        ticker = ticker.upper()

        suppliers: List[Dict] = []
        customers: List[Dict] = []
        competitors: List[Dict] = []

        if self.manager.is_covered(ticker):
            rel_data = self.manager.db["relationships"][ticker]
            suppliers = list(rel_data.get("suppliers", []))
            customers = list(rel_data.get("customers", []))
            competitors = list(rel_data.get("competitors", []))

        if discovered_links:
            logger.debug(
                "Propagator received %d discovered links for %s",
                len(discovered_links), ticker,
            )
            for link in discovered_links:
                if not isinstance(link, dict):
                    continue
                direction = (link.get("direction") or "").lower()
                entity = link.get("entity") or link.get("target_entity") or ""
                if not entity or not isinstance(entity, str):
                    continue

                resolved_ticker = self._resolve_entity_to_ticker(entity, valid_tickers)
                if not resolved_ticker:
                    continue
                logger.debug("Mapped '%s' to '%s'", entity.strip(), resolved_ticker)
                rec = {"ticker": resolved_ticker, "confidence": "medium"}
                if direction == "upstream":
                    suppliers.append(rec)
                elif direction == "downstream":
                    customers.append(rec)
            logger.info("Merged %d discovered links for %s", len(discovered_links), ticker)

        return {
            "suppliers": suppliers,
            "customers": customers,
            "competitors": competitors,
        }
    
    def propagate_from_news_result(
        self,
        ticker: str,
        news_result: Dict
    ) -> Tuple[Dict, List[PropagatedSignal]]:
        """
        Propagate sentiment from a news analysis result.
        
        Args:
            ticker: Primary ticker
            news_result: Result from GeminiNewsAnalyzer (dict with sentiment_score, etc.)
            
        Returns:
            Tuple of (direct_signal, propagated_signals)
            - direct_signal: Dict with source_type='direct'
            - propagated_signals: List of PropagatedSignal objects
        """
        # Create NewsItem from result
        news_item = NewsItem(
            ticker=ticker.upper(),
            sentiment_score=news_result.get('sentiment_score', 0.0),
            supply_chain_score=news_result.get('supply_chain_score', 0.0),
            confidence=news_result.get('confidence', 1.0),
            relationship=news_result.get('relationship', 'Neutral'),
            reasoning=news_result.get('reasoning', '')
        )
        
        # Create direct signal
        direct_signal = {
            'ticker': ticker.upper(),
            'source_ticker': ticker.upper(),
            'sentiment_score': news_item.sentiment_score,
            'supply_chain_score': news_item.supply_chain_score,
            'relationship_type': 'direct',
            'relationship_tier': 0,
            'propagation_weight': 1.0,
            'source_type': 'direct',
            'confidence': news_item.confidence,
            'reasoning': news_item.reasoning
        }
        
        # Propagate to related companies
        propagated_signals = self.propagate(news_item)
        
        return direct_signal, propagated_signals
    
    def to_dict(self, signal: PropagatedSignal) -> Dict:
        """Convert PropagatedSignal to dictionary."""
        return {
            'ticker': signal.ticker,
            'source_ticker': signal.source_ticker,
            'sentiment_score': signal.sentiment_score,
            'supply_chain_score': signal.supply_chain_score,
            'relationship_type': signal.relationship_type,
            'relationship_tier': signal.relationship_tier,
            'propagation_weight': signal.propagation_weight,
            'source_type': signal.source_type,
            'confidence': signal.confidence,
            'reasoning': signal.reasoning
        }
    
    def to_dataframe(self, signals: List[PropagatedSignal]):
        """Convert list of signals to pandas DataFrame."""
        import pandas as pd
        
        data = [self.to_dict(s) for s in signals]
        return pd.DataFrame(data)
