"""
Audit Logger - Run tracking and metrics logging
Ported from wealth_signal_mvp_v1/core/logging/audit_logger.py
"""
import os
import json
from datetime import datetime
from src.utils.logger import setup_logger

logger = setup_logger()


def log_audit_record(
    run_id: str,
    model_metrics: dict,
    config: dict,
    output_paths: dict,
    trade_summary: dict,
    audit_dir: str = "outputs/audit"
) -> str:
    """Logs an audit record for a single run. Returns path to saved audit log JSON."""
    os.makedirs(audit_dir, exist_ok=True)
    record = {
        "timestamp": datetime.now().isoformat(),
        "run_id": run_id,
        "metrics": model_metrics,
        "config": config,
        "outputs": output_paths,
        "trade_summary": trade_summary
    }
    path = os.path.join(audit_dir, f"audit_{run_id}.json")
    try:
        with open(path, "w") as f:
            json.dump(record, f, indent=4)
        logger.info(f"Audit record saved: {path}")
        return path
    except Exception as e:
        logger.error(f"Error saving audit record: {e}")
        raise
