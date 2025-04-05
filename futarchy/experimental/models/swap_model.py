# futarchy/experimental/models/swap_model.py
from typing import Optional, Dict
import traceback

try:
    # Relative imports assuming the structure defined in the plan
    from ..core.futarchy_bot import FutarchyBot
    from ..exchanges.balancer.swap import BalancerSwapHandler
    from ..exchanges.passthrough_router import PassthroughRouter
    # Import other needed constants or handlers
    from ..config.constants import TOKEN_CONFIG, CONTRACT_ADDRESSES
except ImportError:
    print("Error importing modules in SwapModel. Check paths.")
    raise

class SwapModel:
    """Handles interactions with swap functionalities (Balancer, Passthrough)."""

    def __init__(self, bot_context: FutarchyBot):
        self.bot = bot_context
        self.w3 = bot_context.w3
        self.verbose = bot_context.verbose
        # Instantiate necessary exchange handlers
        self.balancer_handler = BalancerSwapHandler(bot_context)
        # self.passthrough_router = PassthroughRouter(...) # Instantiate if needed

    def swap_on_balancer(self, token_in_symbol: str, token_out_symbol: str, amount: float) -> Optional[Dict]:
        """
        Executes a swap on the Balancer sDAI/waGNO pool.

        Args:
            token_in_symbol: 'sDAI' or 'waGNO'.
            token_out_symbol: 'sDAI' or 'waGNO'.
            amount: Amount of token_in to swap (in ether units).

        Returns:
            Dictionary with swap result {'success': bool, 'amount_out': float, 'tx_hash': str} or None on failure.
        """
        try:
            if token_in_symbol == 'sDAI' and token_out_symbol == 'waGNO':
                result = self.balancer_handler.swap_sdai_to_wagno(amount)
            elif token_in_symbol == 'waGNO' and token_out_symbol == 'sDAI':
                result = self.balancer_handler.swap_wagno_to_sdai(amount)
            else:
                print(f"❌ Unsupported Balancer swap: {token_in_symbol} -> {token_out_symbol}")
                return None

            # Assume the handler returns a dict like {'success': True, 'tx_hash': '0x...', 'balance_changes': {'token_in': -X, 'token_out': Y}}
            if result and result.get('success'):
                return {
                    'success': True,
                    'amount_out': abs(result.get('balance_changes', {}).get('token_out', 0.0)), # Get the positive change in output token
                    'tx_hash': result.get('tx_hash')
                }
            else:
                return {'success': False, 'message': f"Balancer swap failed.", 'tx_hash': result.get('tx_hash')}

        except Exception as e:
            print(f"❌ Error during Balancer swap in model: {e}")
            traceback.print_exc()
            return {'success': False, 'message': str(e)}

    # Add other swap methods (e.g., swap_passthrough) here later if needed
    # def buy_sdai_yes(self, amount: float) -> Optional[Dict]: ...
    # def sell_sdai_yes(self, amount: float) -> Optional[Dict]: ...
