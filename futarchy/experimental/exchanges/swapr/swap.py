import time
import traceback
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Dict, Any, List
import json
import os

from web3 import Web3
from web3.exceptions import ContractLogicError

# --- Local Project Imports ---
# Assuming these ABIs and constants are defined in the config
from ...config import (
    CONTRACT_ADDRESSES,
    ERC20_ABI,
    CHAIN_ID
)
from ...config.abis.swapr import SWAPR_ROUTER_ABI
from ...utils.web3_utils import get_raw_transaction
# Import the Tenderly client class
from ...services.tenderly_client import TenderlySimulationClient # Adjust path as needed

# For type hinting without circular imports
if TYPE_CHECKING:
    from ...core.futarchy_bot import FutarchyBot

# Define custom exception locally if not globally available
class TransactionFailed(Exception):
    """Custom exception for failed transactions."""
    def __init__(self, message, receipt=None):
        super().__init__(message)
        self.receipt = receipt

class SwaprV3Handler:
    """
    Handler for Swapr V3 (Algebra) swap operations on Gnosis Chain,
    using Tenderly for simulations.
    """

    # Constants for sqrt price limits (approx values from Uniswap V3)
    MIN_SQRT_RATIO = 4295128739
    MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342

    def _log(self, *args):
        """Helper for verbose logging."""
        if self.verbose:
            print("   >", *args)

    def __init__(self, bot_context: "FutarchyBot"):
        self.bot = bot_context
        self.w3 = bot_context.w3
        self.account = bot_context.account
        self.address = bot_context.address
        self.verbose = bot_context.verbose
        # --- Tenderly Integration ---
        # Assuming the bot_context provides the initialized Tenderly client
        self.tenderly_client: Optional[TenderlySimulationClient] = getattr(bot_context, 'tenderly_client', None)
        if not self.tenderly_client:
             print("⚠️ Warning: TenderlySimulationClient not found in bot_context. Simulations will fail.")
        # --- End Tenderly Integration ---


        self._log("Initializing SwaprV3Handler...")

        # Load Swapr Router V3 contract
        self.router_address = self.w3.to_checksum_address(CONTRACT_ADDRESSES["swaprRouterV3"])
        self._log(f"Router Address: {self.router_address}")
        self.router_contract = self.w3.eth.contract(
            address=self.router_address,
            abi=SWAPR_ROUTER_ABI
        )
        self._log("Router Contract loaded.")

        if self.verbose:
            print(f"🔄 SwaprV3Handler initialized with Router: {self.router_address}")
            if self.tenderly_client:
                print(f"   Tenderly Client: Initialized for project {self.tenderly_client.project_slug}")
            else:
                print("   Tenderly Client: Not available")
        self._log("SwaprV3Handler Initialization complete.")

    def simulate_swap_exact_in(self, token_in_addr: str, token_out_addr: str, amount_in: float) -> dict:
        """
        Simulates an exact input swap using the Tenderly simulate-bundle API.
        """
        self._log(f"Simulate Input (Tenderly): amount_in={amount_in}, token_in={token_in_addr}, token_out={token_out_addr}")

        if not self.tenderly_client:
            return {'success': False, 'error': "Tenderly client not initialized", 'type': 'simulation'}

        token_in_addr_cs = self.w3.to_checksum_address(token_in_addr)
        token_out_addr_cs = self.w3.to_checksum_address(token_out_addr)
        try:
            # Use Decimal for precision before converting to Wei
            amount_in_decimal = Decimal(str(amount_in))
            # Assuming standard 18 decimals for conversion, adjust if token_in has different decimals
            # TODO: Fetch token_in decimals if necessary for accurate Wei conversion
            amount_in_wei = self.w3.to_wei(amount_in_decimal, 'ether')
        except ValueError:
             return {'success': False, 'error': f"Invalid amount: {amount_in}", 'type': 'simulation'}

        if self.verbose:
            print(f"🔄 Simulating Swapr V3 swap via Tenderly: {amount_in} {token_in_addr} -> {token_out_addr}")

        # Parameters for Swapr Router's exactInputSingle (struct as dict)
        amountOutMinimum = 0 # Allow any amount out for simulation (max slippage)
        limitSqrtPrice = 0 # No price limit for simulation
        deadline = int(time.time()) + 300 # Use a short deadline for simulation

        params_tuple = (
            token_in_addr_cs,
            token_out_addr_cs,
            self.address, # recipient
            deadline,
            amount_in_wei,
            amountOutMinimum,
            limitSqrtPrice
        )

        # --- Encode Input Data using Tenderly Client's helper (or directly) ---
        # Requires the Tenderly client to be initialized with a web3 provider
        print(f"[simulate_swap_exact_in] Calling encode_input with ABI: {SWAPR_ROUTER_ABI[:2]}... (truncated)") # DEBUG
        print(f"[simulate_swap_exact_in] Function name: exactInputSingle") # DEBUG
        print(f"[simulate_swap_exact_in] Args: {[params_tuple]}") # DEBUG
        input_data = self.tenderly_client.encode_input(
            abi=SWAPR_ROUTER_ABI,
            function_name="exactInputSingle",
            args=[params_tuple] # Pass the parameters as a tuple inside a list
        )

        if not input_data:
             error_msg = "Failed to encode input data for Tenderly simulation."
             self._log(error_msg)
             print(f"❌ {error_msg}")
             return {'success': False, 'error': error_msg, 'type': 'simulation'}

        # --- Build the Tenderly Transaction Object ---
        # Use a high gas limit for simulation to avoid out-of-gas errors unrelated to logic
        simulation_gas_limit = 8_000_000
        tenderly_tx = self.tenderly_client.build_transaction(
            network_id=str(CHAIN_ID), # Use Gnosis Chain ID
            from_address=self.address,      # Simulate from our address
            to_address=self.router_address, # Target the Swapr router
            gas=simulation_gas_limit,
            value="0",                      # Assuming token swap, not native ETH wrap
            input_data=input_data,
            save=False,                     # Don't save simple simulations by default
            simulation_type="full"          # Get detailed output including return value
        )

        # --- Call Tenderly API ---
        self._log(f"Calling tenderly_client.simulate_bundle with tx: {tenderly_tx}")
        simulation_results = self.tenderly_client.simulate_bundle([tenderly_tx])

        # --- Parse Tenderly Response ---
        if not simulation_results or not isinstance(simulation_results, list) or len(simulation_results) == 0:
            error_msg = "Tenderly simulation API call failed or returned empty/invalid response."
            self._log(error_msg)
            print(f"❌ {error_msg}")
            return {'success': False, 'error': error_msg, 'type': 'simulation'}

        tx_result = simulation_results[0] # Get the result for our single transaction

        if tx_result.get('status') is False:
            # Simulation reverted
            error_info = tx_result.get('error_info') or tx_result.get('error', {})
            # Try to extract a meaningful message
            error_message = error_info.get('message', 'Unknown simulation revert reason')
            if isinstance(error_message, dict): # Sometimes the message itself is nested
                 error_message = error_message.get('message', str(error_info))

            self._log(f"Tenderly Simulation Reverted: {error_message}")
            print(f"❌ Simulation failed (Tenderly Revert): {error_message}")
            return {'success': False, 'error': f"Simulation Reverted: {error_message}", 'type': 'simulation'}

        # --- DEBUG: Dump the transaction_info part of the result to a file --- 
        import json
        try:
            # Extract transaction_info, default to empty dict if not found
            transaction_info = tx_result.get('transaction', {}).get('transaction_info', {})
            with open("tenderly_sim_result.json", "w") as f:
                json.dump(transaction_info, f, indent=2)
            print("[DEBUG] Successfully dumped transaction_info to tenderly_sim_result.json")
        except Exception as e:
            print(f"[DEBUG] Error dumping transaction_info to file: {e}")
        # --- END DEBUG ---

        # Simulation Succeeded - Extract output amount
        try:
            # The return value of exactInputSingle is amountOut (uint256)
            raw_output = None

            # --- Correctly access nested output data using user's logic --- 
            # Get transaction_info nested within transaction object
            transaction_object = tx_result.get('transaction', {})
            transaction_info = transaction_object.get('transaction_info', {}) # Use user's provided access

            if transaction_info:
                call_trace = transaction_info.get('call_trace')
                if call_trace and call_trace.get('output') and call_trace['output'] != "0x":
                    print("[DEBUG] Found output in tx_result['transaction']['transaction_info']['call_trace']['output']") # DEBUG
                    raw_output = call_trace['output']
                else:
                    print("[DEBUG] Output not found in transaction_info.call_trace.output") # DEBUG
            else:
                 # Also check the top level tx_result just in case structure varies
                 transaction_info_alt = tx_result.get('transaction_info')
                 if transaction_info_alt:
                     call_trace_alt = transaction_info_alt.get('call_trace')
                     if call_trace_alt and call_trace_alt.get('output') and call_trace_alt['output'] != "0x":
                         print("[DEBUG] Found output directly in tx_result['transaction_info']['call_trace']['output']") # DEBUG
                         raw_output = call_trace_alt['output']
                     else:
                        print("[DEBUG] transaction_info found, but output not in call_trace.output") # DEBUG
                 else:
                    print("[DEBUG] transaction_info not found in tx_result.transaction or tx_result directly") # DEBUG
            # --- End output data search --- 

            if raw_output:
                simulated_amount_out_wei = Web3.to_int(hexstr=raw_output)
                self._log(f"Tenderly Simulation OK: Raw Output={raw_output}, Decoded Wei={simulated_amount_out_wei}")

                # TODO: Adjust 'ether' if token_out has different decimals
                sim_amount_out_decimal = self.w3.from_wei(simulated_amount_out_wei, 'ether')
                # Estimate price based on simulated amounts
                price = Decimal(amount_in_wei) / Decimal(simulated_amount_out_wei) if simulated_amount_out_wei else Decimal(0)

                self._log(f"Simulation OK: ~{sim_amount_out_decimal} out, Price: {price:.6f} in/out")

                if self.verbose:
                    print(f"   -> Tenderly Simulation Result: ~{sim_amount_out_decimal:.18f} out ({simulated_amount_out_wei} wei)")
                    print(f"   -> Estimated Price: {price:.6f} in/out")

                return {
                    'success': True,
                    'simulated_amount_out_wei': simulated_amount_out_wei,
                    'simulated_amount_out': float(sim_amount_out_decimal),
                    'estimated_price': float(price),
                    'type': 'simulation'
                }
            else:
                 # Succeeded but no output data?
                 error_msg = "Tenderly simulation succeeded but no output data found in expected locations (transaction.output or call_trace.output)."
                 # --- Remove the large DEBUG dump --- 
                 # import json
                 # print(f"[DEBUG] Full tx_result where output was not found:\n{json.dumps(tx_result, indent=2)}")
                 self._log(f"Warning: {error_msg}. Raw Output: {raw_output}")
                 print(f"⚠️ {error_msg}")
                 return {'success': False, 'error': error_msg, 'type': 'simulation'}

        except Exception as e:
            self._log(f"Error parsing Tenderly simulation result: {e}")
            print(f"❌ Error processing Tenderly result: {e}")
            traceback.print_exc()
            return {'success': False, 'error': f"Result parsing error: {e}", 'type': 'simulation'}


    def swap_exact_in(self, token_in_addr: str, token_out_addr: str, amount_in: float) -> dict:
        """Executes an exact input swap via the Swapr V3 Router. (Unchanged from original)"""
        self._log(f"Execute Input: amount_in={amount_in}, token_in={token_in_addr}, token_out={token_out_addr}")

        token_in_addr_cs = self.w3.to_checksum_address(token_in_addr)
        token_out_addr_cs = self.w3.to_checksum_address(token_out_addr)
        try:
             # Use Decimal for precision
             amount_in_decimal = Decimal(str(amount_in))
             # TODO: Fetch token_in decimals if necessary
             amount_in_wei = self.w3.to_wei(amount_in_decimal, 'ether')
        except ValueError:
             return {'success': False, 'error': f"Invalid amount: {amount_in}", 'type': 'execution'}

        token_in_contract = self.w3.eth.contract(address=token_in_addr_cs, abi=ERC20_ABI)

        self._log(f"TokenIn Contract: {token_in_addr_cs}")

        if self.verbose:
            print(f"\n⚙️ Executing Swapr V3 swap via Router: {amount_in} {token_in_addr} -> {token_out_addr}")

        # 1. Check Balance
        try:
            self._log(f"Checking balance of {token_in_addr_cs} for owner {self.address}")
            balance = token_in_contract.functions.balanceOf(self.address).call()
            self._log(f"Balance: {balance} wei")
            if balance < amount_in_wei:
                 # TODO: Fetch token_in decimals if necessary for display
                 error_msg = f"Insufficient balance for {token_in_addr}: Have {self.w3.from_wei(balance, 'ether')}, need {amount_in}"
                 print(f"❌ {error_msg}")
                 return {'success': False, 'error': error_msg, 'type': 'execution'}
        except Exception as e:
            print(f"❌ Error checking balance for {token_in_addr}: {e}")
            return {'success': False, 'error': f"Balance check failed: {e}", 'type': 'execution'}

        # 2. Check/Set Allowance for Router
        self._log(f"Checking allowance: owner={self.address}, spender={self.router_address}, token={token_in_addr_cs}")
        try:
            allowance = token_in_contract.functions.allowance(self.address, self.router_address).call()
            self._log(f"Current allowance: {allowance} wei")
            if allowance < amount_in_wei:
                self._log(f"Approval required: amount={amount_in_wei}")
                self._log(f"Calling bot.approve_token for spender {self.router_address}")
                # Use bot helper for approval
                if not self.bot.approve_token(token_in_contract, self.router_address, amount_in_wei):
                    self._log("Approval transaction failed or was not confirmed by bot helper.")
                    raise TransactionFailed("Approval transaction failed or was not confirmed.")
                self._log("Approval successful.")
                time.sleep(1) # Small delay after approval
            else:
                self._log("Allowance sufficient.")
        except Exception as e:
            self._log(f"Exception during approval check/process: {e}")
            error_msg = f"Error during approval check/process: {e}"
            print(f"❌ {error_msg}")
            traceback.print_exc()
            return {'success': False, 'error': error_msg, 'type': 'execution'}

        # Simplification: Set amountOutMinimum directly to 1 wei (minimal slippage protection)
        amount_out_minimum = 1
        self._log(f"Using fixed amount_out_minimum: {amount_out_minimum} wei")

        # 4. Prepare parameters for Swapr Router exactInputSingle
        deadline = int(time.time()) + 300 # 5 minute deadline

        # Note: exactInputSingle expects a tuple/struct for its parameter
        params_tuple = (
            token_in_addr_cs,
            token_out_addr_cs,
            self.address, # recipient
            deadline,
            amount_in_wei,
            amount_out_minimum,
            0 # limitSqrtPrice = 0 (no limit)
        )
        self._log(f"Execution Params Tuple: {params_tuple}")

        try:
            if self.verbose:
                print("Building swap transaction via Swapr Router...")

            # Simplification: Use a fixed high gas limit
            gas_estimate = 500000
            self._log(f"Using fixed gas limit: {gas_estimate}")

            # Build Transaction
            self._log("Building transaction...")
            swap_tx = self.router_contract.functions.exactInputSingle(params_tuple).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
                'chainId': CHAIN_ID, # Use constant
                'gas': gas_estimate,
                'gasPrice': self.w3.eth.gas_price, # Use current network gas price
            })
            self._log(f"Built Tx: {swap_tx}")

            if self.verbose:
                print("Signing transaction...")
                self._log("Signing transaction...")
            signed_tx = self.w3.eth.account.sign_transaction(swap_tx, self.account.key)
            self._log("Transaction signed.")

            if self.verbose:
                print("Sending transaction...")
                self._log("Sending raw transaction...")
            tx_hash = self.w3.eth.send_raw_transaction(get_raw_transaction(signed_tx))
            print(f"⏳ Swap transaction sent: {tx_hash.hex()}")
            print(f"   GnosisScan: https://gnosisscan.io/tx/{tx_hash.hex()}")
            self._log(f"Tx sent: {tx_hash.hex()}")

            if self.verbose:
                print("Waiting for confirmation...")
                self._log("Waiting for transaction receipt...")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300) # Increased timeout
            self._log(f"Receipt received: Status={receipt.status}")

            if receipt.status != 1:
                self._log(f"Transaction failed on-chain. Receipt: {receipt}")
                raise TransactionFailed(f"Swap transaction failed on-chain. Hash: {tx_hash.hex()}", receipt)

            print(f"✅ Swap successful! Tx: {tx_hash.hex()}")
            self._log(f"Swap successful. Tx Hash: {tx_hash.hex()}")

            self._log(f"Returning success: tx_hash={tx_hash.hex()}")
            return {
                'success': True,
                'tx_hash': tx_hash.hex(),
                'receipt': dict(receipt), # Convert to dict for easier handling downstream
                # Actual output amount needs log parsing from receipt, not available here
                'balance_changes': {'token_in': -float(amount_in_decimal), 'token_out': None},
                'type': 'execution'
            }

        except TransactionFailed as tf:
            self._log(f"TransactionFailed exception: {tf}")
            print(f"❌ {tf}")
            tx_hash_hex = tf.receipt.transactionHash.hex() if tf.receipt and hasattr(tf.receipt, 'transactionHash') else None
            return {'success': False, 'error': str(tf), 'tx_hash': tx_hash_hex, 'receipt': dict(tf.receipt) if tf.receipt else None, 'type': 'execution'}
        except Exception as e:
            self._log(f"Exception during execution: {e}")
            print(f"❌ Swap execution error: {e}")
            traceback.print_exc()
            # Include tx_hash if available
            error_dict = {'success': False, 'error': str(e), 'type': 'execution'}
            if 'tx_hash' in locals() and isinstance(tx_hash, bytes):
                self._log(f"Including tx_hash in error dict: {tx_hash.hex()}")
                error_dict['tx_hash'] = tx_hash.hex()
            return error_dict

