"""
Centralized logging configuration for the application.
"""
import logging
import os
from typing import Optional
from contextvars import ContextVar
from .config import settings

# Context variable to store session ID for logging
session_id_context: ContextVar[Optional[str]] = ContextVar('session_id', default=None)


class SessionLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter that adds session ID to log messages."""
    
    def __init__(self, logger, session_id: str):
        super().__init__(logger, {'session_id': session_id})
    
    def process(self, msg, kwargs):
        session_id = self.extra.get('session_id', 'no-session') if self.extra else 'no-session'
        return f"[{session_id}] {msg}", kwargs


def get_session_logger(name: Optional[str] = None, session_id: Optional[str] = None):
    """Get a logger with session ID context."""
    base_logger = logging.getLogger(name or __name__)
    if session_id:
        return SessionLoggerAdapter(base_logger, session_id)
    return base_logger


def get_logger_with_session(request, name: Optional[str] = None):
    """Get a session-aware logger from a FastAPI request object."""
    session_id = getattr(request.state, 'session_id', None)
    return get_session_logger(name, session_id)


def setup_logging():
    """Configure logging for the entire application."""
    def get_log_level(level_str: str) -> int:
        """Convert string log level to logging constant."""
        level_mapping = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        return level_mapping.get(level_str.upper(), logging.INFO)

    # Get the desired logging level
    log_level = get_log_level(settings.log_level)
    
    # Get root logger and clear existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Create standard formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # Configure root logger
    root_logger.addHandler(console_handler)
    root_logger.setLevel(log_level)
    
    return logging.getLogger(__name__)


def get_logger(name: Optional[str] = None):
    """Get a logger instance with the centralized configuration."""
    return logging.getLogger(name or __name__)


# Initialize logging when this module is imported
setup_logging()