"""Custom project exceptions."""


class GarminCoachError(Exception):
    """Base project exception."""


class ConfigurationError(GarminCoachError):
    """Raised when local configuration is invalid or incomplete."""


class DependencyError(GarminCoachError):
    """Raised when runtime dependencies are missing."""


class SyncError(GarminCoachError):
    """Raised for sync-related failures."""


class ResourceUnavailableError(SyncError):
    """Raised when a Garmin resource is not available for the user."""
