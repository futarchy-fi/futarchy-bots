#!/usr/bin/env python3
"""
Futarchy Trading Bot - Main entry point

This module is currently in EXPERIMENTAL status.
Please use with caution as functionality may change.
"""

import sys
import os
import argparse
from decimal import Decimal
import time
import json
from web3 import Web3
from dotenv import load_dotenv
from futarchy.experimental.exchanges.sushiswap import SushiSwapExchange
from futarchy.experimental.exchanges.passthrough_router import PassthroughRouter
from futarchy.experimental.config.constants import (
    CONTRACT_ADDRESSES,
    TOKEN_CONFIG,
    POOL_CONFIG_YES,
    POOL_CONFIG_NO,
    BALANCER_CONFIG,
    DEFAULT_SWAP_CONFIG,
    DEFAULT_PERMIT_CONFIG,
    DEFAULT_RPC_URLS,
    UNISWAP_V3_POOL_ABI,
    UNISWAP_V3_PASSTHROUGH_ROUTER_ABI,
    ERC20_ABI
)
from eth_account import Account
from eth_account.signers.local import LocalAccount
import math

# Add the current directory to the path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from futarchy.experimental.core.futarchy_bot import FutarchyBot
from futarchy.experimental.strategies.monitoring import simple_monitoring_strategy
from futarchy.experimental.strategies.probability import probability_threshold_strategy
from futarchy.experimental.strategies.arbitrage import arbitrage_strategy
# Import the moved functions
from futarchy.experimental.actions.conditional_token_actions import sell_sdai_yes, buy_sdai_yes
# Import BalancerSwapHandler as it's used in arbitrage functions
from futarchy.experimental.exchanges.balancer.swap import BalancerSwapHandler

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Futarchy Trading Bot')
    
    # General options
    parser.add_argument('--rpc', type=str, help='RPC URL for Gnosis Chain')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    
    # Command mode
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Interactive mode (default)
    interactive_parser = subparsers.add_parser('interactive', help='Run in interactive mode')
    
    # Monitor mode
    monitor_parser = subparsers.add_parser('monitor', help='Run monitoring strategy')
    monitor_parser.add_argument('--iterations', type=int, default=5, help='Number of monitoring iterations')
    monitor_parser.add_argument('--interval', type=int, default=60, help='Interval between updates (seconds)')
    
    # Probability strategy mode
    prob_parser = subparsers.add_parser('prices', help='Show current market prices and probabilities')
    prob_parser.add_argument('--buy', type=float, default=0.7, help='Buy threshold')
    prob_parser.add_argument('--sell', type=float, default=0.3, help='Sell threshold')
    prob_parser.add_argument('--amount', type=float, default=0.1, help='Trade amount')
    
    # Arbitrage strategy mode
    arb_parser = subparsers.add_parser('arbitrage', help='Run arbitrage strategy')
    arb_parser.add_argument('--diff', type=float, default=0.02, help='Minimum price difference')
    arb_parser.add_argument('--amount', type=float, default=0.1, help='Trade amount')
    
    # Balance commands
    balances_parser = subparsers.add_parser('balances', help='Show token balances')
    refresh_balances_parser = subparsers.add_parser('refresh_balances', help='Refresh and show token balances')
    
    # Buy GNO commands
    buy_wrapped_gno_parser = subparsers.add_parser('buy_wrapped_gno', help='Buy waGNO with sDAI')
    buy_wrapped_gno_parser.add_argument('amount', type=float, help='Amount of sDAI to spend')
    
    buy_gno_parser = subparsers.add_parser('buy_gno', help='Buy GNO with sDAI (buys waGNO and unwraps it)')
    buy_gno_parser.add_argument('amount', type=float, help='Amount of sDAI to spend')
    
    wrap_gno_parser = subparsers.add_parser('wrap_gno', help='Wrap GNO to waGNO')
    wrap_gno_parser.add_argument('amount', type=float, help='Amount of GNO to wrap')
    
    unwrap_wagno_parser = subparsers.add_parser('unwrap_wagno', help='Unwrap waGNO to GNO')
    unwrap_wagno_parser.add_argument('amount', type=float, help='Amount of waGNO to unwrap')
    
    split_gno_parser = subparsers.add_parser('split_gno', help='Split GNO into YES/NO tokens')
    split_gno_parser.add_argument('amount', type=float, help='Amount of GNO to split')
    
    swap_gno_yes_parser = subparsers.add_parser('swap_gno_yes', help='Swap GNO YES to sDAI YES')
    swap_gno_yes_parser.add_argument('amount', type=float, help='Amount of GNO YES to swap')
    
    swap_gno_no_parser = subparsers.add_parser('swap_gno_no', help='Swap GNO NO to sDAI NO')
    swap_gno_no_parser.add_argument('amount', type=float, help='Amount of GNO NO to swap')
    
    # Add the arbitrage synthetic GNO command (sell direction)
    arbitrage_sell_synthetic_gno_parser = subparsers.add_parser('arbitrage_sell_synthetic_gno', 
                                help='Execute full arbitrage: buy GNO spot → split → sell YES/NO → balance & merge')
    arbitrage_sell_synthetic_gno_parser.add_argument('amount', type=float, help='Amount of sDAI to use for arbitrage')
    
    # Add the arbitrage synthetic GNO command (buy direction)
    arbitrage_buy_synthetic_gno_parser = subparsers.add_parser('arbitrage_buy_synthetic_gno', 
                                help='Execute full arbitrage: buy sDAI-YES/NO → buy GNO-YES/NO → merge → wrap → sell')
    arbitrage_buy_synthetic_gno_parser.add_argument('amount', type=float, help='Amount of sDAI to use for arbitrage')
    
    # Add the four new passthrough router swap commands
    swap_gno_yes_to_sdai_yes_parser = subparsers.add_parser('swap_gno_yes_to_sdai_yes', help='Swap GNO YES to sDAI YES using passthrough router')
    swap_gno_yes_to_sdai_yes_parser.add_argument('amount', type=float, help='Amount of GNO YES to swap')
    
    swap_sdai_yes_to_gno_yes_parser = subparsers.add_parser('swap_sdai_yes_to_gno_yes', help='Swap sDAI YES to GNO YES using passthrough router')
    swap_sdai_yes_to_gno_yes_parser.add_argument('amount', type=float, help='Amount of sDAI YES to swap')
    
    swap_gno_no_to_sdai_no_parser = subparsers.add_parser('swap_gno_no_to_sdai_no', help='Swap GNO NO to sDAI NO using passthrough router')
    swap_gno_no_to_sdai_no_parser.add_argument('amount', type=float, help='Amount of GNO NO to swap')
    
    swap_sdai_no_to_gno_no_parser = subparsers.add_parser('swap_sdai_no_to_gno_no', help='Swap sDAI NO to GNO NO using passthrough router')
    swap_sdai_no_to_gno_no_parser.add_argument('amount', type=float, help='Amount of sDAI NO to swap')
    
    # Add merge_sdai command
    merge_sdai_parser = subparsers.add_parser('merge_sdai', help='Merge sDAI-YES and sDAI-NO back into sDAI')
    merge_sdai_parser.add_argument('amount', type=float, help='Amount of sDAI-YES and sDAI-NO to merge')
    
    # Add buy_sdai_yes command
    buy_sdai_yes_parser = subparsers.add_parser('buy_sdai_yes', help='Buy sDAI-YES tokens with sDAI using the dedicated sDAI/sDAI-YES pool')
    buy_sdai_yes_parser.add_argument('amount', type=float, help='Amount of sDAI to spend')
    
    # Add debug command
    debug_parser = subparsers.add_parser('debug', help='Run in debug mode with additional output')
    
    # Add test_swaps command
    test_swaps_parser = subparsers.add_parser('test_swaps', help='Test all swap functions with small amounts')
    test_swaps_parser.add_argument('--amount', type=float, default=0.001, help='Amount to use for testing (default: 0.001)')
    
    return parser.parse_args()

