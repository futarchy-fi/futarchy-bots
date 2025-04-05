#!/usr/bin/env python3
"""
Uniswap V3 Passthrough Router for swapping conditional tokens.

This module is currently in EXPERIMENTAL status.
Please use with caution as functionality may change.
"""

import os
from web3 import Web3
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_utils import to_hex
from dotenv import load_dotenv

# Load .env file but don't override existing environment variables
load_dotenv(override=False)

from futarchy.experimental.config.constants import TOKEN_CONFIG, ERC20_ABI

class PassthroughRouter:
    """
    Implementation of the Uniswap V3 Passthrough Router for swapping conditional tokens.
    This class follows the exact same logic as the passthrough_router_swap.py script.
    """
    
    # Router ABI from the original script
    ROUTER_ABI = [
        {
            "inputs": [
                {"internalType": "address", "name": "pool", "type": "address"},
                {"internalType": "address", "name": "recipient", "type": "address"},
                {"internalType": "bool", "name": "zeroForOne", "type": "bool"},
                {"internalType": "int256", "name": "amountSpecified", "type": "int256"},
                {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
                {"internalType": "bytes", "name": "data", "type": "bytes"}
            ],
            "name": "swap",
            "outputs": [
                {"internalType": "int256", "name": "amount0", "type": "int256"},
                {"internalType": "int256", "name": "amount1", "type": "int256"}
            ],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "owner",
            "outputs": [{"internalType": "address", "name": "", "type": "address"}],
            "stateMutability": "view",
            "type": "function"
        },
        {
            "inputs": [{"internalType": "address", "name": "pool", "type": "address"}],
            "name": "authorizePool",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]

    def __init__(self, w3: Web3, private_key: str, router_address: str):
        """Initialize the PassthroughRouter with web3 instance and contract addresses."""
        self.w3 = w3
        self.account: LocalAccount = Account.from_key(private_key)
        self.router_address = self.w3.to_checksum_address(router_address)
        self.router_contract = self.w3.eth.contract(
            address=self.router_address,
            abi=self.ROUTER_ABI
        )

    def _check_router_ownership(self) -> bool:
        """Check if we are the owner of the router."""
        router_owner = self.router_contract.functions.owner().call()
        return router_owner.lower() == self.account.address.lower()

    def _authorize_pool(self, pool_address: str) -> bool:
        """Authorize a pool for the router."""
        try:
            print("\n🔑 Authorizing pool for the router...")
            nonce = self.w3.eth.get_transaction_count(self.account.address)
            
            authorize_tx = self.router_contract.functions.authorizePool(
                pool_address
            ).build_transaction({
                "from": self.account.address,
                "nonce": nonce,
                "gas": 200000,
                "maxFeePerGas": self.w3.eth.gas_price * 2,
                "maxPriorityFeePerGas": self.w3.eth.gas_price,
                "chainId": self.w3.eth.chain_id,
                "type": "0x2"
            })

            signed_tx = self.w3.eth.account.sign_transaction(authorize_tx, private_key=self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"⏳ Pool authorization tx sent: {tx_hash.hex()}")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                print("✅ Pool authorization successful.")
                return True
            else:
                print("❌ Pool authorization failed.")
                return False
        except Exception as e:
            print(f"❌ Pool authorization error: {str(e)}")
            print("Continuing with swap attempt...")
            return True  # Continue anyway as the pool might already be authorized

    def _approve_token(self, token_address: str, amount: int) -> bool:
        """Approve the router to spend tokens."""
        try:
            token_contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
            current_allowance = token_contract.functions.allowance(
                self.account.address,
                self.router_address
            ).call()
            
            if current_allowance >= amount:
                return True

            print(f"🔑 Approving pass-through router to spend tokens...")
            nonce = self.w3.eth.get_transaction_count(self.account.address)
            
            approve_tx = token_contract.functions.approve(
                self.router_address,
                amount * 10  # Approve 10x to reduce future approvals
            ).build_transaction({
                "from": self.account.address,
                "nonce": nonce,
                "gas": 120000,
                "maxFeePerGas": self.w3.eth.gas_price * 2,
                "maxPriorityFeePerGas": self.w3.eth.gas_price,
                "chainId": self.w3.eth.chain_id,
                "type": "0x2"
            })

            signed_tx = self.w3.eth.account.sign_transaction(approve_tx, private_key=self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"⏳ Approval tx sent: {tx_hash.hex()}")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                print("✅ Approval successful.")
                return True
            else:
                print("❌ Approval failed.")
                return False
        except Exception as e:
            print(f"❌ Approval error: {str(e)}")
            return False

    def execute_swap(
        self,
        pool_address: str,
        token_in: str,
        token_out: str,
        amount: float,
        zero_for_one: bool,
        sqrt_price_limit_x96: int = 4295128740
    ) -> bool:
        """
        Execute a swap using the passthrough router.
        This follows the exact same logic as the passthrough_router_swap.py script.
        """
        try:
            # Convert amount to Wei
            amount_wei = self.w3.to_wei(amount, 'ether')
            
            # Check balances
            token_in_contract = self.w3.eth.contract(address=token_in, abi=ERC20_ABI)
            token_out_contract = self.w3.eth.contract(address=token_out, abi=ERC20_ABI)
            
            token_in_balance = token_in_contract.functions.balanceOf(self.account.address).call()
            token_out_balance_before = token_out_contract.functions.balanceOf(self.account.address).call()
            
            print(f"💰 Current balance: {self.w3.from_wei(token_in_balance, 'ether')} tokens")
            print(f"💰 Required amount: {amount} tokens")
            
            # If the difference between balance and requested amount is very small (< 0.0001 tokens),
            # use the entire balance instead
            balance_diff = abs(token_in_balance - amount_wei)
            if token_in_balance < amount_wei and balance_diff < self.w3.to_wei(0.0001, 'ether'):
                print(f"⚠️ Available balance is slightly less than requested. Using entire balance instead.")
                amount_wei = token_in_balance
                amount = float(self.w3.from_wei(amount_wei, 'ether'))
                print(f"💰 Updated amount: {amount} tokens")
            elif token_in_balance < amount_wei:
                print("❌ Insufficient balance")
                return False
            
            # Check router ownership
            if not self._check_router_ownership():
                print("❌ You are not the owner of the UniswapV3PassthroughRouter")
                return False
            
            # Approve tokens
            if not self._approve_token(token_in, amount_wei):
                return False
            
            # Authorize pool
            if not self._authorize_pool(pool_address):
                return False
            
            # Execute the swap
            print("\n🔄 Executing Uniswap V3 swap...")
            print(f"Pool: {pool_address}")
            print(f"Zero for One: {zero_for_one}")
            print(f"Amount: {amount_wei} ({amount} tokens)")
            print(f"Sqrt Price Limit X96: {sqrt_price_limit_x96}")
            
            nonce = self.w3.eth.get_transaction_count(self.account.address)
            
            swap_tx = self.router_contract.functions.swap(
                pool_address,
                self.account.address,  # recipient
                zero_for_one,
                amount_wei,
                sqrt_price_limit_x96,
                b''  # empty bytes for data
            ).build_transaction({
                "from": self.account.address,
                "nonce": nonce,
                "gas": 1000000,
                "maxFeePerGas": self.w3.eth.gas_price * 2,
                "maxPriorityFeePerGas": self.w3.eth.gas_price,
                "chainId": self.w3.eth.chain_id,
                "type": "0x2"
            })

            signed_tx = self.w3.eth.account.sign_transaction(swap_tx, private_key=self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            print(f"⏳ Swap transaction sent: {tx_hash.hex()}")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                print("✅ Swap successful!")
                
                # Check final balance
                token_out_balance_after = token_out_contract.functions.balanceOf(self.account.address).call()
                print(f"🔹 Token out balance: {self.w3.from_wei(token_out_balance_after, 'ether')}")
                gained = token_out_balance_after - token_out_balance_before
                print(f"🔹 Gained: {self.w3.from_wei(gained, 'ether')} tokens")
                
                print(f"\n🔗 Explorer: https://gnosisscan.io/tx/{tx_hash.hex()}")
                return True
            else:
                print("❌ Swap failed")
                return False
                
        except Exception as e:
            print(f"❌ Error during swap: {str(e)}")
            return False 