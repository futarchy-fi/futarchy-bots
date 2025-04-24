#!/usr/bin/env python3

import os
import json
import traceback
from web3 import Web3
from dotenv import load_dotenv
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_utils import to_hex
from pathlib import Path
import sys
import binascii

# Load .env file but don't override existing environment variables
load_dotenv(override=False)  # This ensures command-line vars take precedence

DEBUG = True

# Hardcoded constants instead of imports from config.constants
# Token configuration
TOKEN_CONFIG = {
    "currency": {
        "no_address": "0xE1133Ef862f3441880adADC2096AB67c63f6E102"  # NO_SDAI
    },
    "company": {
        "no_address": "0xf1B3E5Ffc0219A4F8C0ac69EC98C97709EdfB6c9"  # NO_GNO
    }
}

# ERC20 ABI - minimal version
ERC20_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {"internalType": "address", "name": "spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    }
]

def debug_print(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")

def send_signed_transaction(w3, signed_tx):
    """Helper function to handle different web3.py versions and their signed transaction formats"""
    try:
        # For newer web3.py versions
        return w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    except AttributeError:
        # For older web3.py versions or different signature formats
        if hasattr(signed_tx, 'raw_transaction'):
            return w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        elif isinstance(signed_tx, dict) and 'rawTransaction' in signed_tx:
            return w3.eth.send_raw_transaction(signed_tx['rawTransaction'])
        elif isinstance(signed_tx, dict) and 'raw_transaction' in signed_tx:
            return w3.eth.send_raw_transaction(signed_tx['raw_transaction'])
        elif hasattr(signed_tx, 'get'):
            if signed_tx.get('rawTransaction'):
                return w3.eth.send_raw_transaction(signed_tx.get('rawTransaction'))
            elif signed_tx.get('raw_transaction'):
                return w3.eth.send_raw_transaction(signed_tx.get('raw_transaction'))
        
        # If we can extract raw transaction as a hex string
        try:
            raw_tx_hex = to_hex(signed_tx)
            return w3.eth.send_raw_transaction(raw_tx_hex)
        except:
            pass
            
        # Last resort - try to access via r,s,v components
        try:
            tx_data = signed_tx.build_transaction()
            raw_tx = w3.eth.account.sign_transaction(tx_data, private_key=private_key)
            return w3.eth.send_raw_transaction(raw_tx.rawTransaction)
        except:
            raise ValueError(f"Could not extract raw transaction from signed transaction object: {type(signed_tx)}")

def main():
    # 1. Connect to Gnosis (or your preferred) chain
    rpc_url = os.getenv("GNOSIS_RPC_URL", "https://rpc.gnosis.gateway.fm")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("❌ Failed to connect to the blockchain")
        return

    print(f"✅ Connected to chain (chainId: {w3.eth.chain_id})")

    # 2. Load private key and create account object
    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        print("❌ PRIVATE_KEY not set in .env")
        return

    account: LocalAccount = Account.from_key(private_key)
    owner_address = account.address
    print(f"🔑 Using owner account: {owner_address}")

    # 3. Define contract addresses (update as needed)
    #    - Must match the deployed UniswapV3PassthroughRouter for which you are owner
    # UNISWAP_V3_PASSTHROUGH_ROUTER_ADDRESS = w3.to_checksum_address(os.getenv("V3_PASSTHROUGH_ROUTER_ADDRESS", "0x77DBE0441C950cE9C97a5F9A79CF316947aAa578"))
    UNISWAP_V3_PASSTHROUGH_ROUTER_ADDRESS = w3.to_checksum_address(os.getenv("V3_PASSTHROUGH_ROUTER_ADDRESS", "0x61A00dA5287988d39E8a354F386D600595B4D1e9"))
    # Updated pool address from the provided parameters (pool NO)
    UNISWAP_V3_POOL_ADDRESS = w3.to_checksum_address(os.getenv("UNISWAP_V3_POOL_ADDRESS", "0x6E33153115Ab58dab0e0F1E3a2ccda6e67FA5cD7"))
    # Default recipient address
    RECIPIENT_ADDRESS = w3.to_checksum_address(os.getenv("RECIPIENT_ADDRESS", "0x33A0b5d7DA5314594D2C163D448030b9F1cADcb2"))
    
    # Use NO_SDAI and NO_GNO tokens 
    TOKEN_IN_ADDRESS = w3.to_checksum_address(os.getenv("TOKEN_IN_ADDRESS", TOKEN_CONFIG["currency"]["no_address"]))  # NO_SDAI
    TOKEN_OUT_ADDRESS = w3.to_checksum_address(os.getenv("TOKEN_OUT_ADDRESS", TOKEN_CONFIG["company"]["no_address"])) # NO_GNO

    # 4. ABIs
    # Passthrough Router ABI updated with the new struct-based swap function
    passthrough_router_abi = [
        {
            "inputs": [
                {
                    "components": [
                        {"internalType": "address", "name": "pool", "type": "address"},
                        {"internalType": "address", "name": "recipient", "type": "address"},
                        {"internalType": "bytes", "name": "callbackData", "type": "bytes"}
                    ],
                    "internalType": "struct IUniswapV3PassthroughRouter.PoolInteraction",
                    "name": "poolInfo",
                    "type": "tuple"
                },
                {
                    "components": [
                        {"internalType": "bool", "name": "zeroForOne", "type": "bool"},
                        {"internalType": "int256", "name": "amountSpecified", "type": "int256"},
                        {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"},
                        {"internalType": "uint256", "name": "minAmountReceived", "type": "uint256"}
                    ],
                    "internalType": "struct IUniswapV3PassthroughRouter.TokenInteraction",
                    "name": "tokenInfo",
                    "type": "tuple"
                }
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

    # 5. Initialize contracts
    token_in_contract = w3.eth.contract(address=TOKEN_IN_ADDRESS, abi=ERC20_ABI)
    token_out_contract = w3.eth.contract(address=TOKEN_OUT_ADDRESS, abi=ERC20_ABI)
    router_contract = w3.eth.contract(address=UNISWAP_V3_PASSTHROUGH_ROUTER_ADDRESS, abi=passthrough_router_abi)

    # 6. Check balances
    token_in_balance = token_in_contract.functions.balanceOf(owner_address).call()
    token_out_balance_before = token_out_contract.functions.balanceOf(owner_address).call()
    
    # Update token names to reflect NO tokens
    token_in_symbol = "NO_SDAI" if TOKEN_IN_ADDRESS.lower() == TOKEN_CONFIG["currency"]["no_address"].lower() else "TOKEN_IN"
    token_out_symbol = "NO_GNO" if TOKEN_OUT_ADDRESS.lower() == TOKEN_CONFIG["company"]["no_address"].lower() else "TOKEN_OUT"
    
    print(f"💰 {w3.from_wei(token_in_balance, 'ether')} {token_in_symbol} balance")
    print(f"💰 {w3.from_wei(token_out_balance_before, 'ether')} {token_out_symbol} balance before swap")

    # 7. Decide how much to swap; ensure you have enough balance
    # Updated amount for testing (0.0001 tokens in wei)
    amount_in_wei = int(os.getenv("AMOUNT_TO_SWAP_WEI", "100000000000000"))
    # Allow for decimal input as well
    if os.getenv("AMOUNT_TO_SWAP"):
        amount_in_wei = w3.to_wei(float(os.getenv("AMOUNT_TO_SWAP")), "ether")
    
    print(f"🔄 Swap amount: {w3.from_wei(amount_in_wei, 'ether')} {token_in_symbol}")
    
    if token_in_balance < amount_in_wei:
        print(f"❌ Insufficient {token_in_symbol} balance.")
        return

    # 8. Check allowance. If insufficient, approve the pass-through router.
    current_allowance = token_in_contract.functions.allowance(owner_address, UNISWAP_V3_PASSTHROUGH_ROUTER_ADDRESS).call()
    print(f"Current allowance for router: {w3.from_wei(current_allowance, 'ether')}")

    if current_allowance < amount_in_wei:
        print(f"🔑 Approving pass-through router to spend our {token_in_symbol}...")
        nonce = w3.eth.get_transaction_count(owner_address)
        try:
            approve_tx = token_in_contract.functions.approve(
                UNISWAP_V3_PASSTHROUGH_ROUTER_ADDRESS, 
                amount_in_wei * 10  # Approve 10x to reduce repeated approvals
            ).build_transaction({
                "from": owner_address,
                "nonce": nonce,
                "gas": 120000,
                "maxFeePerGas": w3.eth.gas_price * 2,
                "maxPriorityFeePerGas": w3.eth.gas_price,
                "chainId": w3.eth.chain_id,
                "type": "0x2"
            })

            signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key=private_key)
            
            # Use our helper function to send the transaction safely
            tx_hash = send_signed_transaction(w3, signed_approve)
            
            print(f"⏳ Approval tx sent: 0x{tx_hash.hex()}")
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                print("✅ Approval successful.")
            else:
                print("❌ Approval failed.")
                return
        except Exception as e:
            print(f"❌ Approval error: {str(e)}")
            traceback.print_exc()
            return

    # 9. Perform the swap
    # For a normal "exact input" swap, amountSpecified > 0. 
    # Updated parameters from the provided data
    zero_for_one = True  # From the provided parameters
    sqrt_price_limit_x96 = 4295128740  # From the provided parameters
    min_amount_received = int(amount_in_wei * 0.001)  # Decreased from 1% to 0.1% of input to allow more slippage

    # Double check that your address is indeed the router's owner
    router_owner = router_contract.functions.owner().call()
    if router_owner.lower() != owner_address.lower():
        print("❌ You are not the owner of the UniswapV3PassthroughRouter. Swap will revert.")
        return

    # Determine if we need to authorize the pool first
    try:
        # Check if pool needs authorization
        # This could be done with a call to authorizedPools() if that function is available in the ABI
        # For simplicity, we'll just authorize the pool anyway (which is idempotent)
        print("\n🔑 Authorizing pool for the router...")
        nonce = w3.eth.get_transaction_count(owner_address)
        authorize_tx = router_contract.functions.authorizePool(
            UNISWAP_V3_POOL_ADDRESS
        ).build_transaction({
            "from": owner_address,
            "nonce": nonce,
            "gas": 200000,
            "maxFeePerGas": w3.eth.gas_price * 2,
            "maxPriorityFeePerGas": w3.eth.gas_price,
            "chainId": w3.eth.chain_id,
            "type": "0x2"
        })

        signed_authorize_tx = w3.eth.account.sign_transaction(authorize_tx, private_key=private_key)
        
        # Use our helper function to send the transaction safely
        tx_hash = send_signed_transaction(w3, signed_authorize_tx)
        
        print(f"⏳ Pool authorization tx sent: 0x{tx_hash.hex()}")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status == 1:
            print("✅ Pool authorization successful.")
        else:
            print("❌ Pool authorization failed.")
            return
    except Exception as e:
        print(f"❌ Pool authorization error: {str(e)}")
        # This might not be a fatal error if the pool is already authorized
        print("Continuing with swap attempt...")

    print("\n🔄 Executing Uniswap V3 swap...")
    print(f"Pool: {UNISWAP_V3_POOL_ADDRESS}")
    print(f"Recipient: {RECIPIENT_ADDRESS}")
    print(f"Zero for One: {zero_for_one}")
    print(f"Amount: {amount_in_wei} ({w3.from_wei(amount_in_wei, 'ether')} tokens)")
    print(f"Sqrt Price Limit X96: {sqrt_price_limit_x96}")
    print(f"Min Amount Received: {min_amount_received} ({w3.from_wei(min_amount_received, 'ether')} tokens)")
    print(f"Token In: {TOKEN_IN_ADDRESS} ({token_in_symbol})")
    print(f"Token Out: {TOKEN_OUT_ADDRESS} ({token_out_symbol})")
    
    try:
        nonce = w3.eth.get_transaction_count(owner_address)
        
        # Create the input structs for the new swap function signature
        pool_interaction = (
            UNISWAP_V3_POOL_ADDRESS,  # pool
            RECIPIENT_ADDRESS,        # recipient
            b''                       # callbackData (empty)
        )
        
        token_interaction = (
            zero_for_one,            # zeroForOne
            amount_in_wei,           # amountSpecified
            sqrt_price_limit_x96,    # sqrtPriceLimitX96
            min_amount_received      # minAmountReceived
        )
        
        # Check recipient's balance before swap
        recipient_balance_before = token_out_contract.functions.balanceOf(RECIPIENT_ADDRESS).call()
        print(f"🔹 {token_out_symbol} balance before swap (recipient): {w3.from_wei(recipient_balance_before, 'ether')}")
        
        swap_tx = router_contract.functions.swap(
            pool_interaction,   # poolInfo struct
            token_interaction   # tokenInfo struct
        ).build_transaction({
            "from": owner_address,
            "nonce": nonce,
            "gas": 1000000,  # increased from 500000 to 1000000
            "maxFeePerGas": w3.eth.gas_price * 2,
            "maxPriorityFeePerGas": w3.eth.gas_price,
            "chainId": w3.eth.chain_id,
            "type": "0x2"
        })

        debug_print("Signing and sending swap transaction...")
        signed_swap_tx = w3.eth.account.sign_transaction(swap_tx, private_key=private_key)
        
        # Use our helper function to send the transaction safely
        tx_hash = send_signed_transaction(w3, signed_swap_tx)
        
        print(f"⏳ Swap transaction sent: 0x{tx_hash.hex()}")

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        # Check recipient's balance after swap to determine if the swap was successful
        recipient_balance_after = token_out_contract.functions.balanceOf(RECIPIENT_ADDRESS).call()
        
        if receipt.status == 1:
            print("✅ Swap transaction confirmed on-chain.")
        else:
            print("⚠️ Transaction receipt shows reverted status, but checking actual balances...")
            
        # Determine success based on token balance change
        if recipient_balance_after > recipient_balance_before:
            print("✅ Swap successful! Recipient balance increased.")
        else:
            print("❌ Swap failed. No tokens received by recipient.")

        # 10. Check post-swap balances
        # If recipient is not our address, check their balance too
        token_out_balance_after = token_out_contract.functions.balanceOf(owner_address).call()
        print(f"🔹 {token_out_symbol} after swap (owner): {w3.from_wei(token_out_balance_after, 'ether')}")
        gained = token_out_balance_after - token_out_balance_before
        print(f"🔹 Gained (owner): {w3.from_wei(gained, 'ether')} {token_out_symbol}")
        
        if RECIPIENT_ADDRESS.lower() != owner_address.lower():
            tokens_received = recipient_balance_after - recipient_balance_before
            print(f"🔹 {token_out_symbol} balance (recipient): {w3.from_wei(recipient_balance_after, 'ether')}")
            print(f"🔹 Tokens received (recipient): {w3.from_wei(tokens_received, 'ether')} {token_out_symbol}")

        print(f"\n🔗 Explorer: https://gnosisscan.io/tx/0x{tx_hash.hex()}")

    except Exception as e:
        print(f"❌ Error during swap: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main() 