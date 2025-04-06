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

    def wrap_gno(self, amount: float, simulate: bool = False) -> Optional[Dict]:
        """Wraps GNO into waGNO."""
        try:
            # Pass simulate flag to handler
            result = self.handler.wrap_gno_to_wagno(amount, simulate=simulate)
            
            if simulate:
                return result # Handler already returns dict in simulation mode
            else:
                # Existing execution logic (handler returns tx_hash)
                tx_hash = result
                if tx_hash:
                    return {'success': True, 'amount_wrapped': amount, 'tx_hash': tx_hash, 'type': 'execution'}
                else:
                    return {'success': False, 'message': "Wrap transaction failed or returned no hash.", 'type': 'execution'}
        except Exception as e:
            print(f"❌ Error during GNO wrap in model: {e}")
            traceback.print_exc()
            return {'success': False, 'message': str(e), 'type': 'simulation' if simulate else 'execution'}

    def unwrap_wagno(self, amount: float, simulate: bool = False) -> Optional[Dict]:
        """Unwraps waGNO into GNO."""
        try:
            # Pass simulate flag to handler
            result = self.handler.unwrap_wagno(amount, simulate=simulate) # Uses alias in handler
            
            if simulate:
                return result # Handler already returns dict in simulation mode
            else:
                # Existing execution logic (handler returns tx_hash)
                tx_hash = result
                if tx_hash:
                    return {'success': True, 'amount_unwrapped': amount, 'tx_hash': tx_hash, 'type': 'execution'}
                else:
                    return {'success': False, 'message': "Unwrap transaction failed or returned no hash.", 'type': 'execution'}
        except Exception as e:
            print(f"❌ Error during waGNO unwrap in model: {e}")
            traceback.print_exc()
            return {'success': False, 'message': str(e), 'type': 'simulation' if simulate else 'execution'} 