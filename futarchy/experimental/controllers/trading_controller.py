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
    from ..models.conditional_token_model import ConditionalTokenModel # Add this import
except ImportError:
    print("Error importing modules in TradingController. Check paths.")
    raise

class TradingController:
    """Handles commands related to buying, selling, and swapping tokens."""

    def __init__(self, bot_context: FutarchyBot, view: View, swap_model: SwapModel, gno_wrapper_model: GnoWrapperModel, conditional_token_model: ConditionalTokenModel):
        self.bot = bot_context
        self.view = view
        self.swap_model = swap_model
        self.gno_wrapper_model = gno_wrapper_model
        self.conditional_token_model = conditional_token_model
        self.market_data_model = MarketDataModel(bot_context) # Instantiate needed model

    def _check_balance(self, token_symbol_key: str, required_amount: float) -> bool:
        """Helper to check balance before an operation."""
        try:
            balances = self.market_data_model.get_all_balances()
            balance = 0
            token_name = token_symbol_key # Use the key as default name

            # Handle base tokens
            if token_symbol_key == 'sDAI':
                balance = balances.get("currency", {}).get("wallet", 0)
                token_name = "sDAI"
            elif token_symbol_key == 'GNO':
                balance = balances.get("company", {}).get("wallet", 0)
                token_name = "GNO"
            elif token_symbol_key == 'waGNO':
                balance = balances.get("wagno", {}).get("wallet", 0)
                token_name = "waGNO"
                
            # Handle conditional tokens
            elif token_symbol_key == 'sDAI-YES':
                balance = balances.get("currency", {}).get("yes", 0)
                # token_name is already 'sDAI-YES'
            elif token_symbol_key == 'sDAI-NO':
                balance = balances.get("currency", {}).get("no", 0)
                # token_name is already 'sDAI-NO'
            elif token_symbol_key == 'GNO-YES':
                balance = balances.get("company", {}).get("yes", 0)
                # token_name is already 'GNO-YES'
            elif token_symbol_key == 'GNO-NO':
                balance = balances.get("company", {}).get("no", 0)
                # token_name is already 'GNO-NO'
            else:
                # Optional: Handle unknown token keys if necessary
                self.view.display_error(f"Unknown token symbol key '{token_symbol_key}' in _check_balance")
                return False

            if Decimal(str(balance)) < Decimal(str(required_amount)):
                self.view.display_error(f"Insufficient {token_name} balance. Required: {required_amount:.6f}, Available: {balance:.6f}")
                return False
            
            return True
        except Exception as e:
            self.view.display_error(f"Error checking balance for {token_symbol_key}: {e}")
            traceback.print_exc() # Added for debugging
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

    # --- Conditional Token Methods --- #

    def split_conditional_token(self, base_token: str, amount: float, simulate: bool = False):
        """Acquires conditional tokens by splitting the base token (e.g., sDAI -> sDAI-YES + sDAI-NO)."""
        # Determine base token symbol for the model (e.g., "sDAI", "GNO")
        # We might need a more robust mapping if symbols differ significantly
        base_token_symbol = base_token # Assuming input 'sDAI' maps directly to model's 'sDAI'
        
        action_desc = f"Split {amount:.6f} {base_token_symbol} into YES/NO tokens"
        if simulate:
            self.view.display_message(f"\n🔄 SIMULATING: {action_desc}...")
        else:
            self.view.display_message(f"\nAttempting: {action_desc}...")

        # 1. Check base token balance (using the symbol key, e.g., 'sDAI')
        if not self._check_balance(base_token_symbol, amount):
            return

        # 2. Call ConditionalTokenModel to split the position
        # The 'condition' argument ('yes'/'no') isn't directly used here,
        # as splitting always creates both YES and NO tokens.
        success, tx_hash = self.conditional_token_model.split_position(
            token_symbol=base_token_symbol, 
            amount=amount, 
            simulate=simulate
        )

        # 3. Handle result
        if success:
            if simulate:
                # Simulation success message is handled within the model
                self.view.display_message(f"\n✅ Split {base_token_symbol} simulation completed successfully.")
            else:
                # Execution success message is handled within the model
                self.view.display_message(f"\n🎉 Split {base_token_symbol} operation completed. Tx: {tx_hash}")
                # Display final balances
                self.view.display_message("\nFetching final balances...")
                balances = self.market_data_model.get_all_balances()
                self.view.display_balances(balances)
        else:
            # Failure message is handled within the model
            self.view.display_error(f"Split {base_token_symbol} {'simulation' if simulate else 'operation'} failed.")
            # Optionally display balances even on failure?

    def _check_conditional_pair_balance(self, base_token_symbol: str, required_amount: float) -> bool:
        """Helper to check balances of both YES and NO conditional tokens."""
        try:
            balances = self.market_data_model.get_all_balances()
            yes_balance = 0
            no_balance = 0
            yes_token_name = ""
            no_token_name = ""

            if base_token_symbol == 'sDAI':
                # Use nested access: balances['currency']['yes'] and ['no']
                currency_balances = balances.get("currency", {})
                yes_balance = currency_balances.get("yes", 0)
                no_balance = currency_balances.get("no", 0)
                yes_token_name = "sDAI-YES"
                no_token_name = "sDAI-NO"
            elif base_token_symbol == 'GNO':
                # Use nested access: balances['company']['yes'] and ['no']
                company_balances = balances.get("company", {})
                yes_balance = company_balances.get("yes", 0)
                no_balance = company_balances.get("no", 0)
                yes_token_name = "GNO-YES"
                no_token_name = "GNO-NO"
            else:
                 self.view.display_error(f"Unsupported base token for conditional balance check: {base_token_symbol}")
                 return False

            required = Decimal(str(required_amount))
            # Ensure balances are converted to Decimal for comparison
            has_yes = Decimal(str(yes_balance)) >= required
            has_no = Decimal(str(no_balance)) >= required

            if not has_yes or not has_no:
                # Display balances with potentially more precision if needed
                error_msg = f"Insufficient balance for merge. Required: {required_amount:.6f} each of {yes_token_name} and {no_token_name}.\n"
                error_msg += f"  Available: {yes_balance:.6f} {yes_token_name}, {no_balance:.6f} {no_token_name}"
                self.view.display_error(error_msg)
                return False
                
            return True
        except Exception as e:
            self.view.display_error(f"Error checking conditional pair balance: {e}")
            traceback.print_exc() # Added for debugging
            return False

    def merge_conditional_token(self, base_token: str, amount: float, simulate: bool = False):
        """Redeems base token by merging conditional YES and NO tokens."""
        base_token_symbol = base_token # Assuming input 'sDAI' maps directly to model's 'sDAI'
        # The 'condition' arg is not strictly needed for merge but helps identify the operation
        action_desc = f"Merge {amount:.6f} {base_token_symbol}-YES and {base_token_symbol}-NO back into {base_token_symbol}"

        if simulate:
            self.view.display_message(f"\n🔄 SIMULATING: {action_desc}...")
        else:
            self.view.display_message(f"\nAttempting: {action_desc}...")

        # 1. Check YES and NO conditional token balances
        if not self._check_conditional_pair_balance(base_token_symbol, amount):
            return

        # 2. Call ConditionalTokenModel to merge the positions
        success, tx_hash = self.conditional_token_model.merge_position(
            token_symbol=base_token_symbol,
            amount=amount,
            simulate=simulate
        )

        # 3. Handle result
        if success:
            if simulate:
                # Simulation success message is handled within the model
                self.view.display_message(f"\n✅ Merge {base_token_symbol} simulation completed successfully.")
            else:
                # Execution success message is handled within the model
                self.view.display_message(f"\n🎉 Merge {base_token_symbol} operation completed. Tx: {tx_hash}")
                # Display final balances
                self.view.display_message("\nFetching final balances...")
                balances = self.market_data_model.get_all_balances()
                self.view.display_balances(balances)
        else:
            # Failure message is handled within the model
            self.view.display_error(f"Merge {base_token_symbol} {'simulation' if simulate else 'operation'} failed.")

    # --- Conditional Token SWAP Methods --- #

    def buy_conditional_via_swap(self, input_token: str, output_token: str, amount: float, simulate: bool = False):
        """Buys one conditional token using another via swap (e.g., sDAI-YES -> GNO-YES)."""
        input_symbol_key = input_token # e.g., 'sDAI-YES'
        output_symbol_key = output_token # e.g., 'GNO-YES'
        
        action_desc = f"Swap {amount:.6f} {input_symbol_key} for {output_symbol_key}"
        if simulate:
            self.view.display_message(f"\n🔄 SIMULATING: {action_desc}...")
        else:
            self.view.display_message(f"\nAttempting: {action_desc}...")

        # 1. Check INPUT token balance
        if not self._check_balance(input_symbol_key, amount):
            return

        # 2. Simulate/Execute Swap
        swap_result = self.swap_model.swap_conditional(input_symbol_key, output_symbol_key, amount, simulate=simulate)

        if not swap_result or not swap_result.get('success'):
            error_msg = swap_result.get('message') or swap_result.get('error', 'Unknown error')
            self.view.display_error(f"Swap {'simulation' if simulate else ''} failed: {error_msg}")
            return
        
        # 3. Handle result
        if simulate:
            sim_amount_wei = swap_result.get('simulated_amount_out_wei', 0)
            sim_amount = self.bot.w3.from_wei(sim_amount_wei, 'ether')
            price = swap_result.get('estimated_price', 0) # Price here is input_token / output_token
            self.view.display_message(f"   - Simulation Result: Would receive ~{sim_amount:.6f} {output_symbol_key}")
            self.view.display_message(f"   - Estimated Price: ~{price:.6f} {input_symbol_key} per {output_symbol_key}")
            self.view.display_message(f"\n✅ Buy {output_symbol_key} via swap simulation completed.")
        else:
            output_received = swap_result.get('balance_changes', {}).get('token_out', 0.0)
            tx_hash_swap = swap_result.get('tx_hash')
            self.view.display_message(f"✅ Swap successful! Received approx {output_received:.6f} {output_symbol_key}. Tx: {tx_hash_swap}")
            self.view.display_message(f"\n🎉 Buy {output_symbol_key} via swap operation completed.")
            self.view.display_message("\nFetching final balances...")
            balances = self.market_data_model.get_all_balances()
            self.view.display_balances(balances)
            
    def sell_conditional_via_swap(self, input_token: str, output_token: str, amount: float, simulate: bool = False):
        """Sells one conditional token for another via swap (e.g., GNO-YES -> sDAI-YES)."""
        input_symbol_key = input_token  # e.g., 'GNO-YES'
        output_symbol_key = output_token # e.g., 'sDAI-YES'
        
        action_desc = f"Swap {amount:.6f} {input_symbol_key} for {output_symbol_key}"
        if simulate:
            self.view.display_message(f"\n🔄 SIMULATING: {action_desc}...")
        else:
            self.view.display_message(f"\nAttempting: {action_desc}...")

        # 1. Check INPUT token balance
        if not self._check_balance(input_symbol_key, amount):
            return

        # 2. Simulate/Execute Swap
        swap_result = self.swap_model.swap_conditional(input_symbol_key, output_symbol_key, amount, simulate=simulate)

        if not swap_result or not swap_result.get('success'):
            error_msg = swap_result.get('message') or swap_result.get('error', 'Unknown error')
            self.view.display_error(f"Swap {'simulation' if simulate else ''} failed: {error_msg}")
            return
        
        # 3. Handle result
        if simulate:
            sim_amount_wei = swap_result.get('simulated_amount_out_wei', 0)
            sim_amount = self.bot.w3.from_wei(sim_amount_wei, 'ether')
            price = swap_result.get('estimated_price', 0) # Price here is input_token / output_token
            # Invert price for more intuitive display (output_token per input_token)
            inv_price = 1 / price if price else 0 
            self.view.display_message(f"   - Simulation Result: Would receive ~{sim_amount:.6f} {output_symbol_key}")
            self.view.display_message(f"   - Estimated Price: ~{inv_price:.6f} {output_symbol_key} per {input_symbol_key}") 
            self.view.display_message(f"\n✅ Sell {input_symbol_key} via swap simulation completed.")
        else:
            output_received = swap_result.get('balance_changes', {}).get('token_out', 0.0)
            tx_hash_swap = swap_result.get('tx_hash')
            self.view.display_message(f"✅ Swap successful! Received approx {output_received:.6f} {output_symbol_key}. Tx: {tx_hash_swap}")
            self.view.display_message(f"\n🎉 Sell {input_symbol_key} via swap operation completed.")
            self.view.display_message("\nFetching final balances...")
            balances = self.market_data_model.get_all_balances()
            self.view.display_balances(balances)

    # --- END NEW METHODS ---

    # Add other trading methods (buy_sdai_yes, sell_sdai_yes, etc.) here later 