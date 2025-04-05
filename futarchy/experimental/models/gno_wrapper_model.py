# futarchy/experimental/models/gno_wrapper_model.py
import traceback
from typing import Optional, Dict

try:
    # Relative imports assuming the structure defined in the plan
    from ..core.futarchy_bot import FutarchyBot
    from ..exchanges.aave_balancer import AaveBalancerHandler
except ImportError:
    print("Error importing modules in GnoWrapperModel. Check paths.")
    raise

class GnoWrapperModel:
    """Handles GNO wrapping/unwrapping via AaveBalancerHandler."""

    def __init__(self, bot_context: FutarchyBot):
        self.bot = bot_context
        # Assuming FutarchyBot initializes AaveBalancerHandler as self.aave_balancer
        self.handler = bot_context.aave_balancer

    def wrap_gno(self, amount: float) -> Optional[Dict]:
        """Wraps GNO into waGNO."""
        try:
            tx_hash = self.handler.wrap_gno_to_wagno(amount)
            if tx_hash:
                # TODO: Ideally, parse the receipt to get the exact amount wrapped if the ratio isn't 1:1
                # For now, assume 1:1 for simplicity in the controller
                return {'success': True, 'amount_wrapped': amount, 'tx_hash': tx_hash}
            else:
                return {'success': False, 'message': "Wrap transaction failed or returned no hash."}
        except Exception as e:
            print(f"❌ Error during GNO wrap in model: {e}")
            traceback.print_exc()
            return {'success': False, 'message': str(e)}

    def unwrap_wagno(self, amount: float) -> Optional[Dict]:
        """Unwraps waGNO into GNO."""
        try:
            tx_hash = self.handler.unwrap_wagno(amount) # Uses alias in handler
            if tx_hash:
                # TODO: Parse receipt for exact amount unwrapped
                return {'success': True, 'amount_unwrapped': amount, 'tx_hash': tx_hash}
            else:
                return {'success': False, 'message': "Unwrap transaction failed or returned no hash."}
        except Exception as e:
            print(f"❌ Error during waGNO unwrap in model: {e}")
            traceback.print_exc()
            return {'success': False, 'message': str(e)} 