def main():
    """Main entry point"""
    args = parse_args()
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Initialize the bot with optional RPC URL
    bot = FutarchyBot(rpc_url=args.rpc, verbose=args.verbose)
    
    # Initialize passthrough router for conditional token swaps
    router = PassthroughRouter(
        bot.w3,
        os.environ.get("PRIVATE_KEY"),
        os.environ.get("V3_PASSTHROUGH_ROUTER_ADDRESS")
    )
    
    if args.command == 'debug':
        # Debug mode - check pool configuration and balances
        print("\n🔍 Debug Information:")
        
        # Get token balances
        sdai_balance = bot.get_token_balance(TOKEN_CONFIG["currency"]["address"])
        wagno_balance = bot.get_token_balance(TOKEN_CONFIG["wagno"]["address"])
        print("\n💰 Token Balances:")
        print(f"  sDAI: {bot.w3.from_wei(sdai_balance, 'ether')}")
        print(f"  waGNO: {bot.w3.from_wei(wagno_balance, 'ether')}")
        
        # Check pool configuration
        pool_id = BALANCER_CONFIG["pool_id"]
        print(f"\n🏊 Pool Configuration:")
        print(f"  Pool Address: {BALANCER_CONFIG['pool_address']}")
        print(f"  Pool ID: {pool_id}")
        
        # Get pool tokens and balances
        try:
            tokens, balances, _ = bot.balancer_handler.balancer_vault.functions.getPoolTokens(pool_id).call()
            print("\n📊 Pool Tokens:")
            for i, token in enumerate(tokens):
                print(f"  {i+1}: {token} - Balance: {bot.w3.from_wei(balances[i], 'ether')}")
        except Exception as e:
            print(f"❌ Error getting pool tokens: {e}")
        
        # Check token approvals
        vault_address = BALANCER_CONFIG["vault_address"]
        sdai_allowance = bot.get_token_allowance(TOKEN_CONFIG["currency"]["address"], vault_address)
        wagno_allowance = bot.get_token_allowance(TOKEN_CONFIG["wagno"]["address"], vault_address)
        print("\n✅ Token Approvals for Balancer Vault:")
        print(f"  sDAI: {bot.w3.from_wei(sdai_allowance, 'ether')}")
        print(f"  waGNO: {bot.w3.from_wei(wagno_allowance, 'ether')}")
        
        return
    
    elif args.command in ['balances', 'refresh_balances']:
        balances = bot.get_balances()
        bot.print_balances(balances)
        return
    
    # Check if command needs an amount and if it's provided
    if hasattr(args, 'amount') and not args.amount and args.command not in ['test_swaps']:
        print("❌ Amount is required for this command")
        return
    
    # Run the appropriate command
    if args.command == 'monitor':
        print(f"Running monitoring strategy for {args.iterations} iterations every {args.interval} seconds")
        bot.run_strategy(lambda b: simple_monitoring_strategy(b, args.iterations, args.interval))
    
    elif args.command == 'prices':
        # Show market prices using the bot's print_market_prices method
        prices = bot.get_market_prices()
        if prices:
            bot.print_market_prices(prices)
        return
    
    elif args.command == 'arbitrage':
        print(f"Running arbitrage strategy (min diff: {args.diff}, amount: {args.amount})")
        bot.run_strategy(lambda b: arbitrage_strategy(b, args.diff, args.amount))
    
    elif args.command == 'buy_wrapped_gno':
        # Buy waGNO with sDAI using Balancer BatchRouter
        from futarchy.experimental.exchanges.balancer.swap import BalancerSwapHandler
        try:
            balancer = BalancerSwapHandler(bot)
            result = balancer.swap_sdai_to_wagno(args.amount)
            if result and result.get('success'):
                print("\nTransaction Summary:")
                print(f"Transaction Hash: {result['tx_hash']}")
                print("\nBalance Changes:")
                print(f"sDAI: {result['balance_changes']['token_in']:+.18f}")
                print(f"waGNO: {result['balance_changes']['token_out']:+.18f}")
        except Exception as e:
            print(f"❌ Error during swap: {e}")
            sys.exit(1)
    
    elif args.command == 'buy_gno':
        # Buy waGNO and automatically unwrap it to GNO
        from futarchy.experimental.exchanges.balancer.swap import BalancerSwapHandler
        try:
            print(f"\n🔄 Buying and unwrapping GNO using {args.amount} sDAI...")
            
            # Step 1: Buy waGNO
            balancer = BalancerSwapHandler(bot)
            result = balancer.swap_sdai_to_wagno(args.amount)
            if not result or not result.get('success'):
                print("❌ Failed to buy waGNO")
                sys.exit(1)
                
            wagno_received = result['balance_changes']['token_out']
            print(f"\n✅ Successfully bought {wagno_received:.18f} waGNO")
            
            # Step 2: Unwrap waGNO to GNO
            print(f"\n🔹 Step 2: Unwrapping {wagno_received:.18f} waGNO to GNO...")
            
            # Get GNO balance before unwrapping
            before_balances = bot.get_balances()
            gno_before = float(before_balances['company']['wallet'])
            
            # Try to unwrap waGNO to GNO (but ignore errors)
            try:
                bot.aave_balancer.unwrap_wagno(wagno_received)
            except Exception as e:
                # Ignore errors, we'll check the balance later
                pass
            
            # Check if GNO balance increased after the operation
            after_balances = bot.get_balances()
            gno_after = float(after_balances['company']['wallet'])
            gno_amount = gno_after - gno_before
            
            if gno_amount <= 0:
                print("❌ No GNO received after unwrapping. Aborting arbitrage.")
                return
            
            print(f"✅ Received {gno_amount:.6f} GNO after unwrapping")
                
        except Exception as e:
            print(f"❌ Error during buy_gno operation: {e}")
            sys.exit(1)
    
    elif args.command == 'unwrap_wagno':
        # Use the waGNO token contract to unwrap to GNO
        success = bot.aave_balancer.unwrap_wagno(args.amount)
        if success:
            balances = bot.get_balances()
            bot.print_balances(balances)
    
    elif args.command == 'wrap_gno':
        # Use the waGNO token contract to wrap GNO
        success = bot.aave_balancer.wrap_gno_to_wagno(args.amount)
        if success:
            balances = bot.get_balances()
            bot.print_balances(balances)
    
    elif args.command == 'split_gno':
        # Split GNO into YES/NO tokens using add_collateral
        success = bot.add_collateral('company', args.amount)
        if success:
            balances = bot.get_balances()
            bot.print_balances(balances)
    
    elif args.command == 'swap_gno_yes':
        amount_wei = bot.w3.to_wei(args.amount, 'ether')
        token_in = bot.w3.to_checksum_address(TOKEN_CONFIG["company"]["yes_address"])
        token_out = bot.w3.to_checksum_address(TOKEN_CONFIG["currency"]["yes_address"])
        bot.execute_swap(token_in=token_in, token_out=token_out, amount=amount_wei)
    
    elif args.command == 'swap_gno_no':
        amount_wei = bot.w3.to_wei(args.amount, 'ether')
        token_in = bot.w3.to_checksum_address(TOKEN_CONFIG["company"]["no_address"])
        token_out = bot.w3.to_checksum_address(TOKEN_CONFIG["currency"]["no_address"])
        bot.execute_swap(token_in=token_in, token_out=token_out, amount=amount_wei)
    
    elif args.command == 'merge_sdai':
        # Merge sDAI-YES and sDAI-NO back into sDAI
        success = bot.remove_collateral('currency', args.amount)
        if success:
            balances = bot.get_balances()
            bot.print_balances(balances)
    
    elif args.command == 'buy_sdai_yes':
        buy_sdai_yes(bot, args.amount)
    
    elif args.command == 'swap_gno_yes_to_sdai_yes':
        # In YES pool: GNO is token0, so GNO->SDAI is zero_for_one=true
        # Get the current pool price directly from the pool
        pool_address = router.w3.to_checksum_address(POOL_CONFIG_YES["address"])
        pool_contract = bot.w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
        slot0 = pool_contract.functions.slot0().call()
        current_sqrt_price = slot0[0]
        print(f"Current pool sqrtPriceX96: {current_sqrt_price}")
        
        # For zero_for_one=True (going down in price), use 95% of current price as the limit
        sqrt_price_limit_x96 = int(current_sqrt_price * 0.95)
        print(f"Using price limit of 95% of current price: {sqrt_price_limit_x96}")
        
        # Get the current pool tokens to show the token ordering
        token0 = pool_contract.functions.token0().call()
        token1 = pool_contract.functions.token1().call()
        print(f"Pool token0: {token0}")
        print(f"Pool token1: {token1}")
        print(f"sDAI-YES: {TOKEN_CONFIG['currency']['yes_address']}")
        print(f"sDAI: {TOKEN_CONFIG['currency']['address']}")
        
        # Calculate the actual price from sqrtPriceX96
        price = (current_sqrt_price ** 2) / (2 ** 192)
        print(f"Current price: {price:.6f} (price of token1 in terms of token0)")
        if token0.lower() == TOKEN_CONFIG['currency']['yes_address'].lower():
            print(f"This means 1 sDAI-YES = {price:.6f} sDAI")
        else:
            print(f"This means 1 sDAI = {price:.6f} sDAI-YES")
        
        result = router.execute_swap(
            pool_address=pool_address,
            token_in=TOKEN_CONFIG["company"]["yes_address"],
            token_out=TOKEN_CONFIG["currency"]["yes_address"],
            amount=args.amount,
            zero_for_one=True,
            sqrt_price_limit_x96=sqrt_price_limit_x96
        )
        if not result:
            print("❌ GNO YES to sDAI YES swap failed")
            return
    
    elif args.command == 'swap_sdai_yes_to_gno_yes':
        # In YES pool: GNO is token0, so SDAI->GNO is zero_for_one=false
        # Get the current pool price directly from the pool
        pool_address = router.w3.to_checksum_address(POOL_CONFIG_YES["address"])
        pool_contract = bot.w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
        slot0 = pool_contract.functions.slot0().call()
        current_sqrt_price = slot0[0]
        print(f"Current pool sqrtPriceX96: {current_sqrt_price}")
        
        # For zero_for_one=False (going up in price), use 120% of current price as the limit
        sqrt_price_limit_x96 = int(current_sqrt_price * 1.2)
        print(f"Using price limit of 120% of current price: {sqrt_price_limit_x96}")
        
        result = router.execute_swap(
            pool_address=pool_address,
            token_in=TOKEN_CONFIG["currency"]["yes_address"],
            token_out=TOKEN_CONFIG["company"]["yes_address"],
            amount=args.amount,
            zero_for_one=False,
            sqrt_price_limit_x96=sqrt_price_limit_x96
        )
        if not result:
            print("❌ sDAI YES to GNO YES swap failed")
            return
    
    elif args.command == 'swap_gno_no_to_sdai_no':
        # In NO pool: SDAI is token0, so GNO->SDAI is zero_for_one=false
        # Get the current pool price directly from the pool
        pool_address = router.w3.to_checksum_address(POOL_CONFIG_NO["address"])
        pool_contract = bot.w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
        slot0 = pool_contract.functions.slot0().call()
        current_sqrt_price = slot0[0]
        print(f"Current pool sqrtPriceX96: {current_sqrt_price}")
        
        # For zero_for_one=False (going up in price), use 120% of current price as the limit
        sqrt_price_limit_x96 = int(current_sqrt_price * 1.2)
        print(f"Using price limit of 120% of current price: {sqrt_price_limit_x96}")
        
        result = router.execute_swap(
            pool_address=pool_address,
            token_in=TOKEN_CONFIG["company"]["no_address"],
            token_out=TOKEN_CONFIG["currency"]["no_address"],
            amount=args.amount,
            zero_for_one=False,
            sqrt_price_limit_x96=sqrt_price_limit_x96
        )
        if not result:
            print("❌ GNO NO to sDAI NO swap failed")
            return
    
    elif args.command == 'swap_sdai_no_to_gno_no':
        # In NO pool: SDAI is token0, so SDAI->GNO is zero_for_one=true
        # Get the current pool price directly from the pool
        pool_address = router.w3.to_checksum_address(POOL_CONFIG_NO["address"])
        pool_contract = bot.w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
        slot0 = pool_contract.functions.slot0().call()
        current_sqrt_price = slot0[0]
        print(f"Current pool sqrtPriceX96: {current_sqrt_price}")
        
        # For zero_for_one=True (going down in price), use 80% of current price as the limit
        sqrt_price_limit_x96 = int(current_sqrt_price * 0.8)
        print(f"Using price limit of 80% of current price: {sqrt_price_limit_x96}")
        
        result = router.execute_swap(
            pool_address=pool_address,
            token_in=TOKEN_CONFIG["currency"]["no_address"],
            token_out=TOKEN_CONFIG["company"]["no_address"],
            amount=args.amount,
            zero_for_one=True,
            sqrt_price_limit_x96=sqrt_price_limit_x96
        )
        if not result:
            print("❌ sDAI NO to GNO NO swap failed")
            return
    
    elif args.command == 'test_swaps':
        print("\n🧪 Testing all swap functions with small amounts...")
        test_amount = args.amount if hasattr(args, 'amount') else 0.001
        
        # Set up pool ABIs for price queries
        pool_abi = [{"inputs": [], "name": "slot0", "outputs": [{"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"}, {"internalType": "int24", "name": "tick", "type": "int24"}, {"internalType": "uint16", "name": "observationIndex", "type": "uint16"}, {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"}, {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"}, {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"}, {"internalType": "bool", "name": "unlocked", "type": "bool"}], "stateMutability": "view", "type": "function"}]
        
        # Get YES pool price
        yes_pool_address = router.w3.to_checksum_address(POOL_CONFIG_YES["address"])
        yes_pool_contract = bot.w3.eth.contract(address=yes_pool_address, abi=UNISWAP_V3_POOL_ABI)
        yes_slot0 = yes_pool_contract.functions.slot0().call()
        yes_sqrt_price = yes_slot0[0]
        print(f"YES pool current sqrtPriceX96: {yes_sqrt_price}")
        
        # Get NO pool price
        no_pool_address = router.w3.to_checksum_address(POOL_CONFIG_NO["address"])
        no_pool_contract = bot.w3.eth.contract(address=no_pool_address, abi=UNISWAP_V3_POOL_ABI)
        no_slot0 = no_pool_contract.functions.slot0().call()
        no_sqrt_price = no_slot0[0]
        print(f"NO pool current sqrtPriceX96: {no_sqrt_price}")
        
        # 1. Test GNO YES to SDAI YES
        print("\n\n============================================")
        print(f"🔄 Testing GNO YES to SDAI YES swap with {test_amount} tokens...")
        print("============================================")
        
        # For GNO to SDAI (zero_for_one=True), use 80% of current price
        yes_sqrt_price_limit = int(yes_sqrt_price * 0.8)
        print(f"Using price limit of 80% of current price: {yes_sqrt_price_limit}")
        
        gno_yes_to_sdai_result = router.execute_swap(
            pool_address=yes_pool_address,
            token_in=TOKEN_CONFIG["company"]["yes_address"],
            token_out=TOKEN_CONFIG["currency"]["yes_address"],
            amount=test_amount,
            zero_for_one=True,
            sqrt_price_limit_x96=yes_sqrt_price_limit
        )
        
        # 2. Test SDAI YES to GNO YES
        print("\n\n============================================")
        print(f"🔄 Testing SDAI YES to GNO YES swap with {test_amount} tokens...")
        print("============================================")
        
        # For SDAI to GNO (zero_for_one=False), use 120% of current price
        yes_sqrt_price_limit = int(yes_sqrt_price * 1.2)
        print(f"Using price limit of 120% of current price: {yes_sqrt_price_limit}")
        
        sdai_yes_to_gno_result = router.execute_swap(
            pool_address=yes_pool_address,
            token_in=TOKEN_CONFIG["currency"]["yes_address"],
            token_out=TOKEN_CONFIG["company"]["yes_address"],
            amount=test_amount,
            zero_for_one=False,
            sqrt_price_limit_x96=yes_sqrt_price_limit
        )
        
        # 3. Test GNO NO to SDAI NO
        print("\n\n============================================")
        print(f"🔄 Testing GNO NO to SDAI NO swap with {test_amount} tokens...")
        print("============================================")
        
        # For GNO to SDAI (zero_for_one=False), use 120% of current price
        no_sqrt_price_limit = int(no_sqrt_price * 1.2)
        print(f"Using price limit of 120% of current price: {no_sqrt_price_limit}")
        
        gno_no_to_sdai_result = router.execute_swap(
            pool_address=no_pool_address,
            token_in=TOKEN_CONFIG["company"]["no_address"],
            token_out=TOKEN_CONFIG["currency"]["no_address"],
            amount=test_amount,
            zero_for_one=False,
            sqrt_price_limit_x96=no_sqrt_price_limit
        )
        
        # 4. Test SDAI NO to GNO NO
        print("\n\n============================================")
        print(f"🔄 Testing SDAI NO to GNO NO swap with {test_amount} tokens...")
        print("============================================")
        
        # For SDAI to GNO (zero_for_one=True), use 80% of current price
        no_sqrt_price_limit = int(no_sqrt_price * 0.8)
        print(f"Using price limit of 80% of current price: {no_sqrt_price_limit}")
        
        sdai_no_to_gno_result = router.execute_swap(
            pool_address=no_pool_address,
            token_in=TOKEN_CONFIG["currency"]["no_address"],
            token_out=TOKEN_CONFIG["company"]["no_address"],
            amount=test_amount,
            zero_for_one=True,
            sqrt_price_limit_x96=no_sqrt_price_limit
        )
        
        # Print summary
        print("\n\n============================================")
        print("🧪 Swap Tests Summary")
        print("============================================")
        print(f"GNO YES to SDAI YES: {'✅ Success' if gno_yes_to_sdai_result else '❌ Failed'}")
        print(f"SDAI YES to GNO YES: {'✅ Success' if sdai_yes_to_gno_result else '❌ Failed'}")
        print(f"GNO NO to SDAI NO: {'✅ Success' if gno_no_to_sdai_result else '❌ Failed'}")
        print(f"SDAI NO to GNO NO: {'✅ Success' if sdai_no_to_gno_result else '❌ Failed'}")
        
        # Show final balances
        balances = bot.get_balances()
        bot.print_balances(balances)
    
    elif args.command == 'arbitrage_sell_synthetic_gno':
        # This function executes a full arbitrage operation
        execute_arbitrage_sell_synthetic_gno(bot, args.amount)
    
    elif args.command == 'arbitrage_buy_synthetic_gno':
        # This function executes a full arbitrage operation to buy synthetic GNO
        execute_arbitrage_buy_synthetic_gno(bot, args.amount)
    
    else:
        # Default to showing help
        print("Please specify a command. Use --help for available commands.")
        sys.exit(1)

def execute_arbitrage_sell_synthetic_gno(bot, sdai_amount):
    """
    Execute a full arbitrage operation:
    1. Buy waGNO with sDAI
    2. Unwrap waGNO to GNO
    3. Split GNO into YES/NO tokens
    4. Sell GNO-YES for sDAI-YES
    5. Sell GNO-NO for sDAI-NO
    6. Balance YES/NO tokens:
       - If YES > NO: Sell excess YES for sDAI
       - If NO > YES: Buy additional YES with sDAI
    7. Merge sDAI-YES and sDAI-NO back into sDAI
    8. Compare final sDAI amount with initial amount
    
    Args:
        bot: The FutarchyBot instance
        sdai_amount: Amount of sDAI to use for arbitrage
    """
    print(f"\n🔄 Starting synthetic GNO arbitrage with {sdai_amount} sDAI")
    
    # Get initial balances and prices
    initial_balances = bot.get_balances()
    initial_sdai = float(initial_balances['currency']['wallet'])
    initial_wagno = float(initial_balances['wagno']['wallet'])
    
    if initial_sdai < sdai_amount:
        print(f"❌ Insufficient sDAI balance. Required: {sdai_amount}, Available: {initial_sdai}")
        return
    
    # Get initial market prices for reporting only
    print("\n📊 Initial market prices:")
    market_prices = bot.get_market_prices()
    synthetic_price, spot_price = bot.calculate_synthetic_price()
    
    print(f"GNO Spot Price: {spot_price:.6f} sDAI")
    print(f"GNO Synthetic Price: {synthetic_price:.6f} sDAI")
    print(f"Price Difference: {((synthetic_price / spot_price) - 1) * 100:.2f}%")
    
    # Step 1: Buy waGNO with sDAI
    print(f"\n🔹 Step 1: Buying waGNO with {sdai_amount} sDAI")
    
    # Buy waGNO with sDAI
    balancer = BalancerSwapHandler(bot)
    result = balancer.swap_sdai_to_wagno(sdai_amount)
    
    # Check if the swap succeeded (result should always be returned now)
    if not result or not result.get('success'):
        print("❌ Failed to buy waGNO. Aborting arbitrage.")
        return

    # Get the waGNO amount from the result's balance changes
    # Check if balance changes were calculable
    if 'token_out' not in result.get('balance_changes', {}) or result['balance_changes']['token_out'] == 0:
        # If calculation failed or was zero, get balance manually
        print("⚠️ Could not get waGNO received from swap result, checking balance manually.")
        updated_balances = bot.get_balances()
        current_wagno = float(updated_balances['wagno']['wallet'])
        wagno_received = current_wagno - initial_wagno
    else:
        wagno_received = abs(result['balance_changes']['token_out'])

    if wagno_received <= 0:
        print("❌ No waGNO received. Aborting arbitrage.")
        return
        
    print(f"✅ Successfully bought {wagno_received:.6f} waGNO")
    
    # Step 2: Unwrap waGNO to GNO
    print(f"\n🔹 Step 2: Unwrapping waGNO to GNO")
    
    # Get the current balance after buying waGNO
    current_balances = bot.get_balances()
    total_wagno = float(current_balances['wagno']['wallet'])
    
    print(f"📊 Total waGNO available: {total_wagno:.6f}")
    
    # Get GNO balance before unwrapping
    gno_before = float(current_balances['company']['wallet'])
    
    # Try to unwrap all available waGNO to GNO
    try:
        bot.aave_balancer.unwrap_wagno(total_wagno)
    except Exception as e:
        # Ignore errors, we'll check the balance later
        pass
    
    # Check if GNO balance increased after the operation
    after_balances = bot.get_balances()
    gno_after = float(after_balances['company']['wallet'])
    gno_amount = gno_after - gno_before
    
    if gno_amount <= 0:
        print("❌ No GNO received after unwrapping. Aborting arbitrage.")
        return
    
    print(f"✅ Received {gno_amount:.6f} GNO after unwrapping")
    
    # Step 3: Split GNO into YES/NO tokens
    print(f"\n🔹 Step 3: Splitting GNO into YES/NO tokens")
    
    # Get current GNO balance to split
    current_balances = bot.get_balances()
    total_gno = float(current_balances['company']['wallet'])
    
    print(f"📊 Total GNO available: {total_gno:.6f}")
    
    # Get current YES/NO token balances
    gno_yes_before = float(current_balances['company']['yes'])
    gno_no_before = float(current_balances['company']['no'])
    
    try:
        # Add collateral (split) all available GNO
        success = bot.add_collateral('company', total_gno)
        if not success:
            print("❌ Failed to split GNO. Aborting arbitrage.")
            return
    except Exception as e:
        print(f"❌ Error splitting GNO: {e}")
        return
    
    # Check GNO-YES and GNO-NO balances
    intermediate_balances = bot.get_balances()
    gno_yes_amount = float(intermediate_balances['company']['yes']) - gno_yes_before
    gno_no_amount = float(intermediate_balances['company']['no']) - gno_no_before
    
    # Get total YES/NO token balances for selling
    total_gno_yes = float(intermediate_balances['company']['yes'])
    total_gno_no = float(intermediate_balances['company']['no'])
    
    if gno_yes_amount <= 0 or gno_no_amount <= 0:
        print("❌ Failed to receive both GNO-YES and GNO-NO tokens. Aborting arbitrage.")
        return
    
    print(f"✅ Received {gno_yes_amount:.6f} GNO-YES and {gno_no_amount:.6f} GNO-NO tokens")
    print(f"📊 Total available: {total_gno_yes:.6f} GNO-YES and {total_gno_no:.6f} GNO-NO tokens")
    
    # Step 4: Sell GNO-YES for sDAI-YES
    print(f"\n🔹 Step 4: Selling {total_gno_yes:.6f} GNO-YES for sDAI-YES")
    
    # Get current sDAI-YES balance before swap
    sdai_yes_before = float(intermediate_balances['currency']['yes'])
    
    try:
        # Create a PassthroughRouter instance directly
        passthrough = PassthroughRouter(
            bot.w3,
            os.environ.get("PRIVATE_KEY"),
            os.environ.get("V3_PASSTHROUGH_ROUTER_ADDRESS")
        )
        
        token_in = TOKEN_CONFIG["company"]["yes_address"]  # GNO YES
        token_out = TOKEN_CONFIG["currency"]["yes_address"]  # sDAI YES
        
        # Get the current pool price directly from the pool
        pool_address = bot.w3.to_checksum_address(POOL_CONFIG_YES["address"])
        pool_contract = bot.w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
        slot0 = pool_contract.functions.slot0().call()
        current_sqrt_price = slot0[0]
        
        # For zero_for_one=True (going down in price), use 95% of current price as the limit
        sqrt_price_limit_x96 = int(current_sqrt_price * 0.95)
        
        result = passthrough.execute_swap(
            pool_address=pool_address,
            token_in=token_in,
            token_out=token_out,
            amount=total_gno_yes,
            zero_for_one=True,
            sqrt_price_limit_x96=sqrt_price_limit_x96
        )
        
        print("✅ Successfully sold GNO-YES tokens for sDAI-YES")
    except Exception as e:
        print(f"❌ Error selling GNO-YES: {e}")
        print("⚠️ Continuing with arbitrage despite GNO-YES selling error")
    
    # Step 5: Sell GNO-NO for sDAI-NO
    print(f"\n🔹 Step 5: Selling {total_gno_no:.6f} GNO-NO for sDAI-NO")
    
    # Get current sDAI-NO balance before swap
    sdai_no_before = float(intermediate_balances['currency']['no'])
    
    try:
        # Add a small delay to avoid nonce too low errors
        time.sleep(2)
        
        # Create a PassthroughRouter instance directly
        passthrough = PassthroughRouter(
            bot.w3,
            os.environ.get("PRIVATE_KEY"),
            os.environ.get("V3_PASSTHROUGH_ROUTER_ADDRESS")
        )
        
        token_in = TOKEN_CONFIG["company"]["no_address"]  # GNO NO
        token_out = TOKEN_CONFIG["currency"]["no_address"]  # sDAI NO
        
        # Get the current pool price directly from the pool
        pool_address = bot.w3.to_checksum_address(POOL_CONFIG_NO["address"])
        pool_contract = bot.w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
        slot0 = pool_contract.functions.slot0().call()
        current_sqrt_price = slot0[0]
        
        # For GNO NO -> sDAI NO in NO pool (SDAI is token0), use 120% as the limit
        sqrt_price_limit_x96 = int(current_sqrt_price * 1.2)
        
        result = passthrough.execute_swap(
            pool_address=pool_address,
            token_in=token_in,
            token_out=token_out,
            amount=sdai_no_before,
            zero_for_one=False,  # GNO NO -> sDAI NO is swapping token0 for token1
            sqrt_price_limit_x96=sqrt_price_limit_x96
        )
        
        print("✅ Successfully sold GNO-NO tokens for sDAI-NO")
    except Exception as e:
        print(f"❌ Error selling GNO-NO: {e}")
        print("⚠️ Continuing with arbitrage despite GNO-NO selling error")
    
    # Step 6: Balance YES/NO tokens before merging
    # Get latest balances after swaps
    post_swap_balances = bot.get_balances()
    sdai_yes_after = float(post_swap_balances['currency']['yes'])
    sdai_no_after = float(post_swap_balances['currency']['no'])
    sdai_balance = float(post_swap_balances['currency']['wallet'])
    
    # Calculate how much was received
    sdai_yes_received = sdai_yes_after - sdai_yes_before
    sdai_no_received = sdai_no_after - sdai_no_before
    
    print(f"\n📊 sDAI-YES received: {sdai_yes_received:.6f}")
    print(f"📊 sDAI-NO received: {sdai_no_received:.6f}")
    
    print(f"\n🔹 Step 6: Balancing YES/NO tokens before merging")
    print(f"Current sDAI-YES: {sdai_yes_after:.6f}")
    print(f"Current sDAI-NO: {sdai_no_after:.6f}")
    
    # Check which token we have more of
    if sdai_yes_after > sdai_no_after:
        # We have more YES than NO, sell the difference
        difference = sdai_yes_after - sdai_no_after
        print(f"We have {difference:.6f} more sDAI-YES than sDAI-NO")
        print(f"Selling excess sDAI-YES for sDAI...")
        
        try:
            sell_sdai_yes(bot, difference)
            
            # Update balances after selling
            balance_balances = bot.get_balances()
            sdai_yes_after = float(balance_balances['currency']['yes'])
            sdai_no_after = float(balance_balances['currency']['no'])
            
            print(f"After balancing: sDAI-YES: {sdai_yes_after:.6f}, sDAI-NO: {sdai_no_after:.6f}")
        except Exception as e:
            print(f"❌ Error selling excess sDAI-YES: {e}")
            print("⚠️ Continuing with unbalanced tokens")
    
    elif sdai_no_after > sdai_yes_after:
        # We have more NO than YES, buy some YES with sDAI
        difference = sdai_no_after - sdai_yes_after
        print(f"We have {difference:.6f} more sDAI-NO than sDAI-YES")
        
        # Check if we have enough sDAI to buy the difference
        if sdai_balance >= difference:
            print(f"Buying {difference:.6f} sDAI-YES with sDAI...")
            
            try:
                buy_sdai_yes(bot, difference)
                
                # Update balances after buying
                balance_balances = bot.get_balances()
                sdai_yes_after = float(balance_balances['currency']['yes'])
                sdai_no_after = float(balance_balances['currency']['no'])
                
                print(f"After balancing: sDAI-YES: {sdai_yes_after:.6f}, sDAI-NO: {sdai_no_after:.6f}")
            except Exception as e:
                print(f"❌ Error buying sDAI-YES: {e}")
                print("⚠️ Continuing with unbalanced tokens")
        else:
            print(f"⚠️ Not enough sDAI ({sdai_balance:.6f}) to buy {difference:.6f} sDAI-YES")
            print("⚠️ Continuing with unbalanced tokens")
    
    else:
        print(f"Tokens are already balanced: {sdai_yes_after:.6f} sDAI-YES = {sdai_no_after:.6f} sDAI-NO")
    
    
    # Step 7: Merge sDAI-YES and sDAI-NO tokens into sDAI
    # Recalculate merge amount after balancing
    post_balance_balances = bot.get_balances()
    sdai_yes_final = float(post_balance_balances['currency']['yes'])
    sdai_no_final = float(post_balance_balances['currency']['no'])
    
    # Calculate amount to merge (min of YES and NO to form pairs)
    merge_amount = min(sdai_yes_final, sdai_no_final)
    
    print(f"\n🔹 Step 7: Merging {merge_amount:.6f} pairs of sDAI-YES and sDAI-NO tokens into sDAI")
    
    if merge_amount > 0:
        try:
            # Using remove_collateral which is the existing implementation for merge
            success = bot.remove_collateral('currency', merge_amount)
            if success:
                print(f"✅ Successfully merged {merge_amount:.6f} pairs of YES/NO tokens into sDAI")
            else:
                print("⚠️ Failed to merge sDAI tokens. Continuing to final evaluation.")
        except Exception as e:
            print(f"❌ Error merging sDAI tokens: {e}")
            print("⚠️ Continuing to final evaluation despite merging error")
    else:
        print("\n🔹 Step 7: No tokens to merge (requires equal YES and NO amounts)")
    
    # Get final balances and calculate profit/loss
    final_balances = bot.get_balances()
    final_sdai = float(final_balances['currency']['wallet'])
    sdai_yes_final = float(final_balances['currency']['yes'])
    sdai_no_final = float(final_balances['currency']['no'])
    
    # Calculate remaining value locked in YES/NO tokens
    # This is a rough estimate using the current market probability
    market_prices_final = bot.get_market_prices()
    probability = market_prices_final.get('probability', 0.5)
    
    estimated_value_of_yes = sdai_yes_final * probability
    estimated_value_of_no = sdai_no_final * (1 - probability)
    
    # Total value = direct sDAI + estimated value of YES/NO tokens
    total_estimated_value = final_sdai + estimated_value_of_yes + estimated_value_of_no
    
    # Calculate profit/loss
    profit_loss = final_sdai - initial_sdai
    profit_loss_percent = (profit_loss / initial_sdai) * 100 if initial_sdai > 0 else 0
    
    total_profit_loss = total_estimated_value - initial_sdai
    total_profit_loss_percent = (total_profit_loss / initial_sdai) * 100 if initial_sdai > 0 else 0
    
    # Get updated market prices for reporting only
    synthetic_price_final, spot_price_final = bot.calculate_synthetic_price()
    
    # Print summary
    print("\n📈 Arbitrage Operation Summary")
    print("=" * 40)
    print(f"Initial sDAI: {initial_sdai:.6f}")
    print(f"Final sDAI: {final_sdai:.6f}")
    print(f"Direct Profit/Loss: {profit_loss:.6f} sDAI ({profit_loss_percent:.2f}%)")
    
    if remaining_tokens_value > 0:
        print(f"\nRemaining tokens:")
        if gno_yes_final > 0:
            print(f"- GNO-YES: {gno_yes_final:.6f} (est. value: {estimated_value_of_yes:.6f} sDAI)")
        if gno_no_final > 0:
            print(f"- GNO-NO: {gno_no_final:.6f} (est. value: {estimated_value_of_no:.6f} sDAI)")
        
        print(f"Total estimated value of remaining tokens: {remaining_tokens_value:.6f} sDAI")
        print(f"Total estimated value: {total_estimated_value:.6f} sDAI")
        print(f"Total estimated profit/loss: {total_profit_loss:.6f} sDAI ({total_profit_loss_percent:.2f}%)")
    
    print("\nMarket Prices:")
    print(f"Initial GNO Spot: {spot_price:.6f} → Final: {spot_price_final:.6f}")
    print(f"Initial GNO Synthetic: {synthetic_price:.6f} → Final: {synthetic_price_final:.6f}")
    print(f"Initial Price Gap: {((synthetic_price / spot_price) - 1) * 100:.2f}% → Final: {((synthetic_price_final / spot_price_final) - 1) * 100:.2f}%")
    
    if profit_loss > 0:
        print("\n✅ Arbitrage was profitable!")
    else:
        print("\n⚠️ Arbitrage was not profitable. Consider market conditions and gas costs.")

def execute_arbitrage_buy_synthetic_gno(bot, sdai_amount):
    """
    Execute a full arbitrage operation to buy synthetic GNO:
    1. Check market prices (YES pool, NO pool, and probability)
    2. Calculate optimal amounts of sDAI-YES and sDAI-NO (x,y) needed
    3. Balance sDAI-YES and sDAI-NO amounts
       - If x>y: Use (x-y)*probability of sDAI to buy sDAI-YES directly
    4. Use y sDAI to split into sDAI-YES and sDAI-NO tokens
    5. If x<y: Sell excess sDAI-YES back to sDAI
    6. Buy GNO-YES with all sDAI-YES
    7. Buy GNO-NO with all sDAI-NO
    8. Merge GNO-YES and GNO-NO back into GNO
    9. Wrap GNO into waGNO
    10. Sell waGNO for sDAI
    11. Compare final sDAI with initial amount
    
    Args:
        bot: The FutarchyBot instance
        sdai_amount: Amount of sDAI to use for arbitrage
    """
    print(f"\n🔄 Starting synthetic GNO buying arbitrage with {sdai_amount} sDAI")
    
    # Import needed modules
    import time
    from exchanges.passthrough_router import PassthroughRouter
    from config.constants import TOKEN_CONFIG, POOL_CONFIG_YES, POOL_CONFIG_NO, UNISWAP_V3_POOL_ABI
    import os
    
    # Get initial balances and prices
    initial_balances = bot.get_balances()
    initial_sdai = float(initial_balances['currency']['wallet'])
    
    if initial_sdai < sdai_amount:
        print(f"❌ Insufficient sDAI balance. Required: {sdai_amount}, Available: {initial_sdai}")
        return
    
    # Step 1: Get market prices (YES pool, NO pool, probability)
    print("\n🔹 Step 1: Getting market prices and calculating optimal amounts")
    
    # Get market prices
    market_prices = bot.get_market_prices()
    
    # Extract relevant values
    yes_price = market_prices['yes_price']
    no_price = market_prices['no_price']
    probability = market_prices['probability']
    synthetic_price, spot_price = bot.calculate_synthetic_price()
    
    print(f"YES Price: {yes_price:.6f} sDAI")
    print(f"NO Price: {no_price:.6f} sDAI")
    print(f"Probability: {probability:.6f}")
    print(f"GNO Spot Price: {spot_price:.6f} sDAI")
    print(f"GNO Synthetic Price: {synthetic_price:.6f} sDAI")
    print(f"Price Difference: {((synthetic_price / spot_price) - 1) * 100:.2f}%")
    
    # Step 2: Calculate optimal amounts of sDAI-YES and sDAI-NO (x, y)
    print("\n🔹 Step 2: Calculating optimal amounts of sDAI-YES and sDAI-NO")
    
    # From the equations:
    # x/y = (yes_price) / (no_price)
    # x * probability + y * (1 - probability) = amount
    
    # Calculate denominator
    denominator = (yes_price * probability) / no_price + (1 - probability)
    
    # Calculate y first
    y = sdai_amount / denominator
    
    # Then calculate x
    x = y * (yes_price / no_price)
    
    print(f"Optimal amounts:")
    print(f"sDAI-YES (x): {x:.6f}")
    print(f"sDAI-NO (y): {y:.6f}")
    
    # Step 3: Balance sDAI-YES and sDAI-NO amounts
    print(f"\n🔹 Step 3: Balancing sDAI-YES and sDAI-NO amounts")
    
    # If x > y, we need more YES tokens than would be acquired from just splitting
    if x > y:
        # Calculate how much sDAI we need to buy directly as sDAI-YES
        direct_yes_amount = (x - y) * probability
        print(f"We need more sDAI-YES. Buying {direct_yes_amount:.6f} sDAI worth of sDAI-YES directly")
        
        # Buy sDAI-YES directly using the existing buy_sdai_yes function
        try:
            buy_sdai_yes(bot, direct_yes_amount)
            
            # Get updated balances
            current_balances = bot.get_balances()
            sdai_yes_current = float(current_balances['currency']['yes'])
            
            print(f"Current sDAI-YES after direct purchase: {sdai_yes_current:.6f}")
        except Exception as e:
            print(f"❌ Error buying sDAI-YES directly: {e}")
            print("⚠️ Continuing with arbitrage despite direct purchase error")
    else:
        print(f"No direct sDAI-YES purchase needed (x <= y)")
    
    # Step 4: Use y sDAI to split into sDAI-YES and sDAI-NO tokens
    print(f"\n🔹 Step 4: Splitting {y:.6f} sDAI into YES/NO tokens")
    
    # Add sDAI as collateral (split into YES/NO tokens)
    try:
        success = bot.add_collateral('currency', y)
        if not success:
            print("❌ Failed to split sDAI. Aborting arbitrage.")
            return
    except Exception as e:
        print(f"❌ Error splitting sDAI: {e}")
        return
    
    # Get updated balances after splitting
    post_split_balances = bot.get_balances()
    sdai_yes_after_split = float(post_split_balances['currency']['yes'])
    sdai_no_after_split = float(post_split_balances['currency']['no'])
    
    print(f"After splitting:")
    print(f"sDAI-YES: {sdai_yes_after_split:.6f}")
    print(f"sDAI-NO: {sdai_no_after_split:.6f}")
    
    # Step 5: If x < y, sell excess sDAI-YES back to sDAI
    if x < y:
        print(f"\n🔹 Step 5: Selling excess sDAI-YES back to sDAI")
        
        # Calculate excess sDAI-YES to sell
        excess_yes = y - x
        print(f"We have {excess_yes:.6f} more sDAI-YES than needed")
        
        try:
            # Sell the excess using the existing sell_sdai_yes function
            sell_sdai_yes(bot, excess_yes)
            
            # Get updated balances
            current_balances = bot.get_balances()
            sdai_yes_current = float(current_balances['currency']['yes'])
            
            print(f"Current sDAI-YES after selling excess: {sdai_yes_current:.6f}")
        except Exception as e:
            print(f"❌ Error selling excess sDAI-YES: {e}")
            print("⚠️ Continuing with arbitrage despite selling error")
    else:
        print(f"\n🔹 Step 5: No excess sDAI-YES to sell (x >= y)")
    
    # Get current balances before swapping
    pre_swap_balances = bot.get_balances()
    sdai_yes_available = float(pre_swap_balances['currency']['yes'])
    sdai_no_available = float(pre_swap_balances['currency']['no'])
    
    # Step 6: Buy GNO-YES with all sDAI-YES
    print(f"\n🔹 Step 6: Buying GNO-YES with {sdai_yes_available:.6f} sDAI-YES")
    
    try:
        # Create a PassthroughRouter instance directly
        passthrough = PassthroughRouter(
            bot.w3,
            os.environ.get("PRIVATE_KEY"),
            os.environ.get("V3_PASSTHROUGH_ROUTER_ADDRESS")
        )
        
        token_in = TOKEN_CONFIG["currency"]["yes_address"]  # sDAI YES
        token_out = TOKEN_CONFIG["company"]["yes_address"]  # GNO YES
        
        # Get the current pool price directly from the pool
        pool_address = bot.w3.to_checksum_address(POOL_CONFIG_YES["address"])
        pool_contract = bot.w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
        slot0 = pool_contract.functions.slot0().call()
        current_sqrt_price = slot0[0]
        
        # For zero_for_one=False (going up in price), use 120% of current price as the limit
        sqrt_price_limit_x96 = int(current_sqrt_price * 1.2)
        
        result = passthrough.execute_swap(
            pool_address=pool_address,
            token_in=token_in,
            token_out=token_out,
            amount=sdai_yes_available,
            zero_for_one=False,  # sDAI-YES -> GNO-YES is swapping token0 for token1
            sqrt_price_limit_x96=sqrt_price_limit_x96
        )
        
        print("✅ Successfully bought GNO-YES tokens with sDAI-YES")
    except Exception as e:
        print(f"❌ Error buying GNO-YES: {e}")
        print("⚠️ Continuing with arbitrage despite GNO-YES buying error")
    
    # Step 7: Buy GNO-NO with all sDAI-NO
    print(f"\n🔹 Step 7: Buying GNO-NO with {sdai_no_available:.6f} sDAI-NO")
    
    try:
        # Add a small delay to avoid nonce too low errors
        time.sleep(2)
        
        # Create a PassthroughRouter instance directly
        passthrough = PassthroughRouter(
            bot.w3,
            os.environ.get("PRIVATE_KEY"),
            os.environ.get("V3_PASSTHROUGH_ROUTER_ADDRESS")
        )
        
        token_in = TOKEN_CONFIG["currency"]["no_address"]  # sDAI NO
        token_out = TOKEN_CONFIG["company"]["no_address"]  # GNO NO
        
        # Get the current pool price directly from the pool
        pool_address = bot.w3.to_checksum_address(POOL_CONFIG_NO["address"])
        pool_contract = bot.w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
        slot0 = pool_contract.functions.slot0().call()
        current_sqrt_price = slot0[0]
        
        # For sDAI NO -> GNO NO in NO pool (SDAI is token0), use 80% as the limit
        sqrt_price_limit_x96 = int(current_sqrt_price * 0.8)
        
        result = passthrough.execute_swap(
            pool_address=pool_address,
            token_in=token_in,
            token_out=token_out,
            amount=sdai_no_available,
            zero_for_one=True,  # sDAI NO -> GNO NO is swapping token0 for token1
            sqrt_price_limit_x96=sqrt_price_limit_x96
        )
        
        print("✅ Successfully bought GNO-NO tokens with sDAI-NO")
    except Exception as e:
        print(f"❌ Error buying GNO-NO: {e}")
        print("⚠️ Continuing with arbitrage despite GNO-NO buying error")
    
    # Get balances after buying GNO tokens
    post_buy_balances = bot.get_balances()
    gno_yes_amount = float(post_buy_balances['company']['yes'])
    gno_no_amount = float(post_buy_balances['company']['no'])
    
    print(f"GNO-YES received: {gno_yes_amount:.6f}")
    print(f"GNO-NO received: {gno_no_amount:.6f}")
    
    # Step 8: Merge GNO-YES and GNO-NO back into GNO
    print(f"\n🔹 Step 8: Merging GNO-YES and GNO-NO back into GNO")
    
    # Calculate how much we can merge (minimum of YES and NO)
    merge_amount = min(gno_yes_amount, gno_no_amount)
    
    if merge_amount > 0:
        try:
            # Using remove_collateral which is the existing implementation for merge
            success = bot.remove_collateral('company', merge_amount)
            if success:
                print(f"✅ Successfully merged {merge_amount:.6f} pairs of YES/NO tokens into GNO")
            else:
                print("⚠️ Failed to merge GNO tokens. Continuing to next step.")
        except Exception as e:
            print(f"❌ Error merging GNO tokens: {e}")
            print("⚠️ Continuing to next step despite merging error")
    else:
        print("🔹 No GNO tokens to merge (requires equal YES and NO amounts)")
    
    # Get balances after merging
    post_merge_balances = bot.get_balances()
    gno_amount = float(post_merge_balances['company']['wallet'])
    
    print(f"GNO balance after merging: {gno_amount:.6f}")
    
    # Step 9: Wrap GNO into waGNO
    print(f"\n🔹 Step 9: Wrapping GNO into waGNO")
    
    try:
        # Using the existing aave_balancer.wrap_gno_to_wagno method
        bot.aave_balancer.wrap_gno_to_wagno(gno_amount)
        print(f"✅ Successfully wrapped {gno_amount:.6f} GNO into waGNO")
    except Exception as e:
        print(f"❌ Error wrapping GNO to waGNO: {e}")
        print("⚠️ Continuing to final step despite wrapping error")
    
    # Get waGNO balance after wrapping
    post_wrap_balances = bot.get_balances()
    wagno_amount = float(post_wrap_balances['wagno']['wallet'])
    
    print(f"waGNO balance after wrapping: {wagno_amount:.6f}")
    
    # Step 10: Sell waGNO for sDAI
    print(f"\n🔹 Step 10: Selling waGNO for sDAI")
    
    if wagno_amount > 0:
        try:
            # Using the existing balancer swap handler
            # from exchanges.balancer.swap import BalancerSwapHandler # No longer needed here
            balancer = BalancerSwapHandler(bot)
            result = balancer.swap_wagno_to_sdai(wagno_amount)
            
            if result and result.get('success'):
                print(f"✅ Successfully sold waGNO for sDAI")
            else:
                print("⚠️ Failed to sell waGNO for sDAI.")
        except Exception as e:
            print(f"❌ Error selling waGNO to sDAI: {e}")
    else:
        print("🔹 No waGNO to sell")
    
    # Get final balances and calculate profit/loss
    final_balances = bot.get_balances()
    final_sdai = float(final_balances['currency']['wallet'])
    
    # Calculate remaining value in YES/NO tokens
    gno_yes_final = float(final_balances['company']['yes'])
    gno_no_final = float(final_balances['company']['no'])
    sdai_yes_final = float(final_balances['currency']['yes'])
    sdai_no_final = float(final_balances['currency']['no'])
    
    # This is a rough estimate using the current market probability
    market_prices_final = bot.get_market_prices()
    final_probability = market_prices_final.get('probability', 0.5)
    
    # Estimate the value of remaining tokens
    estimated_value_of_gno_yes = gno_yes_final * market_prices_final['yes_price'] * final_probability
    estimated_value_of_gno_no = gno_no_final * market_prices_final['no_price'] * (1 - final_probability)
    estimated_value_of_sdai_yes = sdai_yes_final * final_probability
    estimated_value_of_sdai_no = sdai_no_final * (1 - final_probability)
    
    remaining_tokens_value = (
        estimated_value_of_gno_yes + 
        estimated_value_of_gno_no + 
        estimated_value_of_sdai_yes + 
        estimated_value_of_sdai_no
    )
    
    # Total value = direct sDAI + estimated value of remaining tokens
    total_estimated_value = final_sdai + remaining_tokens_value
    
    # Calculate profit/loss
    profit_loss = final_sdai - initial_sdai
    profit_loss_percent = (profit_loss / initial_sdai) * 100 if initial_sdai > 0 else 0
    
    total_profit_loss = total_estimated_value - initial_sdai
    total_profit_loss_percent = (total_profit_loss / initial_sdai) * 100 if initial_sdai > 0 else 0
    
    # Get updated market prices for reporting only
    synthetic_price_final, spot_price_final = bot.calculate_synthetic_price()
    
    # Print summary
    print("\n📈 Arbitrage Operation Summary")
    print("=" * 40)
    print(f"Initial sDAI: {initial_sdai:.6f}")
    print(f"Final sDAI: {final_sdai:.6f}")
    print(f"Direct Profit/Loss: {profit_loss:.6f} sDAI ({profit_loss_percent:.2f}%)")
    
    if remaining_tokens_value > 0:
        print(f"\nRemaining tokens:")
        if gno_yes_final > 0:
            print(f"- GNO-YES: {gno_yes_final:.6f} (est. value: {estimated_value_of_gno_yes:.6f} sDAI)")
        if gno_no_final > 0:
            print(f"- GNO-NO: {gno_no_final:.6f} (est. value: {estimated_value_of_gno_no:.6f} sDAI)")
        
        print(f"Total estimated value of remaining tokens: {remaining_tokens_value:.6f} sDAI")
        print(f"Total estimated value: {total_estimated_value:.6f} sDAI")
        print(f"Total estimated profit/loss: {total_profit_loss:.6f} sDAI ({total_profit_loss_percent:.2f}%)")
    
    print("\nMarket Prices:")
    print(f"Initial GNO Spot: {spot_price:.6f} → Final: {spot_price_final:.6f}")
    print(f"Initial GNO Synthetic: {synthetic_price:.6f} → Final: {synthetic_price_final:.6f}")
    print(f"Initial Price Gap: {((synthetic_price / spot_price) - 1) * 100:.2f}% → Final: {((synthetic_price_final / spot_price_final) - 1) * 100:.2f}%")
    
    if profit_loss > 0:
        print("\n✅ Arbitrage was profitable!")
    else:
        print("\n⚠️ Arbitrage was not profitable. Consider market conditions and gas costs.")

if __name__ == "__main__":
    main()
