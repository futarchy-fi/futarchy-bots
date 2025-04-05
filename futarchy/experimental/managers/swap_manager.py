# futarchy/experimental/managers/swap_manager.py
import os
import math
from typing import Dict, Optional, Tuple

from web3 import Web3
from web3.contract import Contract

# Assuming these paths are correct relative to this file's location
# If not, adjust sys.path or use absolute imports if the project structure allows
try:
    from ..core.futarchy_bot import FutarchyBot # Relative import
    from ..exchanges.balancer.swap import BalancerSwapHandler
    from ..exchanges.passthrough_router import PassthroughRouter
    from ..config.constants import (
        TOKEN_CONFIG, CONTRACT_ADDRESSES, POOL_CONFIG_YES, POOL_CONFIG_NO,
        BALANCER_CONFIG, UNISWAP_V3_POOL_ABI, UNISWAP_V3_PASSTHROUGH_ROUTER_ABI,
        MIN_SQRT_RATIO, MAX_SQRT_RATIO
    )
    from ..utils.web3_utils import get_raw_transaction # Assuming this util is still needed
except ImportError:
    print("Error importing modules in SwapManager. Check relative paths or project structure.")
    raise

class SwapManager:
    """Manages different types of token swaps."""

    def __init__(self, bot: FutarchyBot):
        self.bot = bot
        self.w3 = bot.w3
        self.account = bot.account
        self.verbose = bot.verbose

        # Initialize underlying handlers
        self.balancer_handler = BalancerSwapHandler(bot)
        self.passthrough_router = PassthroughRouter(
            bot.w3,
            os.environ.get("PRIVATE_KEY"),
            CONTRACT_ADDRESSES["uniswapV3PassthroughRouter"] # Use correct key from constants
        )
        self.sdai_yes_pool_address = self.w3.to_checksum_address(CONTRACT_ADDRESSES["sdaiYesPool"])


    def swap_balancer(self, token_in_symbol: str, token_out_symbol: str, amount: float) -> Optional[Dict]:
        """
        Executes a swap on the Balancer sDAI/waGNO pool.

        Args:
            token_in_symbol: 'sDAI' or 'waGNO'
            token_out_symbol: 'sDAI' or 'waGNO'
            amount: Amount of token_in to swap (in ether units).

        Returns:
            Swap result dictionary or None on failure.
        """
        try:
            if token_in_symbol == 'sDAI' and token_out_symbol == 'waGNO':
                print(f"\n\U0001f504 Swapping {amount} sDAI for waGNO on Balancer...")
                return self.balancer_handler.swap_sdai_to_wagno(amount)
            elif token_in_symbol == 'waGNO' and token_out_symbol == 'sDAI':
                print(f"\n\U0001f504 Swapping {amount} waGNO for sDAI on Balancer...")
                return self.balancer_handler.swap_wagno_to_sdai(amount)
            else:
                print(f"\u274c Unsupported Balancer swap: {token_in_symbol} -> {token_out_symbol}")
                return None
        except Exception as e:
            print(f"\u274c Error during Balancer swap: {e}")
            import traceback
            traceback.print_exc()
            return None


    def _get_pool_data(self, pool_address: str) -> Tuple[Optional[Contract], Optional[int], Optional[str], Optional[str]]:
        """Gets key data from a V3 pool."""
        try:
            pool_contract = self.w3.eth.contract(address=self.w3.to_checksum_address(pool_address), abi=UNISWAP_V3_POOL_ABI)
            slot0 = pool_contract.functions.slot0().call()
            current_sqrt_price = slot0[0]
            token0 = pool_contract.functions.token0().call()
            token1 = pool_contract.functions.token1().call()
            return pool_contract, current_sqrt_price, token0, token1
        except Exception as e:
            print(f"\u274c Error getting pool data for {pool_address}: {e}")
            return None, None, None, None


    def _calculate_sqrt_price_limit(self, current_sqrt_price: int, zero_for_one: bool, slippage_tolerance: float = 0.05) -> int:
        """Calculates the sqrtPriceLimitX96 based on direction and slippage."""
        if zero_for_one:
            # Price is decreasing, limit is lower bound
            limit = int(current_sqrt_price * (1 - slippage_tolerance))
            return max(limit, MIN_SQRT_RATIO)
        else:
            # Price is increasing, limit is upper bound
            limit = int(current_sqrt_price * (1 + slippage_tolerance))
            return min(limit, MAX_SQRT_RATIO)


    def swap_conditional(self, pool_address: str, token_in: str, token_out: str, amount: float, zero_for_one: bool, slippage_tolerance: float = 0.05) -> bool:
        """
        Executes a swap using the Passthrough Router for conditional tokens.

        Args:
            pool_address: Address of the Uniswap V3 pool.
            token_in: Address of the input token.
            token_out: Address of the output token.
            amount: Amount of token_in to swap (in ether units).
            zero_for_one: Swap direction (True if swapping token0 for token1).
            slippage_tolerance: Allowed slippage (e.g., 0.05 for 5%).

        Returns:
            True if the swap was successful, False otherwise.
        """
        print(f"\n\U0001f504 Swapping {amount} {token_in} for {token_out} via Passthrough Router...")
        print(f"   Pool: {pool_address}, ZeroForOne: {zero_for_one}")

        pool_contract, current_sqrt_price, _, _ = self._get_pool_data(pool_address)
        if not pool_contract or current_sqrt_price is None:
            return False

        sqrt_price_limit_x96 = self._calculate_sqrt_price_limit(current_sqrt_price, zero_for_one, slippage_tolerance)
        print(f"   Current sqrtPriceX96: {current_sqrt_price}")
        print(f"   Calculated sqrtPriceLimitX96: {sqrt_price_limit_x96} (Slippage: {slippage_tolerance*100}%)")

        try:
            success = self.passthrough_router.execute_swap(
                pool_address=self.w3.to_checksum_address(pool_address),
                token_in=self.w3.to_checksum_address(token_in),
                token_out=self.w3.to_checksum_address(token_out),
                amount=amount,
                zero_for_one=zero_for_one,
                sqrt_price_limit_x96=sqrt_price_limit_x96
            )
            return success
        except Exception as e:
            print(f"\u274c Error during conditional swap: {e}")
            import traceback
            traceback.print_exc()
            return False

    def buy_sdai_yes(self, amount_in_sdai: float, slippage_tolerance: float = 0.05) -> bool:
        """Buys sDAI-YES tokens using sDAI."""
        print(f"\n\U0001f504 Buying sDAI-YES with {amount_in_sdai:.6f} sDAI...")

        pool_contract, _, token0, token1 = self._get_pool_data(self.sdai_yes_pool_address)
        if not pool_contract: return False

        sdai_address = self.w3.to_checksum_address(TOKEN_CONFIG["currency"]["address"])
        sdai_yes_address = self.w3.to_checksum_address(TOKEN_CONFIG["currency"]["yes_address"])

        if token0.lower() == sdai_yes_address.lower() and token1.lower() == sdai_address.lower():
            zero_for_one = False # Swapping token1 (sDAI) for token0 (sDAI-YES)
            token_in = sdai_address
            token_out = sdai_yes_address
            print("   Pool order: token0=sDAI-YES, token1=sDAI => zero_for_one=False")
        elif token0.lower() == sdai_address.lower() and token1.lower() == sdai_yes_address.lower():
            zero_for_one = True # Swapping token0 (sDAI) for token1 (sDAI-YES)
            token_in = sdai_address
            token_out = sdai_yes_address
            print("   Pool order: token0=sDAI, token1=sDAI-YES => zero_for_one=True")
        else:
            print("\u274c Pool does not contain expected sDAI/sDAI-YES tokens")
            return False

        return self.swap_conditional(self.sdai_yes_pool_address, token_in, token_out, amount_in_sdai, zero_for_one, slippage_tolerance)

    def sell_sdai_yes(self, amount_in_sdai_yes: float, slippage_tolerance: float = 0.05) -> bool:
        """Sells sDAI-YES tokens for sDAI."""
        print(f"\n\U0001f504 Selling {amount_in_sdai_yes:.6f} sDAI-YES for sDAI...")

        pool_contract, _, token0, token1 = self._get_pool_data(self.sdai_yes_pool_address)
        if not pool_contract: return False

        sdai_address = self.w3.to_checksum_address(TOKEN_CONFIG["currency"]["address"])
        sdai_yes_address = self.w3.to_checksum_address(TOKEN_CONFIG["currency"]["yes_address"])

        if token0.lower() == sdai_yes_address.lower() and token1.lower() == sdai_address.lower():
            zero_for_one = True # Swapping token0 (sDAI-YES) for token1 (sDAI)
            token_in = sdai_yes_address
            token_out = sdai_address
            print("   Pool order: token0=sDAI-YES, token1=sDAI => zero_for_one=True")
        elif token0.lower() == sdai_address.lower() and token1.lower() == sdai_yes_address.lower():
            zero_for_one = False # Swapping token1 (sDAI-YES) for token0 (sDAI)
            token_in = sdai_yes_address
            token_out = sdai_address
            print("   Pool order: token0=sDAI, token1=sDAI-YES => zero_for_one=False")
        else:
            print("\u274c Pool does not contain expected sDAI/sDAI-YES tokens")
            return False

        return self.swap_conditional(self.sdai_yes_pool_address, token_in, token_out, amount_in_sdai_yes, zero_for_one, slippage_tolerance) 