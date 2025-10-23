"""
Custom exceptions for the Bitbucket to GitHub migration tool.

This module defines specific exception types for different categories of errors
that can occur during the migration process, providing better error handling
and more informative error messages.
"""

from typing import Optional


class MigrationError(Exception):
    """
    Base exception for migration errors.

    This is the parent class for all migration-specific exceptions,
    providing a common base for error handling and logging.
    """
    pass


class APIError(MigrationError):
    """
    Errors related to API calls.

    This exception is raised when there are issues with API communication,
    authentication, or when the API returns error responses.

    Attributes:
        status_code: HTTP status code if available
        response_text: API response text if available
    """

    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class AuthenticationError(APIError):
    """
    Authentication-related errors.

    Raised when API authentication fails, such as invalid tokens
    or insufficient permissions.
    """
    pass


class NetworkError(APIError):
    """
    Network-related errors.

    Raised when there are network connectivity issues, timeouts,
    or other network-related problems.
    """
    pass


class ConfigurationError(MigrationError):
    """
    Configuration-related errors.

    Raised when there are issues with the configuration file,
    missing required fields, or invalid configuration values.
    """
    pass


class ValidationError(MigrationError):
    """
    Data validation errors.

    Raised when data validation fails, such as invalid user mappings,
    malformed URLs, or other data integrity issues.
    """
    pass


class BranchNotFoundError(MigrationError):
    """
    Branch not found errors.

    Raised when required Git branches don't exist on GitHub,
    preventing PR creation.
    """
    def __init__(self, message: str, branch_name: str):
        super().__init__(message)
        self.branch_name = branch_name


class AttachmentError(MigrationError):
    """
    Attachment-related errors.

    Raised when there are issues downloading, uploading, or
    processing attachments during migration.
    """
    def __init__(self, message: str, filename: Optional[str] = None):
        super().__init__(message)
        self.filename = filename