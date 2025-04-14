import time
import traceback
import json
import os
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Dict, Any, List

from web3 import Web3
from web3.exceptions import ContractLogicError

# --- Local Project Imports ---
# Assuming these ABIs and constants are defined in the config
from ...config import (
    CONTRACT_ADDRESSES,
    ERC20_ABI,
    CHAIN_ID
)
from ...config.abis.swapr import SWAPR_ROUTER_ABI, ALGEBRA_POOL_ABI
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

    # Constants for sqrt price limits (specific for Algebra protocol)
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
        Also returns the sqrtPriceX96 before and after the swap.
        CRASHES ON ERROR.
        """
        if not self.tenderly_client:
            # Keep this initial check, as it's a prerequisite
            return {'success': False, 'error': "Tenderly client not initialized", 'type': 'simulation'}

        token_in_addr_cs = self.w3.to_checksum_address(token_in_addr)
        token_out_addr_cs = self.w3.to_checksum_address(token_out_addr)

        # Get token addresses for matching
        sdai_yes_env = os.environ.get("SWAPR_SDAI_YES_ADDRESS")
        sdai_no_env = os.environ.get("SWAPR_SDAI_NO_ADDRESS")
        gno_yes_env = os.environ.get("SWAPR_GNO_YES_ADDRESS")
        gno_no_env = os.environ.get("SWAPR_GNO_NO_ADDRESS")

        sdai_yes = self.w3.to_checksum_address(sdai_yes_env) if sdai_yes_env else None
        sdai_no = self.w3.to_checksum_address(sdai_no_env) if sdai_no_env else None
        gno_yes = self.w3.to_checksum_address(gno_yes_env) if gno_yes_env else None
        gno_no = self.w3.to_checksum_address(gno_no_env) if gno_no_env else None
        sdai = self.w3.to_checksum_address(CONTRACT_ADDRESSES.get("baseCurrencyToken", ""))

        self._log(f"Using sDAI YES address: {sdai_yes} (from env: {bool(sdai_yes_env)})")
        self._log(f"Using sDAI NO address: {sdai_no} (from env: {bool(sdai_no_env)})")
        self._log(f"Using GNO YES address: {gno_yes} (from env: {bool(gno_yes_env)})")
        self._log(f"Using GNO NO address: {gno_no} (from env: {bool(gno_no_env)})")

        pool_address_cs = None

        # Determine the Swapr pool
        if sdai_yes and gno_yes and (token_in_addr_cs in [sdai_yes, gno_yes] and token_out_addr_cs in [sdai_yes, gno_yes]):
            swapr_pool_yes = os.environ.get("SWAPR_POOL_YES_ADDRESS")
            self._log(f"Value from os.environ.get('SWAPR_POOL_YES_ADDRESS'): '{swapr_pool_yes}'")
            if swapr_pool_yes:
                pool_address_cs = self.w3.to_checksum_address(swapr_pool_yes)
                self._log(f"Using Swapr YES Pool from env: {pool_address_cs}")
        elif sdai_no and gno_no and (token_in_addr_cs in [sdai_no, gno_no] and token_out_addr_cs in [sdai_no, gno_no]):
            swapr_pool_no = os.environ.get("SWAPR_POOL_NO_ADDRESS")
            if swapr_pool_no:
                pool_address_cs = self.w3.to_checksum_address(swapr_pool_no)
                self._log(f"Using Swapr NO Pool from env: {pool_address_cs}")
        elif sdai_yes and sdai and ((token_in_addr_cs == sdai_yes and token_out_addr_cs == sdai) or (token_out_addr_cs == sdai_yes and token_in_addr_cs == sdai)):
            swapr_sdai_yes_pool = os.environ.get("SWAPR_SDAI_YES_ADDRESS") # Env var seems incorrect, should be pool addr
            if swapr_sdai_yes_pool:
                 # Assuming SWAPR_SDAI_YES_ADDRESS is the pool address, not the token address
                 pool_address_cs = self.w3.to_checksum_address(swapr_sdai_yes_pool)
                 self._log(f"Using Swapr sDAI/YES Pool from env: {pool_address_cs}")
            elif "sdaiYesPool" in CONTRACT_ADDRESSES:
                 pool_address_cs = self.w3.to_checksum_address(CONTRACT_ADDRESSES["sdaiYesPool"])
                 self._log(f"Using sDAI YES/sDAI Pool Address from CONTRACT_ADDRESSES: {pool_address_cs}")

        # If no pool was determined from specific pairs, raise error
        if not pool_address_cs:
             # Removed the generic search loops for clarity as requested by user intent (crash if specific pair not found)
             raise ValueError(f"Could not determine Swapr pool address for specific token pair: {token_in_addr} <-> {token_out_addr}")

        amount_in_decimal = Decimal(str(amount_in)) # Let ValueError propagate
        amount_in_wei = self.w3.to_wei(amount_in_decimal, 'ether')

        # Parameters for Swapr Router's exactInputSingle
        deadline = int(time.time()) + 300
        params_tuple = (
            token_in_addr_cs,
            token_out_addr_cs,
            self.address,
            deadline,
            amount_in_wei,
            0, # amountOutMinimum
            0  # limitSqrtPrice
        )

        # Build transaction 1: Get price BEFORE swap
        tx_get_price_before = self.tenderly_client.encode_and_build_transaction(
            network_id=str(CHAIN_ID),
            from_address=self.address,
            to_address=pool_address_cs,
            abi=ALGEBRA_POOL_ABI,
            function_name="globalState",
            args=[],
            gas=1_000_000,
            save=False,
            simulation_type="full"
        )

        # Build transaction 2: Simulate the swap
        tx_swap_sim = self.tenderly_client.encode_and_build_transaction(
            network_id=str(CHAIN_ID),
            from_address=self.address,
            to_address=self.router_address,
            abi=SWAPR_ROUTER_ABI,
            function_name="exactInputSingle",
            args=[params_tuple],
            gas=8_000_000,
            save=False,
            simulation_type="full"
        )

        # Build transaction 3: Get price AFTER swap
        tx_get_price_after = self.tenderly_client.encode_and_build_transaction(
            network_id=str(CHAIN_ID),
            from_address=self.address,
            to_address=pool_address_cs,
            abi=ALGEBRA_POOL_ABI,
            function_name="globalState",
            args=[],
            gas=1_000_000,
            save=False,
            simulation_type="full"
        )

        if not tx_get_price_before or not tx_swap_sim or not tx_get_price_after:
            # Let this raise an error or handle appropriately if needed, removing try/except
            raise ValueError("Failed to prepare one or more transactions for simulation")

        # Run simulation bundle
        simulation_results = self.tenderly_client.simulate_bundle([
            tx_get_price_before,
            tx_swap_sim,
            tx_get_price_after
        ])

        if not simulation_results or len(simulation_results) != 3:
            raise ValueError("Simulation did not return all expected results")

        price_before_result = simulation_results[0]
        swap_result = simulation_results[1]
        price_after_result = simulation_results[2]

        # Extract simulation output amount and prices (NO TRY/EXCEPT)
        swap_transaction_info = swap_result['transaction']['transaction_info'] # Let KeyError propagate

        sqrt_price_x96_before = None
        sqrt_price_x96_after = None

        # For before price
        before_call_trace = price_before_result['transaction']['transaction_info']['call_trace']
        self._log(f"Before call trace: {json.dumps(before_call_trace, indent=2)[:500]}...")

        if before_call_trace and 'output' in before_call_trace:
            output = before_call_trace.get('output')
            self._log(f"Before price output: {output}")
            if output and output != "0x":
                 # Let decode errors propagate
                 pool_contract = self.w3.eth.contract(address=pool_address_cs, abi=ALGEBRA_POOL_ABI)
                 decoded_data = pool_contract.decode_function_result('globalState', output)
                 sqrt_price_x96_before = decoded_data[0]
                 self._log(f"Extracted sqrtPriceX96 before from globalState: {sqrt_price_x96_before}")
        else:
            self._log("No output in before_call_trace or call failed")
            self._log(f"before_call_trace status: {before_call_trace.get('error', 'No explicit error')}")
            if before_call_trace.get('error'): # Raise error if the call failed
                 raise RuntimeError(f"Price check before swap failed: {before_call_trace.get('error')}")

        # For after price
        after_call_trace = price_after_result['transaction']['transaction_info']['call_trace']
        self._log(f"After call trace: {json.dumps(after_call_trace, indent=2)[:500]}...")

        if after_call_trace and 'output' in after_call_trace:
            output = after_call_trace.get('output')
            self._log(f"After price output: {output}")
            if output and output != "0x":
                 # Let decode errors propagate
                 pool_contract = self.w3.eth.contract(address=pool_address_cs, abi=ALGEBRA_POOL_ABI)
                 decoded_data = pool_contract.decode_function_result('globalState', output)
                 sqrt_price_x96_after = decoded_data[0]
                 self._log(f"Extracted sqrtPriceX96 after from globalState: {sqrt_price_x96_after}")
        else:
            self._log("No output in after_call_trace or call failed")
            self._log(f"after_call_trace status: {after_call_trace.get('error', 'No explicit error')}")
            if after_call_trace.get('error'): # Raise error if the call failed
                 raise RuntimeError(f"Price check after swap failed: {after_call_trace.get('error')}")

        # Extract output data from swap call_trace
        raw_output = None
        if swap_transaction_info and swap_transaction_info.get('call_trace') and swap_transaction_info['call_trace'].get('output'):
            raw_output = swap_transaction_info['call_trace']['output']

        if raw_output and raw_output != "0x":
            simulated_amount_out_wei = Web3.to_int(hexstr=raw_output)
            sim_amount_out_decimal = self.w3.from_wei(simulated_amount_out_wei, 'ether')
            price = Decimal(amount_in_wei) / Decimal(simulated_amount_out_wei) if simulated_amount_out_wei else Decimal(0)

            return {
                'success': True,
                'simulated_amount_out_wei': simulated_amount_out_wei,
                'simulated_amount_out': float(sim_amount_out_decimal),
                'estimated_price': float(price),
                'sqrt_price_x96_before': sqrt_price_x96_before,
                'sqrt_price_x96_after': sqrt_price_x96_after,
                'pool_address': pool_address_cs,
                'type': 'simulation'
            }
        else:
            # Let this raise an error
            raise ValueError("No output data returned from swap simulation")


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

