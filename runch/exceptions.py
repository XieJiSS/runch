class RunchConfigUnchanged(Exception):
    """
    Raised by the user-provided custom loader when there's no need to update the config.
    """

    def __init__(self):
        super().__init__()


class RunchLookupError(Exception):
    """
    Raised when calling read_cached() on async configs, but the value is not ready yet.
    """
