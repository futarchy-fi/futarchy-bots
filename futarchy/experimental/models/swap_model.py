# futarchy/experimental/models/swap_model.py
from typing import Optional, Dict
import traceback
from decimal import Decimal

try:
    # Relative imports assuming the structure defined in the plan
    from ..core.futarchy_bot import FutarchyBot
    from ..exchanges.balancer.swap import BalancerSwapHandler
    # from ..exchanges.passthrough_router import PassthroughRouter # PassthroughRouter.sol is different
    from ..exchanges.sushiswap.swap import SushiSwapV3Handler # <-- IMPORT NEW HANDLER
    # Import other needed constants or handlers
    from ..config.constants import TOKEN_CONFIG, CONTRACT_ADDRESSES
except ImportError:
    print("Error importing modules in SwapModel. Check paths.")
    raise

class SwapModel:
    """Handles interactions with swap functionalities (Balancer, SushiSwap V3)."""

    def __init__(self, bot_context: FutarchyBot):
        self.bot = bot_context
        self.w3 = bot_context.w3
        self.verbose = bot_context.verbose
        # Instantiate necessary exchange handlers
        self.balancer_handler = BalancerSwapHandler(bot_context)
        self.sushi_handler = SushiSwapV3Handler(bot_context) # <-- INSTANTIATE HANDLER
        # self.passthrough_router = PassthroughRouter(...) 

    def _get_token_address_from_symbol(self, symbol_key: str) -> Optional[str]:
        """Helper to get token address from config using symbol key."""
        # Map symbol keys to TOKEN_CONFIG keys
        config_key_map = {
            'sDAI': 'currency',
            'GNO': 'company',
            'waGNO': 'wagno',
            'sDAI-YES': 'currency_yes',
            'sDAI-NO': 'currency_no',
            'GNO-YES': 'company_yes',
            'GNO-NO': 'company_no',
        }
        config_key = config_key_map.get(symbol_key)
        if config_key and config_key in TOKEN_CONFIG:
            return TOKEN_CONFIG[config_key]['address']
        else:
            print(f"❌ Unknown token symbol key: {symbol_key}")
            return None

    def swap_on_balancer(self, token_in_symbol: str, token_out_symbol: str, amount: float, simulate: bool = False) -> Optional[Dict]:
        """
        Executes or simulates a swap on the Balancer sDAI/waGNO pool.

        Args:
            token_in_symbol: 'sDAI' or 'waGNO'.
            token_out_symbol: 'sDAI' or 'waGNO'.
            amount: Amount of token_in to swap (in ether units).
            simulate: If True, simulate the swap.

        Returns:
            Dictionary with swap result or simulation result.
        """
        try:
            # Determine which handler method to call
            if token_in_symbol == 'sDAI' and token_out_symbol == 'waGNO':
                result = self.balancer_handler.swap_sdai_to_wagno(amount, simulate=simulate)
            elif token_in_symbol == 'waGNO' and token_out_symbol == 'sDAI':
                result = self.balancer_handler.swap_wagno_to_sdai(amount, simulate=simulate)
            else:
                print(f"❌ Unsupported Balancer swap: {token_in_symbol} -> {token_out_symbol}")
                return {'success': False, 'error': 'Unsupported swap pair', 'type': 'simulation' if simulate else 'execution'}

            # Handler methods now return structured dicts for both modes
            return result

        except Exception as e:
            print(f"❌ Error during Balancer swap in model: {e}")
            traceback.print_exc()
            return {'success': False, 'message': str(e), 'type': 'simulation' if simulate else 'execution'}

    def swap_conditional(self, token_in_symbol: str, token_out_symbol: str, amount_in: float, simulate: bool = False) -> dict:
        """Handles swaps involving conditional tokens (e.g., sDAI-YES <-> GNO-YES) via SushiSwap."""
        try:
            token_in_addr = self._get_address_from_symbol(token_in_symbol)
            token_out_addr = self._get_address_from_symbol(token_out_symbol)
            if not token_in_addr or not token_out_addr:
                raise ValueError(f"Could not find addresses for {token_in_symbol} or {token_out_symbol}")

            if simulate:
                result = self.sushi_handler.simulate_swap_exact_in(
                    token_in_addr,
                    token_out_addr,
                    amount_in
                )
                if result and result.get('success'):
                    result['token_in_symbol'] = token_in_symbol
                    result['token_out_symbol'] = token_out_symbol
                return result
            else:
                return self.sushi_handler.swap_exact_in(
                    token_in_addr,
                    token_out_addr,
                    amount_in
                )

        except Exception as e:
            error_msg = f"Error during conditional swap in model ({token_in_symbol} -> {token_out_symbol}): {e}"
            print(f"❌ {error_msg}")
            traceback.print_exc()
            return {"success": False, "error": error_msg, "type": "simulation" if simulate else "execution"}

    def _get_address_from_symbol(self, token_symbol: str) -> str:
        """Helper to get token address from its symbol key (e.g., 'sDAI-YES')."""
        token_symbol_upper = token_symbol.upper()
        
        # Check base tokens by name
        if token_symbol_upper == TOKEN_CONFIG.get('currency', {}).get('name', '').upper():
            return TOKEN_CONFIG.get('currency', {}).get('address')
        if token_symbol_upper == TOKEN_CONFIG.get('company', {}).get('name', '').upper():
            return TOKEN_CONFIG.get('company', {}).get('address')
        if token_symbol_upper == TOKEN_CONFIG.get('wagno', {}).get('name', '').upper():
             return TOKEN_CONFIG.get('wagno', {}).get('address')

        # Check conditional tokens using their specific keys in TOKEN_CONFIG
        # (assuming keys like 'currency_yes', 'company_no', etc. exist and map to configs with 'address')
        # We also need to handle if the input symbol key matches the config key directly
        token_symbol_lower = token_symbol.lower() # Use consistent case for keys
        if token_symbol_lower in TOKEN_CONFIG:
             entry = TOKEN_CONFIG[token_symbol_lower]
             if isinstance(entry, dict) and 'address' in entry:
                 return entry['address']
        
        # Fallback/Alternative mapping if keys don't match symbol directly (like sDAI-YES != currency_yes)
        mapping = {
            'sdai-yes': TOKEN_CONFIG.get('currency_yes', {}).get('address'),
            'sdai-no': TOKEN_CONFIG.get('currency_no', {}).get('address'),
            'gno-yes': TOKEN_CONFIG.get('company_yes', {}).get('address'),
            'gno-no': TOKEN_CONFIG.get('company_no', {}).get('address')
        }
        
        addr = mapping.get(token_symbol_lower)
        if addr:
            return addr
        
        # Final check: Look for yes_address/no_address in base configs
        # This might be redundant if the mapping above is comprehensive
        if token_symbol == 'sDAI-YES': return TOKEN_CONFIG.get('currency', {}).get('yes_address')
        if token_symbol == 'sDAI-NO': return TOKEN_CONFIG.get('currency', {}).get('no_address')
        if token_symbol == 'GNO-YES': return TOKEN_CONFIG.get('company', {}).get('yes_address')
        if token_symbol == 'GNO-NO': return TOKEN_CONFIG.get('company', {}).get('no_address')

        self.bot.view.display_warning(f"Could not resolve address for token symbol: {token_symbol}") # Use bot.view if available
        return None # Not found

    # Add other swap methods (e.g., swap_passthrough) here later if needed
    # def buy_sdai_yes(self, amount: float) -> Optional[Dict]: ...
    # def sell_sdai_yes(self, amount: float) -> Optional[Dict]: ...
