# futarchy/experimental/controllers/trading_controller.py
import traceback
from decimal import Decimal # For more precise balance checks if needed

try:
    # Relative imports
    from ..core.futarchy_bot import FutarchyBot
    from ..cli.view import View
    from ..models.swap_model import SwapModel
    from ..models.gno_wrapper_model import GnoWrapperModel
    from ..models.market_data_model import MarketDataModel # For balance checks
except ImportError:
    print("Error importing modules in TradingController. Check paths.")
    raise

class TradingController:
    """Handles commands related to buying, selling, and swapping tokens."""

    def __init__(self, bot_context: FutarchyBot, view: View, swap_model: SwapModel, gno_wrapper_model: GnoWrapperModel):
        self.bot = bot_context
        self.view = view
        self.swap_model = swap_model
        self.gno_wrapper_model = gno_wrapper_model
        self.market_data_model = MarketDataModel(bot_context) # Instantiate needed model

    def _check_balance(self, token_symbol_key: str, required_amount: float) -> bool:
        """Helper to check balance before an operation."""
        try:
            balances = self.market_data_model.get_all_balances()
            balance = 0
            token_name = ""
            if token_symbol_key == 'sDAI':
                balance = balances.get("currency", {}).get("wallet", 0)
                token_name = "sDAI"
            elif token_symbol_key == 'GNO':
                balance = balances.get("company", {}).get("wallet", 0)
                token_name = "GNO"
            elif token_symbol_key == 'waGNO':
                balance = balances.get("wagno", {}).get("wallet", 0)
                token_name = "waGNO"
            # Add other tokens if needed

            if Decimal(str(balance)) < Decimal(str(required_amount)):
                self.view.display_error(f"Insufficient {token_name} balance. Required: {required_amount}, Available: {balance}")
                return False
            return True
        except Exception as e:
            self.view.display_error(f"Error checking balance: {e}")
            return False

    def buy_gno(self, sdai_amount: float):
        """Buys GNO using sDAI (sDAI -> waGNO -> GNO)."""
        self.view.display_message(f"\nAttempting to buy GNO using {sdai_amount} sDAI...")

        # 1. Check sDAI balance
        if not self._check_balance('sDAI', sdai_amount):
            return

        # 2. Swap sDAI for waGNO
        self.view.display_message(f"Step 1/2: Swapping {sdai_amount} sDAI for waGNO on Balancer...")
        swap_result = self.swap_model.swap_on_balancer('sDAI', 'waGNO', sdai_amount)

        if not swap_result or not swap_result.get('success'):
            self.view.display_error(f"Swap failed: {swap_result.get('message', 'Unknown error')}")
            return
        
        wagno_received = swap_result.get('amount_out', 0.0)
        tx_hash_swap = swap_result.get('tx_hash')
        self.view.display_message(f"✅ Swap successful! Received approx {wagno_received:.6f} waGNO. Tx: {tx_hash_swap}")

        if wagno_received <= 0:
            self.view.display_error("Received zero waGNO from swap, cannot proceed with unwrap.")
            return

        # 3. Unwrap waGNO to GNO
        self.view.display_message(f"Step 2/2: Unwrapping {wagno_received:.6f} waGNO to GNO...")
        unwrap_result = self.gno_wrapper_model.unwrap_wagno(wagno_received)

        if not unwrap_result or not unwrap_result.get('success'):
            self.view.display_error(f"Unwrap failed: {unwrap_result.get('message', 'Unknown error')}")
            # Note: The swap already happened, user has waGNO
            self.view.display_message("Swap succeeded, but unwrap failed. You should have waGNO balance.")
        else:
            gno_received = unwrap_result.get('amount_unwrapped', 0.0)
            tx_hash_unwrap = unwrap_result.get('tx_hash')
            self.view.display_message(f"✅ Unwrap successful! Received approx {gno_received:.6f} GNO. Tx: {tx_hash_unwrap}")
            self.view.display_message("\n🎉 Buy GNO operation completed.")

        # 4. Display final balances
        self.view.display_message("\nFetching final balances...")
        balances = self.market_data_model.get_all_balances()
        self.view.display_balances(balances)


    def sell_gno(self, gno_amount: float):
        """Sells GNO for sDAI (GNO -> waGNO -> sDAI)."""
        self.view.display_message(f"\nAttempting to sell {gno_amount} GNO for sDAI...")

        # 1. Check GNO balance
        if not self._check_balance('GNO', gno_amount):
            return

        # 2. Wrap GNO to waGNO
        self.view.display_message(f"Step 1/2: Wrapping {gno_amount} GNO to waGNO...")
        wrap_result = self.gno_wrapper_model.wrap_gno(gno_amount)

        if not wrap_result or not wrap_result.get('success'):
            self.view.display_error(f"Wrap failed: {wrap_result.get('message', 'Unknown error')}")
            return

        wagno_wrapped = wrap_result.get('amount_wrapped', 0.0)
        tx_hash_wrap = wrap_result.get('tx_hash')
        self.view.display_message(f"✅ Wrap successful! Received approx {wagno_wrapped:.6f} waGNO. Tx: {tx_hash_wrap}")

        if wagno_wrapped <= 0:
            self.view.display_error("Received zero waGNO from wrap, cannot proceed with swap.")
            return

        # 3. Swap waGNO for sDAI
        self.view.display_message(f"Step 2/2: Swapping {wagno_wrapped:.6f} waGNO for sDAI on Balancer...")
        swap_result = self.swap_model.swap_on_balancer('waGNO', 'sDAI', wagno_wrapped)

        if not swap_result or not swap_result.get('success'):
            self.view.display_error(f"Swap failed: {swap_result.get('message', 'Unknown error')}")
            # Note: The wrap already happened, user has waGNO
            self.view.display_message("Wrap succeeded, but swap failed. You should have waGNO balance.")
        else:
            sdai_received = swap_result.get('amount_out', 0.0)
            tx_hash_swap = swap_result.get('tx_hash')
            self.view.display_message(f"✅ Swap successful! Received approx {sdai_received:.6f} sDAI. Tx: {tx_hash_swap}")
            self.view.display_message("\n🎉 Sell GNO operation completed.")

        # 4. Display final balances
        self.view.display_message("\nFetching final balances...")
        balances = self.market_data_model.get_all_balances()
        self.view.display_balances(balances)

    # Add other trading methods (buy_sdai_yes, sell_sdai_yes, etc.) here later 