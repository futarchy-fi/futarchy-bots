# futarchy/experimental/managers/gno_wrapper.py
import traceback
from typing import Optional

# Assuming these paths are correct relative to this file's location
try:
    from ..core.futarchy_bot import FutarchyBot # Relative import
    from ..exchanges.aave_balancer import AaveBalancerHandler
except ImportError:
    print("Error importing modules in GnoWrapper. Check relative paths or project structure.")
    raise

class GnoWrapper:
    """Manages wrapping GNO to waGNO and unwrapping waGNO to GNO."""

    def __init__(self, bot: FutarchyBot):
        self.bot = bot
        self.w3 = bot.w3
        self.account = bot.account
        self.address = bot.address
        self.verbose = bot.verbose
        # Note: FutarchyBot already initializes AaveBalancerHandler as self.aave_balancer
        self.handler = bot.aave_balancer # Use the existing handler

    def wrap(self, amount: float) -> Optional[str]:
        """
        Wraps GNO into waGNO.

        Args:
            amount: Amount of GNO to wrap (in ether units).

        Returns:
            Transaction hash string if successful, None otherwise.
        """
        print(f"\n\U0001f504 Wrapping {amount} GNO into waGNO...")
        try:
            return self.handler.wrap_gno_to_wagno(amount)
        except Exception as e:
            print(f"\u274c Error during wrap operation: {e}")
            traceback.print_exc()
            return None

    def unwrap(self, amount: float) -> Optional[str]:
        """
        Unwraps waGNO into GNO.

        Args:
            amount: Amount of waGNO to unwrap (in ether units).

        Returns:
            Transaction hash string if successful, None otherwise.
        """
        print(f"\n\U0001f504 Unwrapping {amount} waGNO into GNO...")
        try:
            return self.handler.unwrap_wagno(amount) # Uses alias in handler
        except Exception as e:
            print(f"\u274c Error during unwrap operation: {e}")
            traceback.print_exc()
            return None 