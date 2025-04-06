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

    def buy_gno(self, sdai_amount: float, simulate: bool = False):
        """Buys GNO using sDAI (sDAI -> waGNO -> GNO)."""
        if simulate:
            self.view.display_message(f"\n🔄 SIMULATING buy GNO using {sdai_amount:.6f} sDAI...")
        else:
            self.view.display_message(f"\nAttempting to buy GNO using {sdai_amount} sDAI...")

        # 1. Check sDAI balance
        if not self._check_balance('sDAI', sdai_amount):
            return

        # 2. Simulate/Execute Swap sDAI for waGNO
        step1_msg = f"Step 1/2: Swapping {sdai_amount} sDAI for waGNO on Balancer..."
        self.view.display_message(step1_msg if not simulate else f"🔄 SIMULATING {step1_msg}")
        swap_result = self.swap_model.swap_on_balancer('sDAI', 'waGNO', sdai_amount, simulate=simulate)

        if not swap_result or not swap_result.get('success'):
            error_msg = swap_result.get('message') or swap_result.get('error', 'Unknown error')
            self.view.display_error(f"Swap {'simulation' if simulate else ''} failed: {error_msg}")
            return
        
        # Process simulation result for step 1
        if simulate:
            sim_amount_wei = swap_result.get('simulated_amount_out_wei', 0)
            sim_amount = self.bot.w3.from_wei(sim_amount_wei, 'ether')
            price = swap_result.get('estimated_price', 0)
            self.view.display_message(f"   - Simulation Result: Would receive ~{sim_amount:.6f} waGNO")
            self.view.display_message(f"   - Estimated Price: ~{price:.6f} sDAI per waGNO")
            wagno_received = float(sim_amount) # Use simulated amount for next step simulation
        else:
            # Execution result processing
            wagno_received = swap_result.get('balance_changes', {}).get('token_out', 0.0)
            tx_hash_swap = swap_result.get('tx_hash')
            self.view.display_message(f"✅ Swap successful! Received approx {wagno_received:.6f} waGNO. Tx: {tx_hash_swap}")

        if wagno_received <= 0:
            self.view.display_error(f"Received zero waGNO from swap{'' if not simulate else ' simulation'}, cannot proceed.")
            return

        # 3. Simulate/Execute Unwrap waGNO to GNO
        step2_msg = f"Step 2/2: Unwrapping {wagno_received:.6f} waGNO to GNO..."
        self.view.display_message(step2_msg if not simulate else f"🔄 SIMULATING {step2_msg}")
        unwrap_result = self.gno_wrapper_model.unwrap_wagno(wagno_received, simulate=simulate)

        if not unwrap_result or not unwrap_result.get('success'):
            error_msg = unwrap_result.get('message') or unwrap_result.get('error', 'Unknown error')
            self.view.display_error(f"Unwrap {'simulation' if simulate else ''} failed: {error_msg}")
            if not simulate: # Only show this message on execution failure
                self.view.display_message("Swap succeeded, but unwrap failed. You should have waGNO balance.")
            return
        
        # Process simulation result for step 2
        if simulate:
            sim_amount = unwrap_result.get('simulated_amount_out', 0)
            self.view.display_message(f"   - Simulation Result: Would receive ~{sim_amount:.6f} GNO")
            self.view.display_message("\n✅ Buy GNO simulation completed.")
            # No balance display needed for simulation
            return
        else:
            # Execution result processing
            gno_received = unwrap_result.get('amount_unwrapped', 0.0) # Model assumes 1:1 for now
            tx_hash_unwrap = unwrap_result.get('tx_hash')
            self.view.display_message(f"✅ Unwrap successful! Received approx {gno_received:.6f} GNO. Tx: {tx_hash_unwrap}")
            self.view.display_message("\n🎉 Buy GNO operation completed.")

        # 4. Display final balances (only on execution)
        self.view.display_message("\nFetching final balances...")
        balances = self.market_data_model.get_all_balances()
        self.view.display_balances(balances)


    def sell_gno(self, gno_amount: float, simulate: bool = False):
        """Sells GNO for sDAI (GNO -> waGNO -> sDAI)."""
        if simulate:
            self.view.display_message(f"\n🔄 SIMULATING sell {gno_amount:.6f} GNO for sDAI...")
        else:
            self.view.display_message(f"\nAttempting to sell {gno_amount} GNO for sDAI...")

        # 1. Check GNO balance
        if not self._check_balance('GNO', gno_amount):
            return

        # 2. Simulate/Execute Wrap GNO to waGNO
        step1_msg = f"Step 1/2: Wrapping {gno_amount} GNO to waGNO..."
        self.view.display_message(step1_msg if not simulate else f"🔄 SIMULATING {step1_msg}")
        wrap_result = self.gno_wrapper_model.wrap_gno(gno_amount, simulate=simulate)

        if not wrap_result or not wrap_result.get('success'):
            error_msg = wrap_result.get('message') or wrap_result.get('error', 'Unknown error')
            self.view.display_error(f"Wrap {'simulation' if simulate else ''} failed: {error_msg}")
            return

        # Process simulation result for step 1
        if simulate:
            # Use input GNO amount directly as wrapped amount due to simulation limitations
            sim_amount = wrap_result.get('simulated_amount_out', gno_amount) # Use gno_amount as fallback
            self.view.display_message(f"   - Simulation Result: Assumed ~{sim_amount:.6f} waGNO (due to simulation limitations)")
            wagno_wrapped = float(sim_amount)
        else:
            # Execution result processing
            wagno_wrapped = wrap_result.get('amount_wrapped', 0.0)
            tx_hash_wrap = wrap_result.get('tx_hash')
            self.view.display_message(f"✅ Wrap successful! Received approx {wagno_wrapped:.6f} waGNO. Tx: {tx_hash_wrap}")

        if wagno_wrapped <= 0:
            self.view.display_error(f"Received zero waGNO from wrap{'' if not simulate else ' simulation'}, cannot proceed.")
            return

        # 3. Simulate/Execute Swap waGNO for sDAI
        step2_msg = f"Step 2/2: Swapping {wagno_wrapped:.6f} waGNO for sDAI on Balancer..."
        self.view.display_message(step2_msg if not simulate else f"🔄 SIMULATING {step2_msg}")
        swap_result = self.swap_model.swap_on_balancer('waGNO', 'sDAI', wagno_wrapped, simulate=simulate)

        if not swap_result or not swap_result.get('success'):
            error_msg = swap_result.get('message') or swap_result.get('error', 'Unknown error')
            self.view.display_error(f"Swap {'simulation' if simulate else ''} failed: {error_msg}")
            if not simulate: # Only show this message on execution failure
                self.view.display_message("Wrap succeeded, but swap failed. You should have waGNO balance.")
            return
            
        # Process simulation result for step 2
        if simulate:
            sim_amount_wei = swap_result.get('simulated_amount_out_wei', 0)
            sim_amount = self.bot.w3.from_wei(sim_amount_wei, 'ether')
            price = swap_result.get('estimated_price', 0)
            self.view.display_message(f"   - Simulation Result: Would receive ~{sim_amount:.6f} sDAI")
            self.view.display_message(f"   - Estimated Price: ~{price:.6f} waGNO per sDAI") # Price is waGNO/sDAI here
            self.view.display_message("\n✅ Sell GNO simulation completed.")
            # No balance display needed for simulation
            return
        else:
            # Execution result processing
            sdai_received = swap_result.get('balance_changes', {}).get('token_out', 0.0)
            tx_hash_swap = swap_result.get('tx_hash')
            self.view.display_message(f"✅ Swap successful! Received approx {sdai_received:.6f} sDAI. Tx: {tx_hash_swap}")
            self.view.display_message("\n🎉 Sell GNO operation completed.")

        # 4. Display final balances (only on execution)
        self.view.display_message("\nFetching final balances...")
        balances = self.market_data_model.get_all_balances()
        self.view.display_balances(balances)

    # Add other trading methods (buy_sdai_yes, sell_sdai_yes, etc.) here later 