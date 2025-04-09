import time
import traceback
from decimal import Decimal
from typing import TYPE_CHECKING
import json
import os

from web3 import Web3
from web3.exceptions import ContractLogicError

# Assuming these ABIs and constants are defined in the config
# You will need to add these ABIs to your config/abis/ directory
# and export them from config/constants.py
from ...config.constants import (
    CONTRACT_ADDRESSES,
    ERC20_ABI,
    # ALGEBRA_POOL_FACTORY_ABI, # Not used here
    # ALGEBRA_POOL_ABI          # Not used here
) 
from ...utils.web3_utils import get_raw_transaction
from ...config.abis.swapr import SWAPR_ROUTER_ABI # Import from the provided swapr.py

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
    """Handler for Swapr V3 (Algebra) swap operations on Gnosis Chain."""

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

        self._log("Initializing SwaprV3Handler...")

        # Load Swapr Router V3 contract
        self.router_address = self.w3.to_checksum_address(CONTRACT_ADDRESSES["swaprRouterV3"])
        self._log(f"Router Address: {self.router_address}")
        self.router_contract = self.w3.eth.contract(
            address=self.router_address,
            abi=SWAPR_ROUTER_ABI 
        )
        self._log("Router Contract loaded.")

        # Note: Factory contract is not strictly needed for exactInputSingle via Router
        # self.factory_address = self.w3.to_checksum_address(CONTRACT_ADDRESSES.get("algebraPoolFactory", "")) 
        # if self.factory_address:
        #     # Only load if address exists and ABI is potentially available via constants
        #     try:
        #         from ...config.constants import ALGEBRA_POOL_FACTORY_ABI
        #         self.factory_contract = self.w3.eth.contract(
        #             address=self.factory_address,
        #             abi=ALGEBRA_POOL_FACTORY_ABI
        #         )
        #     except ImportError:
        #         print("Warning: ALGEBRA_POOL_FACTORY_ABI not found in constants, factory operations unavailable.")
        #         self.factory_contract = None
        # else:
        #     self.factory_contract = None 
        
        if self.verbose:
            print(f"🔄 SwaprV3Handler initialized with Router: {self.router_address}")
            # if self.factory_address: print(f"   Factory: {self.factory_address}")
        self._log("SwaprV3Handler Initialization complete.")

    def simulate_swap_exact_in(self, token_in_addr: str, token_out_addr: str, amount_in: float) -> dict:
        """Simulates an exact input swap by calling the Swapr ROUTER's exactInputSingle function with .call()."""
        self._log(f"Simulate Input: amount_in={amount_in}, token_in={token_in_addr}, token_out={token_out_addr}")

        token_in_addr_cs = self.w3.to_checksum_address(token_in_addr)
        token_out_addr_cs = self.w3.to_checksum_address(token_out_addr)
        try:
            amount_in_wei = self.w3.to_wei(amount_in, 'ether')
        except ValueError:
             return {'success': False, 'error': f"Invalid amount: {amount_in}", 'type': 'simulation'}

        # Note: We don't need pool info just to call router's simulation if ABI allows direct call
        
        if self.verbose:
            print(f"🔄 Simulating Swapr V3 swap via Router Call: {amount_in} {token_in_addr} -> {token_out_addr}")

        # Parameters for Swapr Router's exactInputSingle (struct as dict)
        # amountOutMinimum = 1 # Use 1 wei to prevent reverts on zero output, but still allow simulation
        amountOutMinimum = 0 # Simplest simulation: Allow any amount out (max slippage)
        limitSqrtPrice = 0 # Simplest simulation: No price limit

        params = {
            'tokenIn': token_in_addr_cs,
            'tokenOut': token_out_addr_cs,
            'recipient': self.address, # Simulate receiving to our own address
            'deadline': int(time.time()) + 300, # Use a short deadline for simulation
            'amountIn': amount_in_wei,
            'amountOutMinimum': amountOutMinimum, 
            'limitSqrtPrice': limitSqrtPrice 
        }
        self._log(f"Simulation Params: {params}")

        try:
            self._log("Calling router_contract.functions.exactInputSingle(...).call()")
            simulated_amount_out_wei = self.router_contract.functions.exactInputSingle(params).call({
                'from': self.address # Simulate as if we are the sender
            })
            self._log(f"Simulation raw result (amountOut Wei): {simulated_amount_out_wei}")
            
            sim_amount_out_ether = self.w3.from_wei(simulated_amount_out_wei, 'ether')
            # Estimate price based on simulated amounts
            price = Decimal(amount_in_wei) / Decimal(simulated_amount_out_wei) if simulated_amount_out_wei else Decimal(0)
            
            self._log(f"Simulation OK: ~{sim_amount_out_ether} out, Price: {price:.6f} in/out")
            
            if self.verbose:
                print(f"   -> Simulation Result: ~{sim_amount_out_ether:.18f} out ({simulated_amount_out_wei} wei)")
                print(f"   -> Estimated Price: {price:.6f} in/out")
            return {
                'success': True,
                'simulated_amount_out_wei': simulated_amount_out_wei,
                'simulated_amount_out': float(sim_amount_out_ether),
                'estimated_price': float(price),
                'type': 'simulation'
            }
        except ContractLogicError as e:
            self._log(f"Simulation ContractLogicError: {e}")
            print(f"❌ Simulation failed (Router Revert): {e}")
            return {'success': False, 'error': f"Simulation Reverted: {e}", 'type': 'simulation'}
        except Exception as e:
            self._log(f"Simulation Exception: {e}")
            print(f"❌ Simulation error during router call: {e}")
            traceback.print_exc()
            return {'success': False, 'error': str(e), 'type': 'simulation'}

    def swap_exact_in(self, token_in_addr: str, token_out_addr: str, amount_in: float) -> dict:
        """Executes an exact input swap via the Swapr V3 Router."""
        self._log(f"Execute Input: amount_in={amount_in}, token_in={token_in_addr}, token_out={token_out_addr}")

        token_in_addr_cs = self.w3.to_checksum_address(token_in_addr)
        token_out_addr_cs = self.w3.to_checksum_address(token_out_addr)
        try:
             amount_in_wei = self.w3.to_wei(amount_in, 'ether')
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
                # Use bot helper for approval (mocked in test script)
                if not self.bot.approve_token(token_in_contract, self.router_address, amount_in_wei):
                    self._log("Approval transaction failed or was not confirmed by bot helper.")
                    raise TransactionFailed("Approval transaction failed or was not confirmed.")
                self._log("Approval successful (mocked or real).")
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

        params = {
            'tokenIn': token_in_addr_cs,
            'tokenOut': token_out_addr_cs,
            'recipient': self.address, 
            'deadline': deadline,
            'amountIn': amount_in_wei,
            'amountOutMinimum': amount_out_minimum,
            'limitSqrtPrice': 0 # No price limit
        }
        self._log(f"Execution Params: {params}")

        try:
            if self.verbose:
                print("Building swap transaction via Swapr Router...")
            
            # Simplification: Use a fixed high gas limit
            gas_estimate = 500000 
            self._log(f"Using fixed gas limit: {gas_estimate}")

            # Build Transaction
            self._log("Building transaction...")
            swap_tx = self.router_contract.functions.exactInputSingle(params).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
                'chainId': 100, # Gnosis Chain ID
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
            # Since we didn't simulate, we don't have an approx_amount_out readily available
            # approx_amount_out = sim_result.get('simulated_amount_out', 0.0)
            self._log(f"Swap successful. Tx Hash: {tx_hash.hex()}")
            
            # Return approx output based on simulation (actual output needs log parsing)
            # approx_amount_out = sim_result.get('simulated_amount_out', 0.0) # No sim_result available
  
            self._log(f"Returning success: tx_hash={tx_hash.hex()}")
            return {
                'success': True,
                'tx_hash': tx_hash.hex(),
                'receipt': dict(receipt), # Convert to dict for easier handling downstream
                # 'balance_changes': {'token_in': -float(amount_in), 'token_out': float(approx_amount_out)}, # Cannot estimate output
                'balance_changes': {'token_in': -float(amount_in), 'token_out': None}, # Indicate unknown output amount
                'type': 'execution'
            }

        except TransactionFailed as tf:
            self._log(f"TransactionFailed exception: {tf}")
            print(f"❌ {tf}")
            return {'success': False, 'error': str(tf), 'tx_hash': tf.receipt.transactionHash.hex() if tf.receipt else None, 'type': 'execution'}
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
