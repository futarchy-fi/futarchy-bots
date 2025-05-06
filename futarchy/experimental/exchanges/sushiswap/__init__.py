# futarchy/experimental/exchanges/sushiswap/__init__.py
# This file makes the 'sushiswap' directory a Python package.

# Temporary stub to allow importing without full SushiSwap implementation
class SushiSwapExchange:
    """Minimal stub for SushiSwapExchange to satisfy imports when SushiSwap is not required."""

    def __init__(self, *args, **kwargs):
        # Accept arbitrary arguments but do nothing
        self._disabled = True

    def __getattr__(self, item):
        """Raise informative error for any attribute access."""
        raise NotImplementedError(
            "SushiSwapExchange is currently mocked/stubbed out. "
            "Enable full SushiSwap support before calling its methods."
        )