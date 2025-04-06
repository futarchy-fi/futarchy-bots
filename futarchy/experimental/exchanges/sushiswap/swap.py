# futarchy/experimental/exchanges/sushiswap/swap.py

import time
import traceback
from decimal import Decimal

from web3 import Web3
from web3.exceptions import ContractLogicError
from web3.contract import Contract
from typing import TYPE_CHECKING, Tuple

# For type hinting without circular imports
if TYPE_CHECKING:
    from ...core.futarchy_bot import FutarchyBot # <-- Moved import here

# Assuming these are defined in your config structure
from ...config.constants import (
    CONTRACT_ADDRESSES, TOKEN_CONFIG, UNISWAP_V3_CONFIG,
    # Add necessary ABIs if not already imported
    SUSHISWAP_V3_ROUTER_ABI, ERC20_ABI, UNISWAP_V3_POOL_ABI,
    POOL_CONFIG_YES, POOL_CONFIG_NO, # Import specific pool configs
)
from ...config.abis import SUSHISWAP_V3_ROUTER_ABI, ERC20_ABI # Remove duplicate if already above
from ...utils.web3_utils import get_raw_transaction

# Import the new handler
# from .sushiswap.swap import SushiSwapV3Handler # <-- REMOVE THIS LINE

# Define custom exception locally
class TransactionFailed(Exception):
    """Custom exception for failed transactions."""
    def __init__(self, message, receipt=None):
        super().__init__(message)
        self.receipt = receipt

