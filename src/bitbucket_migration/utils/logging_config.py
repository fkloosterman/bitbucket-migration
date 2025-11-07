"""
Structured logging configuration for the Bitbucket to GitHub migration tool.

This module provides a centralized logging system that replaces the simple
print-based logging in the original script with structured, configurable logging.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional


class MigrationLogger:
    """
    Centralized logger for the migration tool.

    Provides structured logging with different levels, file rotation, and
    console output. Replaces the simple self.log() method in the original script.
    """

    def __init__(self, log_level: str = "INFO", log_file: Optional[str] = None, dry_run: bool = False, overwrite: bool = False, logger_name: Optional[str] = None):
        """
        Initialize the logger.

        Args:
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_file: Optional file path for logging to file
            dry_run: Whether this is a dry run (affects log formatting)
            overwrite: Whether to overwrite existing log file instead of appending
            logger_name: Unique name for this logger. If None, uses 'bitbucket_migration'
        """
        self.dry_run = dry_run
        self.log_level = log_level  # Store log_level as instance attribute
        self.overwrite = overwrite
        self.logger_name = logger_name or 'bitbucket_migration'
        self.logger = logging.getLogger(self.logger_name)
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

        # Clear existing handlers to avoid duplicates
        self.logger.handlers.clear()

        # Create formatter
        formatter = self._create_formatter()

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File handler (if specified)
        if log_file:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            if overwrite:
                # Use regular FileHandler with 'w' mode to overwrite
                file_handler = logging.FileHandler(log_path, mode='w')
            else:
                # Use RotatingFileHandler to prevent log files from growing too large
                file_handler = logging.handlers.RotatingFileHandler(
                    log_path, maxBytes=10*1024*1024, backupCount=5  # 10MB max, 5 backups
                )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def _create_formatter(self) -> logging.Formatter:
        """Create a formatter for log messages."""
        if self.dry_run:
            return logging.Formatter(
                fmt='%(asctime)s - [DRY RUN] - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        else:
            return logging.Formatter(
                fmt='%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

    def info(self, message: str) -> None:
        """Log an info message."""
        self.logger.info(message)

    def warning(self, message: str) -> None:
        """Log a warning message."""
        self.logger.warning(message)

    def error(self, message: str) -> None:
        """Log an error message."""
        self.logger.error(message)

    def debug(self, message: str) -> None:
        """Log a debug message."""
        self.logger.debug(message)

    def log_migration_event(self, event_type: str, details: dict) -> None:
        """
        Log a structured migration event.

        Args:
            event_type: Type of event (e.g., 'issue_migrated', 'pr_created')
            details: Dictionary with event details
        """
        message = f"MIGRATION EVENT: {event_type} - {details}"
        self.info(message)

    def log_api_call(self, api: str, endpoint: str, method: str = "GET", status_code: Optional[int] = None) -> None:
        """
        Log an API call.

        Args:
            api: API name (e.g., 'Bitbucket', 'GitHub')
            endpoint: API endpoint
            method: HTTP method
            status_code: Response status code (if available)
        """
        if status_code:
            message = f"API CALL: {api} {method} {endpoint} - Status: {status_code}"
        else:
            message = f"API CALL: {api} {method} {endpoint}"
        self.debug(message)

    def log_rate_limit(self, api: str, wait_time: float) -> None:
        """
        Log rate limiting information.

        Args:
            api: API name
            wait_time: Time to wait in seconds
        """
        self.debug(f"RATE LIMIT: Waiting {wait_time:.2f}s for {api} API")


def setup_logger(log_level: str = "INFO", log_file: Optional[str] = None, dry_run: bool = False, overwrite: bool = False, logger_name: Optional[str] = None) -> MigrationLogger:
    """
    Convenience function to set up and return a MigrationLogger instance.

    Args:
        log_level: Logging level
        log_file: Optional log file path
        dry_run: Whether this is a dry run
        overwrite: Whether to overwrite existing log file instead of appending
        logger_name: Unique name for this logger. If None, uses 'bitbucket_migration'

    Returns:
        Configured MigrationLogger instance
    """
    return MigrationLogger(log_level, log_file, dry_run, overwrite, logger_name)