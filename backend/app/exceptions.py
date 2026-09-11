class ConcurrentModificationError(RuntimeError):
    """Raised when state version mismatch is detected during optimistic locking."""
    pass
