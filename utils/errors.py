"""Custom exceptions for Email Classification Agent."""


class EmailClassifierError(Exception):
    """Base exception for email classifier errors."""
    pass


class ConfigurationError(EmailClassifierError):
    """Configuration-related errors."""
    pass


class MCPConnectionError(EmailClassifierError):
    """MCP server connection errors."""
    pass


class ClassificationError(EmailClassifierError):
    """Email classification errors."""
    pass


class EmailFetchError(EmailClassifierError):
    """Email fetching errors."""
    pass


class LabelApplicationError(EmailClassifierError):
    """Label/category application errors."""
    pass
