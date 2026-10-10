class CampaignRequiredError(ValueError):
    """Generation requires a loaded campaign; legacy history stays readable."""


class ConcurrentModificationError(RuntimeError):
    """Raised when state version mismatch is detected during optimistic locking."""
    pass
