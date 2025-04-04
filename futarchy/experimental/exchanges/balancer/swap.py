"""
Balancer swap handler for executing swaps on Balancer pools.
This module provides functionality to execute swaps on Balancer with automatic Permit2 handling.
"""

import os
import json
from pathlib import Path
from web3 import Web3
import time

from config.constants import (
    CONTRACT_ADDRESSES, TOKEN_CONFIG, BALANCER_CONFIG,
    BALANCER_VAULT_ABI, BALANCER_POOL_ABI, BALANCER_BATCH_ROUTER_ABI,
    PERMIT2_ABI, ERC20_ABI
)
from .permit2 import BalancerPermit2Handler

class BalancerSwapHandler:
    """Handler for Balancer swap operations."""
    
    def __init__(self, bot):
        """
        Initialize the Balancer swap handler.
        
        Args:
            bot: FutarchyBot instance with web3 connection and account
        """
        self.bot = bot
        self.w3 = bot.w3
        self.account = bot.account
        self.address = bot.address
        self.verbose = bot.verbose
        
        # Initialize contracts
        self.batch_router = self.w3.eth.contract(
            address=self.w3.to_checksum_address(CONTRACT_ADDRESSES["batchRouter"]),
            abi=BALANCER_BATCH_ROUTER_ABI
        )
        self.permit2 = self.w3.eth.contract(
            address=self.w3.to_checksum_address(CONTRACT_ADDRESSES["permit2"]),
            abi=PERMIT2_ABI
        )
        
        # Initialize pool ID directly from constants
        self.pool_id = BALANCER_CONFIG["pool_id"]
        if self.verbose:
            print(f"Using pool ID: {self.pool_id}")
        
        # Initialize contracts
        self.init_contracts()
    
    def init_contracts(self):
        """Initialize contract instances."""
        try:
            # Initialize Balancer Vault contract
            self.balancer_vault = self.w3.eth.contract(
                address=self.w3.to_checksum_address(BALANCER_CONFIG["vault_address"]),
                abi=BALANCER_VAULT_ABI
            )
            
            # Initialize Balancer Pool contract
            self.balancer_pool = self.w3.eth.contract(
                address=self.w3.to_checksum_address(BALANCER_CONFIG["pool_address"]),
                abi=BALANCER_POOL_ABI
            )
            
            if self.verbose:
                print("✅ Contracts initialized successfully")
                
        except Exception as e:
            print(f"❌ Error initializing contracts: {e}")
    
    def _get_raw_transaction(self, signed_tx):
        """Get raw transaction bytes from signed transaction"""
        return signed_tx.rawTransaction if hasattr(signed_tx, 'rawTransaction') else signed_tx.raw_transaction
    
    def _get_token_symbol(self, token_contract):
        """Get token symbol safely"""
        try:
            return token_contract.functions.symbol().call()
        except:
            return token_contract.address[:8] + "..."
    
    def _print_balances(self, token_in, token_out, prefix=""):
        """Print current balances for given tokens"""
        token_in_contract = self.w3.eth.contract(address=token_in, abi=ERC20_ABI)
        token_out_contract = self.w3.eth.contract(address=token_out, abi=ERC20_ABI)
        
        balance_in = token_in_contract.functions.balanceOf(self.address).call()
        balance_out = token_out_contract.functions.balanceOf(self.address).call()
        
        token_in_symbol = self._get_token_symbol(token_in_contract)
        token_out_symbol = self._get_token_symbol(token_out_contract)
        
        print(f"{prefix}Balances:")
        print(f"  {token_in_symbol}: {self.w3.from_wei(balance_in, 'ether')} ({balance_in} wei)")
        print(f"  {token_out_symbol}: {self.w3.from_wei(balance_out, 'ether')} ({balance_out} wei)")
        
        return balance_in, balance_out
    
    def _ensure_permit2_approval(self, token, amount):
        """Ensure token is approved for Permit2"""
        token_contract = self.w3.eth.contract(address=token, abi=ERC20_ABI)
        permit2_allowance = token_contract.functions.allowance(
            self.address,
            CONTRACT_ADDRESSES["permit2"]
        ).call()
        
        if permit2_allowance < amount:
            print(f"Approving {token_contract.functions.symbol().call()} for Permit2...")
            approve_tx = token_contract.functions.approve(
                CONTRACT_ADDRESSES["permit2"],
                2**256 - 1  # Max approval
            ).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.w3.eth.chain_id
            })
            
            # Standardize signing
            signed_approve_tx = self.w3.eth.account.sign_transaction(approve_tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(self._get_raw_transaction(signed_approve_tx))
            print(f"Approval tx sent: {tx_hash.hex()}")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt['status'] != 1:
                raise Exception("Token approval for Permit2 failed")
            print("✅ Token approval for Permit2 successful")
        else:
            print("✅ Token already approved for Permit2")
    
    def _approve_batch_router(self, token, amount):
        """Approve BatchRouter to spend tokens through Permit2"""
        print("\nApproving BatchRouter to spend tokens through Permit2...")
        expiration = self.w3.eth.get_block('latest')['timestamp'] + 24 * 60 * 60
        
        approve_tx = self.permit2.functions.approve(
            token,
            CONTRACT_ADDRESSES["batchRouter"],
            amount,
            expiration
        ).build_transaction({
            'from': self.address,
            'nonce': self.w3.eth.get_transaction_count(self.address),
            'gas': 100000,
            'gasPrice': self.w3.eth.gas_price,
            'chainId': self.w3.eth.chain_id
        })
        
        # Standardize signing
        signed_approve_tx = self.w3.eth.account.sign_transaction(approve_tx, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(self._get_raw_transaction(signed_approve_tx))
        print(f"Permit2 approval tx sent: {tx_hash.hex()}")
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt['status'] != 1:
            raise Exception("BatchRouter approval through Permit2 failed")
        print("✅ BatchRouter approval through Permit2 successful")
    
    def swap_exact_in(self, token_in, token_out, amount, pool_address, slippage=0.05):
        """
        Swap exact amount of token_in for token_out using Balancer BatchRouter
        
        Args:
            token_in: Address of input token
            token_out: Address of output token
            amount: Amount of token_in to swap (in ether)
            pool_address: Address of Balancer pool
            slippage: Maximum acceptable slippage (default 5%)
        
        Returns:
            dict: Transaction result with success status and balance changes
        """
        # Convert addresses to checksum format
        token_in = self.w3.to_checksum_address(token_in)
        token_out = self.w3.to_checksum_address(token_out)
        pool_address = self.w3.to_checksum_address(pool_address)
        
        amount_wei = self.w3.to_wei(amount, 'ether')
        
        # Check and print initial balances
        initial_balance_in, initial_balance_out = self._print_balances(token_in, token_out, "Initial ")
        
        # Check if we have enough tokens
        if initial_balance_in < amount_wei:
            raise Exception(f"Insufficient balance. Need {amount} but only have {self.w3.from_wei(initial_balance_in, 'ether')}")
        
        # Ensure Permit2 approval
        self._ensure_permit2_approval(token_in, amount_wei)
        
        # Create swap path for query
        swap_path = {
            'tokenIn': token_in,
            'steps': [{
                'pool': pool_address,
                'tokenOut': token_out,
                'isBuffer': False
            }],
            'exactAmountIn': amount_wei,
            'minAmountOut': 0  # For query only
        }
        
        # Query expected output
        paths = [swap_path]
        expected_output = self.batch_router.functions.querySwapExactIn(
            paths,
            self.address,
            b''
        ).call()
        
        expected_amount = expected_output[0][0]
        print(f"\nExpected output: {self.w3.from_wei(expected_amount, 'ether')} ({expected_amount} wei)")
        
        # Calculate price
        price = amount_wei / expected_amount if expected_amount > 0 else 0
        print(f"Price: {price:.6f} {token_in} per {token_out}")
        
        # Calculate minimum amount with slippage
        print(f"Using {slippage*100}% slippage tolerance")
        min_amount_wei = int(expected_amount * (1 - slippage))
        print(f"Minimum amount to receive: {self.w3.from_wei(min_amount_wei, 'ether')} ({min_amount_wei} wei)\n")
        
        # Update swap path with minimum amount
        swap_path['minAmountOut'] = min_amount_wei
        
        # Approve BatchRouter through Permit2
        self._approve_batch_router(token_in, amount_wei)
        
        # Wait for nonce to be ready
        time.sleep(2)
        # Fetch pending nonce explicitly
        nonce = self.w3.eth.get_transaction_count(self.address, 'pending')
        print(f"BalancerSwapHandler using nonce: {nonce}")
        
        # Set deadline (30 minutes)
        deadline = self.w3.eth.get_block('latest')['timestamp'] + 1800
        
        # Build and send swap transaction
        swap_tx = self.batch_router.functions.swapExactIn(
            [swap_path],
            deadline,
            False,  # wethIsEth
            b''
        ).build_transaction({
            'from': self.address,
            'nonce': nonce,
            'gas': 500000,
            'gasPrice': self.w3.eth.gas_price,
            'chainId': self.w3.eth.chain_id
        })
        
        # Standardize signing
        signed_swap_tx = self.w3.eth.account.sign_transaction(swap_tx, self.account.key)
        tx_hash = self.w3.eth.send_raw_transaction(self._get_raw_transaction(signed_swap_tx))
        print(f"\nSwap transaction sent: {tx_hash.hex()}")
        
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt['status'] != 1:
            raise Exception("Swap transaction failed")
        
        print("✅ Swap successful!")
        
        # Check final balances and calculate changes
        final_balance_in, final_balance_out = self._print_balances(token_in, token_out, "\nFinal ")
        
        # Calculate precise balance changes safely
        delta_in_wei = final_balance_in - initial_balance_in
        delta_out_wei = final_balance_out - initial_balance_out
        
        try:
            balance_in_change = float(self.w3.from_wei(abs(delta_in_wei), 'ether')) * (-1 if delta_in_wei < 0 else 1)
            balance_out_change = float(self.w3.from_wei(abs(delta_out_wei), 'ether')) * (-1 if delta_out_wei < 0 else 1)
        except ValueError as e:
            # Handle potential ValueError if balance calculation fails, but swap succeeded
            print(f"⚠️ Warning: Could not calculate precise balance change: {e}")
            balance_in_change = 0 # Default to 0
            balance_out_change = 0 # Default to 0
        
        print("\nBalance Changes:")
        print(f"  {token_in}: {balance_in_change:+.18f}")
        print(f"  {token_out}: {balance_out_change:+.18f}")
        
        return {
            'success': True,
            'tx_hash': tx_hash.hex(),
            'balance_changes': {
                'token_in': balance_in_change,
                'token_out': balance_out_change
            }
        }
    
    def swap_sdai_to_wagno(self, amount):
        """Swap sDAI to waGNO"""
        return self.swap_exact_in(
            token_in=TOKEN_CONFIG["currency"]["address"],
            token_out=TOKEN_CONFIG["wagno"]["address"],
            amount=amount,
            pool_address=BALANCER_CONFIG["pool_address"]
        )
    
    def swap_wagno_to_sdai(self, amount):
        """Swap waGNO to sDAI"""
        return self.swap_exact_in(
            token_in=TOKEN_CONFIG["wagno"]["address"],
            token_out=TOKEN_CONFIG["currency"]["address"],
            amount=amount,
            pool_address=BALANCER_CONFIG["pool_address"]
        ) 