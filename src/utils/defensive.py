"""
Defensive Coding Utilities
Prevents silent hangs, adds timeouts, progress logging, and error handling
"""
import time
import signal
import traceback
import functools
import threading
from typing import Callable, Any, Optional
import logging
import os

logger = logging.getLogger(__name__)

# Global debug flag
DEBUG_MODE = False


def set_debug_mode(enabled: bool):
    """Set global debug mode"""
    global DEBUG_MODE
    DEBUG_MODE = enabled
    if enabled:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("DEBUG MODE ENABLED - Verbose logging activated")


def safe_file_operation(operation_name: str = "file operation"):
    """
    Decorator to wrap file operations with try-except and detailed error messages
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                if DEBUG_MODE:
                    logger.debug(f"[FILE OP] Starting {operation_name}: {func.__name__}")
                    logger.debug(f"[FILE OP] Args: {args}, Kwargs: {kwargs}")
                
                result = func(*args, **kwargs)
                
                if DEBUG_MODE:
                    logger.debug(f"[FILE OP] Completed {operation_name}: {func.__name__}")
                
                return result
            except FileNotFoundError as e:
                error_msg = f"File not found in {operation_name} ({func.__name__}): {e}"
                logger.error(error_msg)
                logger.error(f"Full path attempted: {args[0] if args else 'N/A'}")
                raise FileNotFoundError(error_msg) from e
            except PermissionError as e:
                error_msg = f"Permission denied in {operation_name} ({func.__name__}): {e}"
                logger.error(error_msg)
                logger.error(f"File path: {args[0] if args else 'N/A'}")
                raise PermissionError(error_msg) from e
            except Exception as e:
                error_msg = f"Error in {operation_name} ({func.__name__}): {type(e).__name__}: {e}"
                logger.error(error_msg)
                logger.error(f"Traceback:\n{traceback.format_exc()}")
                raise
        return wrapper
    return decorator


class TimeoutError(Exception):
    """Custom timeout exception"""
    pass


def timeout_handler(signum, frame):
    """Signal handler for timeout"""
    raise TimeoutError("Operation timed out")


def with_timeout(timeout_seconds: int = 300, operation_name: str = "operation"):
    """
    Decorator to add timeout to long-running operations (default 5 minutes)
    
    Args:
        timeout_seconds: Maximum time in seconds (default 300 = 5 minutes)
        operation_name: Name of operation for logging
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            logger.info(f"[TIMEOUT] Starting {operation_name} (max {timeout_seconds}s)")
            
            # Use threading for timeout (works on Windows)
            result_container = {'result': None, 'exception': None, 'completed': False}
            
            def target():
                try:
                    result_container['result'] = func(*args, **kwargs)
                    result_container['completed'] = True
                except Exception as e:
                    result_container['exception'] = e
                    result_container['completed'] = True
            
            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout=timeout_seconds)
            
            elapsed = time.time() - start_time
            
            if not result_container['completed']:
                error_msg = f"{operation_name} exceeded timeout of {timeout_seconds}s (elapsed: {elapsed:.1f}s)"
                logger.error(error_msg)
                logger.error(f"Function: {func.__name__}")
                logger.error(f"Args: {args}, Kwargs: {kwargs}")
                logger.error(f"Traceback:\n{traceback.format_exc()}")
                raise TimeoutError(error_msg)
            
            if result_container['exception']:
                raise result_container['exception']
            
            logger.info(f"[TIMEOUT] Completed {operation_name} in {elapsed:.1f}s")
            return result_container['result']
        
        return wrapper
    return decorator