class SushiSwapV3Handler:
    """Handler for SushiSwap V3 swap operations via the SushiSwap V3 Router."""

    # Constants for price limits (matching Uniswap V3 SDK)
    MIN_SQRT_RATIO = 4295128739
    MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970342

    def __init__(self, bot_context: "FutarchyBot"): # <-- Use string literal for type hint
        self.bot = bot_context
        self.w3 = bot_context.w3
        self.account = bot_context.account
        self.address = bot_context.address
        self.verbose = bot_context.verbose

        # Using the SushiSwap V3 Router address and ABI
        self.router_address = self.w3.to_checksum_address(CONTRACT_ADDRESSES["sushiswap"]) # <-- Use correct address key
        self.router_contract = self.w3.eth.contract(
            address=self.router_address,
            abi=SUSHISWAP_V3_ROUTER_ABI # <-- Use correct ABI
        )
        if self.verbose:
            print(f"🍣 SushiSwapV3Handler initialized with SushiSwap Router: {self.router_address}") # <-- Updated print message
            
    def _get_pool_info(self, token_in_addr: str, token_out_addr: str) -> Tuple[str, int, bool, Contract]:
        """Retrieve pool address, fee, token order (zeroForOne), and pool contract instance for known YES/NO pools."""
        token_in_addr_lower = token_in_addr.lower()
        token_out_addr_lower = token_out_addr.lower()
        
        # Define expected addresses for YES and NO pools
        sDAI_YES = CONTRACT_ADDRESSES["currencyYesToken"].lower()
        sDAI_NO = CONTRACT_ADDRESSES["currencyNoToken"].lower()
        GNO_YES = CONTRACT_ADDRESSES["companyYesToken"].lower()
        GNO_NO = CONTRACT_ADDRESSES["companyNoToken"].lower()

        target_pool_config = None
        expected_pair = None

        # Check if the input tokens match the YES pool configuration
        pair_yes = tuple(sorted((GNO_YES, sDAI_YES)))
        input_pair = tuple(sorted((token_in_addr_lower, token_out_addr_lower)))

        if input_pair == pair_yes:
            target_pool_config = POOL_CONFIG_YES
            token0 = GNO_YES if POOL_CONFIG_YES["tokenCompanySlot"] == 0 else sDAI_YES
            print(f"Identified YES Pool: {target_pool_config['address']}")
        else:
            # Check if the input tokens match the NO pool configuration
            pair_no = tuple(sorted((GNO_NO, sDAI_NO)))
            if input_pair == pair_no:
                target_pool_config = POOL_CONFIG_NO
                token0 = GNO_NO if POOL_CONFIG_NO["tokenCompanySlot"] == 0 else sDAI_NO
                print(f"Identified NO Pool: {target_pool_config['address']}")
            # else: # We could add checks for other known pools here if needed
            #     pass

        if target_pool_config:
            pool_address = self.w3.to_checksum_address(target_pool_config["address"])
            fee = target_pool_config["fee"]
            # Determine zeroForOne based on the actual token0 found
            zeroForOne = token_in_addr_lower == token0
            pool_contract = self.w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
            print(f"Found pool: {pool_address}, Fee: {fee}, zeroForOne: {zeroForOne}")
            return pool_address, fee, zeroForOne, pool_contract
        else:
            # If no match for YES/NO pools, raise error (or implement factory lookup later)
            raise ValueError(f"Could not find known V3 pool info for {token_in_addr} <-> {token_out_addr}")

    # Reverted simulation method: Estimates based on current pool price
    def simulate_swap_exact_in(self, token_in_addr: str, token_out_addr: str, amount_in: float) -> dict:
        """Estimates exact input swap output based on current pool spot price."""
        token_in_addr_cs = self.w3.to_checksum_address(token_in_addr)
        token_out_addr_cs = self.w3.to_checksum_address(token_out_addr)
        try:
            amount_in_wei = self.w3.to_wei(amount_in, 'ether')
        except ValueError:
             return {'success': False, 'error': f"Invalid amount: {amount_in}", 'type': 'simulation'}

        try:
            pool_address, pool_fee, zeroForOne, pool_contract = self._get_pool_info(token_in_addr_cs, token_out_addr_cs)
        except ValueError as e:
            print(f"❌ Simulation error finding pool: {e}")
            return {'success': False, 'error': str(e), 'type': 'simulation'}

        print(f"🔄 Estimating SushiSwap V3 swap based on Pool Price: {amount_in} {token_in_addr} -> {token_out_addr}")

        try:
            # Get current price from pool's slot0
            slot0 = pool_contract.functions.slot0().call()
            current_sqrt_price_x96 = slot0[0]
            
            # Calculate spot price (price of token1 in terms of token0)
            spot_price_t1_t0 = (Decimal(current_sqrt_price_x96) / Decimal(2**96))**2

            # Calculate estimated output based on direction
            if zeroForOne: # Swapping token0 for token1
                # Estimated token1 out = amount_token0_in / price_t1_t0
                estimated_out_wei = Decimal(amount_in_wei) * spot_price_t1_t0 
            else: # Swapping token1 for token0
                # Estimated token0 out = amount_token1_in * price_t1_t0 
                # We want price of token0 in terms of token1 for easy calc
                spot_price_t0_t1 = 1 / spot_price_t1_t0 if spot_price_t1_t0 != 0 else 0
                estimated_out_wei = Decimal(amount_in_wei) * spot_price_t0_t1
                
            # Crude fee adjustment (subtract approx fee from output)
            # This is very basic and doesn't account for exact fee mechanics
            fee_decimal = Decimal(pool_fee) / Decimal(1_000_000)
            estimated_out_wei *= (Decimal(1) - fee_decimal)
            
            simulated_amount_out_wei = int(estimated_out_wei)
            sim_amount_out_ether = self.w3.from_wei(simulated_amount_out_wei, 'ether')
            
            # Calculate effective price based on estimation
            price = Decimal(amount_in_wei) / Decimal(simulated_amount_out_wei) if simulated_amount_out_wei else Decimal(0)
            
            print(f"   -> Estimated Output (Spot Price - Fee): ~{sim_amount_out_ether:.18f} out ({simulated_amount_out_wei} wei)")
            print(f"   -> Estimated Price (In/Out): {price:.6f}")
            print(f"   ⚠️ Note: Simulation uses spot price and basic fee calc, actual output may vary.")
            return {
                'success': True,
                'simulated_amount_out_wei': simulated_amount_out_wei,
                'simulated_amount_out': float(sim_amount_out_ether),
                'estimated_price': float(price),
                'type': 'simulation'
            }
        except Exception as e:
            # Catch other errors like connection problems etc.
            print(f"❌ Simulation error during estimation: {e}")
            traceback.print_exc()
            return {'success': False, 'error': str(e), 'type': 'simulation'}
            
    def swap_exact_in(self, token_in_addr: str, token_out_addr: str, amount_in: float, slippage: float = 0.005) -> dict:
        """Executes an exact input swap via the SushiSwap V3 Router."""
        token_in_addr = self.w3.to_checksum_address(token_in_addr)
        token_out_addr = self.w3.to_checksum_address(token_out_addr)
        amount_in_wei = self.w3.to_wei(amount_in, 'ether')
        token_in_contract = self.w3.eth.contract(address=token_in_addr, abi=ERC20_ABI)

        try:
            pool_address, pool_fee, zeroForOne, pool_contract = self._get_pool_info(token_in_addr, token_out_addr)
        except ValueError as e:
            print(f"❌ Execution error: {e}")
            return {'success': False, 'error': str(e), 'type': 'execution'}

        print(f"\n⚙️ Executing SushiSwap V3 swap via Passthrough Router: {amount_in} {token_in_addr} -> {token_out_addr}")

        # 1. Check Balance
        balance = token_in_contract.functions.balanceOf(self.address).call()
        if balance < amount_in_wei:
             error_msg = f"Insufficient balance for {token_in_addr}"
             print(f"❌ {error_msg}")
             return {'success': False, 'error': error_msg, 'type': 'execution'}

        # 2. Approve Router (The PASSTHROUGH Router)
        print(f"Checking/setting allowance for Passthrough Router: {self.router_address}")
        try:
            allowance = token_in_contract.functions.allowance(self.address, self.router_address).call()
            if allowance < amount_in_wei:
                print(f"Current allowance ({allowance}) is less than required ({amount_in_wei}). Approving...")
                # Max approval
                max_approve_amount = 2**256 - 1 
                approve_tx = token_in_contract.functions.approve(
                    self.router_address, max_approve_amount
                ).build_transaction({
                    'from': self.address,
                    'nonce': self.w3.eth.get_transaction_count(self.address),
                    'gas': 100000, # Standard approval gas limit
                    'gasPrice': self.w3.eth.gas_price,
                })
                signed_approve_tx = self.w3.eth.account.sign_transaction(approve_tx, self.account.key)
                approve_tx_hash = self.w3.eth.send_raw_transaction(get_raw_transaction(signed_approve_tx))
                print(f"⏳ Approval transaction sent: {approve_tx_hash.hex()}")
                approve_receipt = self.w3.eth.wait_for_transaction_receipt(approve_tx_hash, timeout=180)
                if approve_receipt.status != 1:
                    raise TransactionFailed(f"Approval transaction failed. Hash: {approve_tx_hash.hex()}", approve_receipt)
                print("✅ Approval successful!")
                # Need to wait briefly or fetch nonce again for the main tx
                time.sleep(1) 
            else:
                print("✅ Sufficient allowance already set.")
        except Exception as e:
             error_msg = f"Error during approval: {e}"
             print(f"❌ {error_msg}")
             traceback.print_exc()
             return {'success': False, 'error': error_msg, 'type': 'execution'}

        # 3. Calculate sqrtPriceLimitX96 based on current price and slippage
        try:
            slot0 = pool_contract.functions.slot0().call()
            current_sqrt_price_x96 = slot0[0]

            if zeroForOne:
                # Price is decreasing, limit is lower bound based on slippage
                sqrt_price_limit_x96 = int(Decimal(str(current_sqrt_price_x96)) * (Decimal(1) - Decimal(str(slippage))))
                sqrt_price_limit_x96 = max(sqrt_price_limit_x96, self.MIN_SQRT_RATIO)
            else:
                # Price is increasing, limit is upper bound based on slippage
                sqrt_price_limit_x96 = int(Decimal(str(current_sqrt_price_x96)) * (Decimal(1) + Decimal(str(slippage))))
                sqrt_price_limit_x96 = min(sqrt_price_limit_x96, self.MAX_SQRT_RATIO)
            
            print(f"Current sqrtPriceX96: {current_sqrt_price_x96}")
            print(f"Calculated sqrtPriceLimitX96: {sqrt_price_limit_x96} based on {slippage*100}% slippage")

        except Exception as e:
            print(f"❌ Error calculating price limit: {e}. Cannot proceed.")
            return {'success': False, 'error': f'Error calculating price limit: {e}', 'type': 'execution'}

        # 4. Prepare parameters for Passthrough Router swap()
        # Note: Router pulls from owner (msg.sender), recipient is final destination
        params = (
            pool_address,
            self.address, # recipient = final user address
            zeroForOne,
            amount_in_wei, # amountSpecified (positive for exact input)
            sqrt_price_limit_x96, # <-- Use calculated limit
            b'' # data (can be empty as router encodes sender internally)
        )

        try:
            print("Building swap transaction via Passthrough Router...")
            # Calling the custom router's swap function
            swap_tx = self.router_contract.functions.swap(*params).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
                'gas': 600000, # May need higher gas for router + pool interaction
                'gasPrice': self.w3.eth.gas_price,
                # 'value': 0 # Only needed if swapping native token
            })

            print("Signing transaction...")
            signed_tx = self.w3.eth.account.sign_transaction(swap_tx, self.account.key)
            
            print("Sending transaction...")
            tx_hash = self.w3.eth.send_raw_transaction(get_raw_transaction(signed_tx))
            print(f"⏳ Swap transaction sent: {tx_hash.hex()}")
            
            print("Waiting for confirmation...")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
            
            if receipt.status != 1:
                raise TransactionFailed(f"Swap transaction failed. Hash: {tx_hash.hex()}", receipt)
                
            print(f"✅ Swap successful! Tx: {tx_hash.hex()}")
            
            # Get approx amount out from simulation for return value (still useful info)
            sim_result = self.simulate_swap_exact_in(token_in_addr, token_out_addr, amount_in)
            simulated_amount_out_wei = sim_result.get('simulated_amount_out_wei', 0)
            approx_amount_out = float(self.w3.from_wei(simulated_amount_out_wei, 'ether'))
            
            return {
                'success': True,
                'tx_hash': tx_hash.hex(),
                'receipt': receipt,
                'balance_changes': {'token_in': -amount_in, 'token_out': approx_amount_out},
                'type': 'execution'
            }

        except Exception as e:
            print(f"❌ Swap execution error: {e}")
            traceback.print_exc()
            # Include tx_hash if available
            error_dict = {'success': False, 'error': str(e), 'type': 'execution'}
            if 'tx_hash' in locals():
                error_dict['tx_hash'] = tx_hash.hex()
            return error_dict 