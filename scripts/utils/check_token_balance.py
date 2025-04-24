#!/usr/bin/env python3

import os
from web3 import Web3
from dotenv import load_dotenv
from eth_account import Account

# Load environment variables
load_dotenv(override=False)

# Token configuration - hardcoded for simplicity
TOKEN_CONFIG = {
    "currency": {
        "address": "0xaf204776c7245bF4147c2612BF6e5972Ee483701",  # sDAI
        "no_address": "0xE1133Ef862f3441880adADC2096AB67c63f6E102"  # NO_SDAI
    },
    "company": {
        "address": "0x9C58BAcC331c9aa871AFD802DB6379a98e80CEdb",  # GNO
        "no_address": "0xf1B3E5Ffc0219A4F8C0ac69EC98C97709EdfB6c9"  # NO_GNO
    }
}

# Minimal ERC20 ABI for balance checking
ERC20_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function"
    }
]

def main():
    # Connect to Gnosis chain
    rpc_url = os.getenv("GNOSIS_RPC_URL", "https://rpc.gnosis.gateway.fm")
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print("❌ Failed to connect to the blockchain")
        return

    print(f"✅ Connected to chain (chainId: {w3.eth.chain_id})")

    # Get account from private key
    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        print("❌ PRIVATE_KEY not set in .env")
        return

    account = Account.from_key(private_key)
    address = account.address
    print(f"🔑 Checking balances for account: {address}")

    # Check native token balance (xDAI)
    native_balance = w3.eth.get_balance(address)
    print(f"💰 Native Token (xDAI): {w3.from_wei(native_balance, 'ether')}")

    # Token addresses to check
    token_addresses = [
        # Regular tokens
        (TOKEN_CONFIG["currency"]["address"], "sDAI"),
        (TOKEN_CONFIG["company"]["address"], "GNO"),
        # NO tokens
        (TOKEN_CONFIG["currency"]["no_address"], "NO_SDAI"),
        (TOKEN_CONFIG["company"]["no_address"], "NO_GNO"),
    ]

    # Check all token balances
    for token_address, token_symbol in token_addresses:
        token_address = w3.to_checksum_address(token_address)
        token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        
        try:
            # Try to get actual symbol from contract
            actual_symbol = token_contract.functions.symbol().call()
            token_symbol = f"{token_symbol} ({actual_symbol})"
        except:
            pass  # Use default symbol if contract call fails
            
        balance = token_contract.functions.balanceOf(address).call()
        
        # Try to get decimals, default to 18 if not available
        try:
            decimals = token_contract.functions.decimals().call()
        except:
            decimals = 18
            
        formatted_balance = balance / (10 ** decimals)
        print(f"💰 {token_symbol}: {formatted_balance}")

if __name__ == "__main__":
    main() 