class ProgressLogger:
    """Logs progress every N seconds for long-running operations"""
    
    def __init__(self, interval_seconds: int = 10, operation_name: str = "operation"):
        self.interval_seconds = interval_seconds
        self.operation_name = operation_name
        self.start_time = None
        self.last_log_time = None
        self.current_item = None
        self.total_items = None
        self._stop = False
    
    def start(self, total_items: Optional[int] = None):
        """Start progress logging"""
        self.start_time = time.time()
        self.last_log_time = self.start_time
        self.total_items = total_items
        self._stop = False
        
        if total_items:
            logger.info(f"[PROGRESS] Starting {self.operation_name} ({total_items} items)")
        else:
            logger.info(f"[PROGRESS] Starting {self.operation_name}")
    
    def update(self, current_item: Any, current_index: Optional[int] = None, total: Optional[int] = None):
        """Update progress"""
        self.current_item = current_item
        current_time = time.time()
        
        # Log every interval_seconds
        if current_time - self.last_log_time >= self.interval_seconds:
            elapsed = current_time - self.start_time
            if current_index is not None and total is not None:
                logger.info(f"[PROGRESS] Still processing {self.operation_name}: {current_item} ({current_index}/{total}) - {elapsed:.1f}s elapsed")
            else:
                logger.info(f"[PROGRESS] Still processing {self.operation_name}: {current_item} - {elapsed:.1f}s elapsed")
            self.last_log_time = current_time
    
    def finish(self):
        """Finish progress logging"""
        if self.start_time:
            elapsed = time.time() - self.start_time
            logger.info(f"[PROGRESS] Completed {self.operation_name} in {elapsed:.1f}s")
    
    def stop(self):
        """Stop progress logging"""
        self._stop = True


def with_progress_logging(interval_seconds: int = 10, operation_name: str = "operation"):
    """
    Decorator to add progress logging to long-running operations
    
    Args:
        interval_seconds: Log progress every N seconds (default 10)
        operation_name: Name of operation for logging
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            progress = ProgressLogger(interval_seconds, operation_name)
            progress.start()
            
            try:
                result = func(*args, **kwargs)
                progress.finish()
                return result
            except Exception as e:
                progress.finish()
                raise
        return wrapper
    return decorator


# File operation wrappers with error handling
@safe_file_operation("read parquet")
def safe_read_parquet(file_path: str, **kwargs) -> Any:
    """Safely read parquet file"""
    import pandas as pd
    if DEBUG_MODE:
        logger.debug(f"Reading parquet: {file_path}")
    return pd.read_parquet(file_path, **kwargs)


@safe_file_operation("write parquet")
def safe_write_parquet(df: Any, file_path: str, **kwargs) -> None:
    """Safely write parquet file"""
    import pandas as pd
    if DEBUG_MODE:
        logger.debug(f"Writing parquet: {file_path} ({len(df)} rows)")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    df.to_parquet(file_path, **kwargs)


@safe_file_operation("read CSV")
def safe_read_csv(file_path: str, **kwargs) -> Any:
    """Safely read CSV file"""
    import pandas as pd
    if DEBUG_MODE:
        logger.debug(f"Reading CSV: {file_path}")
    return pd.read_csv(file_path, **kwargs)


@safe_file_operation("write CSV")
def safe_write_csv(df: Any, file_path: str, **kwargs) -> None:
    """Safely write CSV file"""
    import pandas as pd
    if DEBUG_MODE:
        logger.debug(f"Writing CSV: {file_path} ({len(df)} rows)")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    df.to_csv(file_path, **kwargs)


@safe_file_operation("read JSON")
def safe_read_json(file_path: str, **kwargs) -> Any:
    """Safely read JSON file"""
    import json
    if DEBUG_MODE:
        logger.debug(f"Reading JSON: {file_path}")
    with open(file_path, 'r') as f:
        return json.load(f, **kwargs)


@safe_file_operation("write JSON")
def safe_write_json(data: Any, file_path: str, **kwargs) -> None:
    """Safely write JSON file"""
    import json
    if DEBUG_MODE:
        logger.debug(f"Writing JSON: {file_path}")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(data, f, **kwargs)


@safe_file_operation("read YAML")
def safe_read_yaml(file_path: str) -> Any:
    """Safely read YAML file"""
    import yaml
    if DEBUG_MODE:
        logger.debug(f"Reading YAML: {file_path}")
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)


@safe_file_operation("write YAML")
def safe_write_yaml(data: Any, file_path: str) -> None:
    """Safely write YAML file"""
    import yaml
    if DEBUG_MODE:
        logger.debug(f"Writing YAML: {file_path}")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w') as f:
        yaml.safe_dump(data, f)
