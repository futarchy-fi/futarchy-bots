# futarchy/experimental/managers/conditional_token_manager.py
import traceback
from typing import Optional

# Assuming these paths are correct relative to this file's location
try:
    from ..core.futarchy_bot import FutarchyBot # Relative import
    from ..config.constants import TOKEN_CONFIG, CONTRACT_ADDRESSES
except ImportError:
    print("Error importing modules in ConditionalTokenManager. Check relative paths or project structure.")
    raise

class ConditionalTokenManager:
    """Manages splitting and merging of conditional tokens."""

    def __init__(self, bot: FutarchyBot):
        self.bot = bot
        self.w3 = bot.w3
        self.account = bot.account
        self.address = bot.address
        self.verbose = bot.verbose

    def split(self, token_symbol: str, amount: float) -> bool:
        """
        Splits a base token (GNO or sDAI) into YES/NO conditional tokens.

        Args:
            token_symbol: 'GNO' or 'sDAI'.
            amount: Amount of the base token to split (in ether units).

        Returns:
            True if successful, False otherwise.
        """
        token_type_map = {'GNO': 'company', 'sDAI': 'currency'}
        token_type = token_type_map.get(token_symbol)
        if not token_type:
            print(f"\u274c Invalid token symbol for split: {token_symbol}")
            return False

        print(f"\n\U0001f504 Splitting {amount} {token_symbol} into YES/NO tokens...")
        try:
            return self.bot.add_collateral(token_type, amount)
        except Exception as e:
            print(f"\u274c Error during split operation: {e}")
            traceback.print_exc()
            return False

    def merge(self, token_symbol: str, amount: float) -> bool:
        """
        Merges YES/NO conditional tokens back into the base token (GNO or sDAI).

        Args:
            token_symbol: 'GNO' or 'sDAI'.
            amount: Amount of YES/NO pairs to merge (in ether units).

        Returns:
            True if successful, False otherwise.
        """
        token_type_map = {'GNO': 'company', 'sDAI': 'currency'}
        token_type = token_type_map.get(token_symbol)
        if not token_type:
            print(f"\u274c Invalid token symbol for merge: {token_symbol}")
            return False

        print(f"\n\U0001f504 Merging {amount} {token_symbol}-YES/NO pairs back into {token_symbol}...")
        try:
            return self.bot.remove_collateral(token_type, amount)
        except Exception as e:
            print(f"\u274c Error during merge operation: {e}")
            traceback.print_exc()
            return False 