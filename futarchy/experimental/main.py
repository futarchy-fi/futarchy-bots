#!/usr/bin/env python3
"""
Futarchy Trading Bot - Main entry point (Refactored)

This module is currently in EXPERIMENTAL status.
Please use with caution as functionality may change.
"""

import sys
import os
import argparse
import traceback # Added traceback import here
from decimal import Decimal
import time
import json
from web3 import Web3
from dotenv import load_dotenv
# from futarchy.experimental.exchanges.sushiswap import SushiSwapExchange # Might be unused now
# from futarchy.experimental.exchanges.passthrough_router import PassthroughRouter # Now used internally by SwapManager

# --- Core and Strategy Imports ---
# Add the project root to the path if necessary, or adjust imports based on your structure
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))) # This might be needed depending on run context
try:
    from futarchy.experimental.core.futarchy_bot import FutarchyBot
    from futarchy.experimental.strategies.monitoring import simple_monitoring_strategy
    from futarchy.experimental.strategies.probability import probability_threshold_strategy
    from futarchy.experimental.strategies.arbitrage import arbitrage_strategy
except ImportError:
    # Attempt import assuming script is run from project root
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    from futarchy.experimental.core.futarchy_bot import FutarchyBot
    from futarchy.experimental.strategies.monitoring import simple_monitoring_strategy
    from futarchy.experimental.strategies.probability import probability_threshold_strategy
    from futarchy.experimental.strategies.arbitrage import arbitrage_strategy


# --- Manager Imports ---
from futarchy.experimental.managers import (
    SwapManager,
    ConditionalTokenManager,
    GnoWrapper
)

# --- Configuration Imports ---
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
    ERC20_ABI,
    MIN_SQRT_RATIO,
    MAX_SQRT_RATIO
)
from eth_account import Account
from eth_account.signers.local import LocalAccount
import math

# Comment out direct action imports if logic is fully moved to managers
# from futarchy.experimental.actions.conditional_token_actions import sell_sdai_yes, buy_sdai_yes
# from futarchy.experimental.exchanges.balancer.swap import BalancerSwapHandler # Now used internally by SwapManager

# --- Argument Parsing (Keep as is) ---
def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Futarchy Trading Bot (Refactored)')
    
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
    # Remove strategy-specific args if prices command only shows prices
    # prob_parser.add_argument('--buy', type=float, default=0.7, help='Buy threshold')
    # prob_parser.add_argument('--sell', type=float, default=0.3, help='Sell threshold')
    # prob_parser.add_argument('--amount', type=float, default=0.1, help='Trade amount')

    # Arbitrage strategy mode
    arb_parser = subparsers.add_parser('arbitrage', help='Run arbitrage strategy')
    arb_parser.add_argument('--diff', type=float, default=0.02, help='Minimum price difference')
    arb_parser.add_argument('--amount', type=float, default=0.1, help='Trade amount')

    # Balance commands
    balances_parser = subparsers.add_parser('balances', help='Show token balances')
    refresh_balances_parser = subparsers.add_parser('refresh_balances', help='Refresh and show token balances')

    # Buy/Wrap/Unwrap GNO commands
    buy_wrapped_gno_parser = subparsers.add_parser('buy_wrapped_gno', help='Buy waGNO with sDAI on Balancer')
    buy_wrapped_gno_parser.add_argument('amount', type=float, help='Amount of sDAI to spend')

    buy_gno_parser = subparsers.add_parser('buy_gno', help='Buy GNO with sDAI (buys waGNO and unwraps it)')
    buy_gno_parser.add_argument('amount', type=float, help='Amount of sDAI to spend')

    wrap_gno_parser = subparsers.add_parser('wrap_gno', help='Wrap GNO to waGNO')
    wrap_gno_parser.add_argument('amount', type=float, help='Amount of GNO to wrap')

    unwrap_wagno_parser = subparsers.add_parser('unwrap_wagno', help='Unwrap waGNO to GNO')
    unwrap_wagno_parser.add_argument('amount', type=float, help='Amount of waGNO to unwrap')

    # Conditional Token Commands
    split_gno_parser = subparsers.add_parser('split_gno', help='Split GNO into GNO-YES/NO tokens')
    split_gno_parser.add_argument('amount', type=float, help='Amount of GNO to split')

    split_sdai_parser = subparsers.add_parser('split_sdai', help='Split sDAI into sDAI-YES/NO tokens')
    split_sdai_parser.add_argument('amount', type=float, help='Amount of sDAI to split')

    merge_gno_parser = subparsers.add_parser('merge_gno', help='Merge GNO-YES/NO pairs back into GNO')
    merge_gno_parser.add_argument('amount', type=float, help='Amount of GNO-YES/NO pairs to merge')

    merge_sdai_parser = subparsers.add_parser('merge_sdai', help='Merge sDAI-YES/NO pairs back into sDAI')
    merge_sdai_parser.add_argument('amount', type=float, help='Amount of sDAI-YES/NO pairs to merge')

    # --- Conditional Swap Commands ---
    swap_gno_yes_to_sdai_yes_parser = subparsers.add_parser('swap_gno_yes_to_sdai_yes', help='Swap GNO YES to sDAI YES')
    swap_gno_yes_to_sdai_yes_parser.add_argument('amount', type=float, help='Amount of GNO YES to swap')

    swap_sdai_yes_to_gno_yes_parser = subparsers.add_parser('swap_sdai_yes_to_gno_yes', help='Swap sDAI YES to GNO YES')
    swap_sdai_yes_to_gno_yes_parser.add_argument('amount', type=float, help='Amount of sDAI YES to swap')

    swap_gno_no_to_sdai_no_parser = subparsers.add_parser('swap_gno_no_to_sdai_no', help='Swap GNO NO to sDAI NO')
    swap_gno_no_to_sdai_no_parser.add_argument('amount', type=float, help='Amount of GNO NO to swap')

    swap_sdai_no_to_gno_no_parser = subparsers.add_parser('swap_sdai_no_to_gno_no', help='Swap sDAI NO to GNO NO')
    swap_sdai_no_to_gno_no_parser.add_argument('amount', type=float, help='Amount of sDAI NO to swap')

    buy_sdai_yes_parser = subparsers.add_parser('buy_sdai_yes', help='Buy sDAI-YES tokens with sDAI using the dedicated sDAI/sDAI-YES pool')
    buy_sdai_yes_parser.add_argument('amount', type=float, help='Amount of sDAI to spend')

    sell_sdai_yes_parser = subparsers.add_parser('sell_sdai_yes', help='Sell sDAI-YES tokens for sDAI using the dedicated sDAI/sDAI-YES pool')
    sell_sdai_yes_parser.add_argument('amount', type=float, help='Amount of sDAI-YES to sell')

    # --- Arbitrage Commands ---
    arbitrage_sell_synthetic_gno_parser = subparsers.add_parser('arbitrage_sell_synthetic_gno',
                                       help='Execute full arbitrage: buy GNO spot -> split -> sell YES/NO -> balance & merge')
    arbitrage_sell_synthetic_gno_parser.add_argument('amount', type=float, help='Amount of sDAI to use for arbitrage')

    arbitrage_buy_synthetic_gno_parser = subparsers.add_parser('arbitrage_buy_synthetic_gno',
                                       help='Execute full arbitrage: buy sDAI-YES/NO -> buy GNO-YES/NO -> merge -> wrap -> sell')
    arbitrage_buy_synthetic_gno_parser.add_argument('amount', type=float, help='Amount of sDAI to use for arbitrage')

    # Debug and Test commands
    debug_parser = subparsers.add_parser('debug', help='Run in debug mode with additional output')
    test_swaps_parser = subparsers.add_parser('test_swaps', help='Test all swap functions with small amounts')
    test_swaps_parser.add_argument('--amount', type=float, default=0.001, help='Amount to use for testing (default: 0.001)')
    
    return parser.parse_args()

# --- Main Function ---
def main():
    """Main entry point"""
    args = parse_args()

    # Load environment variables from .env file
    load_dotenv()
    
    # --- Initialization ---
    try:
        bot = FutarchyBot(rpc_url=args.rpc, verbose=args.verbose)
        swap_manager = SwapManager(bot)
        token_manager = ConditionalTokenManager(bot)
        gno_wrapper = GnoWrapper(bot)
    except ConnectionError as e:
        print(f"\u274c Connection Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\u274c Initialization Error: {e}")
        traceback.print_exc()
        sys.exit(1)

    # --- Command Handling ---
    try:
        if args.command == 'debug':
            # Debug mode - check pool configuration and balances
            print("\n\U0001f50d Debug Information:")
            try:
                balances = bot.get_balances()
                bot.print_balances(balances)
            except Exception as e:
                print(f"\u274c Error getting balances: {e}")

            try:
                prices = bot.get_market_prices()
                bot.print_market_prices(prices)
            except Exception as e:
                print(f"\u274c Error getting prices: {e}")
            return

        elif args.command in ['balances', 'refresh_balances']:
            balances = bot.get_balances()
            bot.print_balances(balances)
            return

        # Check if command needs an amount and if it's provided
        if hasattr(args, 'amount') and not args.amount and args.command not in ['test_swaps', 'prices', 'monitor', 'arbitrage', 'debug', 'balances', 'refresh_balances', 'interactive']: # Added checks to avoid error on commands without amount
            print("❌ Amount is required for this command")
            return


        # --- Run Commands ---
        if args.command == 'monitor':
            print(f"Running monitoring strategy for {args.iterations} iterations every {args.interval} seconds")
            bot.run_strategy(lambda b: simple_monitoring_strategy(b, args.iterations, args.interval))

        elif args.command == 'prices':
            prices = bot.get_market_prices()
            if prices:
                bot.print_market_prices(prices)
            return

        elif args.command == 'arbitrage':
            # Placeholder - the specific arbitrage commands handle execution
             if not hasattr(args, 'amount') or not args.amount:
                 print("❌ Amount is required for the arbitrage command")
                 return
             print(f"Running arbitrage strategy (min diff: {args.diff}, amount: {args.amount})")
             bot.run_strategy(lambda b: arbitrage_strategy(b, args.diff, args.amount))

        # --- Balancer/Wrap/Unwrap ---
        elif args.command == 'buy_wrapped_gno':
            result = swap_manager.swap_balancer('sDAI', 'waGNO', args.amount)
            if result and result.get('success'):
                print(f"\n\u2705 Successfully bought waGNO. Tx: {result['tx_hash']}")
            else:
                print(f"\n\u274c Failed to buy waGNO.")

        elif args.command == 'buy_gno':
            print(f"\n\U0001f504 Buying and unwrapping GNO using {args.amount} sDAI...")
            # Step 1: Buy waGNO
            buy_result = swap_manager.swap_balancer('sDAI', 'waGNO', args.amount)
            if not buy_result or not buy_result.get('success'):
                print("\u274c Failed to buy waGNO")
                sys.exit(1)

            wagno_received_change = abs(buy_result.get('balance_changes', {}).get('token_out', 0))
            print(f"   Reported waGNO received from swap: {wagno_received_change:.18f}")

            # Better approach: Check balance *after* the swap
            print("   Checking waGNO balance after swap...")
            balances_after_buy = bot.get_balances() # Fetch balances immediately after swap
            wagno_balance_after = float(balances_after_buy['wagno']['wallet'])
            # Assuming the bot starts with 0 waGNO, this might need adjustment
            # Or track initial waGNO balance if needed for accuracy
            wagno_received = wagno_balance_after # More reliable if starting from 0 or known state

            if wagno_received <= 0:
                 print("⚠️ Could not determine waGNO received accurately, attempting unwrap with reported amount...")
                 wagno_received = wagno_received_change # Fallback to reported change if balance check fails
                 if wagno_received <= 0:
                     print("❌ No waGNO available to unwrap based on reported change or balance check.")
                     sys.exit(1)


            print(f"\n\u2705 Successfully bought (or confirmed balance of) {wagno_received:.18f} waGNO")

            # Step 2: Unwrap waGNO
            unwrap_result = gno_wrapper.unwrap(wagno_received)
            if unwrap_result:
                print(f"\n\u2705 Successfully unwrapped waGNO. Tx: {unwrap_result}")
            else:
                print(f"\n\u274c Failed to unwrap waGNO.")
            bot.print_balances(bot.get_balances())

        elif args.command == 'wrap_gno':
            tx_hash = gno_wrapper.wrap(args.amount)
            if tx_hash:
                bot.print_balances(bot.get_balances())

        elif args.command == 'unwrap_wagno':
            tx_hash = gno_wrapper.unwrap(args.amount)
            if tx_hash:
                bot.print_balances(bot.get_balances())

        # --- Conditional Token Split/Merge ---
        elif args.command == 'split_gno':
            if token_manager.split('GNO', args.amount):
                bot.print_balances(bot.get_balances())

        elif args.command == 'split_sdai':
            if token_manager.split('sDAI', args.amount):
                bot.print_balances(bot.get_balances())

        elif args.command == 'merge_gno':
            if token_manager.merge('GNO', args.amount):
                bot.print_balances(bot.get_balances())

        elif args.command == 'merge_sdai':
            if token_manager.merge('sDAI', args.amount):
                bot.print_balances(bot.get_balances())

        # --- Conditional Swaps ---
        elif args.command == 'swap_gno_yes_to_sdai_yes':
            # GNO-YES (token0 in YES pool) -> sDAI-YES (token1 in YES pool) => zero_for_one=True
            swap_manager.swap_conditional(
                pool_address=POOL_CONFIG_YES["address"],
                token_in=TOKEN_CONFIG["company"]["yes_address"],
                token_out=TOKEN_CONFIG["currency"]["yes_address"],
                amount=args.amount,
                zero_for_one=True
            )
            bot.print_balances(bot.get_balances())

        elif args.command == 'swap_sdai_yes_to_gno_yes':
            # sDAI-YES (token1 in YES pool) -> GNO-YES (token0 in YES pool) => zero_for_one=False
            swap_manager.swap_conditional(
                pool_address=POOL_CONFIG_YES["address"],
                token_in=TOKEN_CONFIG["currency"]["yes_address"],
                token_out=TOKEN_CONFIG["company"]["yes_address"],
                amount=args.amount,
                zero_for_one=False
            )
            bot.print_balances(bot.get_balances())

        elif args.command == 'swap_gno_no_to_sdai_no':
            # GNO-NO (token1 in NO pool) -> sDAI-NO (token0 in NO pool) => zero_for_one=False
            swap_manager.swap_conditional(
                pool_address=POOL_CONFIG_NO["address"],
                token_in=TOKEN_CONFIG["company"]["no_address"],
                token_out=TOKEN_CONFIG["currency"]["no_address"],
                amount=args.amount,
                zero_for_one=False
            )
            bot.print_balances(bot.get_balances())

        elif args.command == 'swap_sdai_no_to_gno_no':
            # sDAI-NO (token0 in NO pool) -> GNO-NO (token1 in NO pool) => zero_for_one=True
            swap_manager.swap_conditional(
                pool_address=POOL_CONFIG_NO["address"],
                token_in=TOKEN_CONFIG["currency"]["no_address"],
                token_out=TOKEN_CONFIG["company"]["no_address"],
                amount=args.amount,
                zero_for_one=True
            )
            bot.print_balances(bot.get_balances())

        elif args.command == 'buy_sdai_yes':
            swap_manager.buy_sdai_yes(args.amount)
            bot.print_balances(bot.get_balances())

        elif args.command == 'sell_sdai_yes':
            swap_manager.sell_sdai_yes(args.amount)
            bot.print_balances(bot.get_balances())

        # --- Test Swaps ---
        elif args.command == 'test_swaps':
            print("\n\U0001f9ea Testing all swap functions with small amounts...")
            test_amount = args.amount if hasattr(args, 'amount') and args.amount else 0.001 # Corrected logic for default

            results = {}

            print("\n\n--- 1. GNO YES -> sDAI YES ---")
            results['gno_yes_to_sdai_yes'] = swap_manager.swap_conditional(
                POOL_CONFIG_YES["address"], TOKEN_CONFIG["company"]["yes_address"], TOKEN_CONFIG["currency"]["yes_address"], test_amount, True)

            print("\n\n--- 2. sDAI YES -> GNO YES ---")
            results['sdai_yes_to_gno_yes'] = swap_manager.swap_conditional(
                POOL_CONFIG_YES["address"], TOKEN_CONFIG["currency"]["yes_address"], TOKEN_CONFIG["company"]["yes_address"], test_amount, False)

            print("\n\n--- 3. GNO NO -> sDAI NO ---")
            results['gno_no_to_sdai_no'] = swap_manager.swap_conditional(
                POOL_CONFIG_NO["address"], TOKEN_CONFIG["company"]["no_address"], TOKEN_CONFIG["currency"]["no_address"], test_amount, False)

            print("\n\n--- 4. sDAI NO -> GNO NO ---")
            results['sdai_no_to_gno_no'] = swap_manager.swap_conditional(
                POOL_CONFIG_NO["address"], TOKEN_CONFIG["currency"]["no_address"], TOKEN_CONFIG["company"]["no_address"], test_amount, True)

            print("\n\n--- 5. Buy sDAI YES ---")
            results['buy_sdai_yes'] = swap_manager.buy_sdai_yes(test_amount)

            print("\n\n--- 6. Sell sDAI YES ---")
            results['sell_sdai_yes'] = swap_manager.sell_sdai_yes(test_amount)

            print("\n\n--- 7. Balancer: sDAI -> waGNO ---")
            balancer_res1 = swap_manager.swap_balancer('sDAI', 'waGNO', test_amount)
            results['sdai_to_wagno'] = balancer_res1 and balancer_res1.get('success', False)

            print("\n\n--- 8. Balancer: waGNO -> sDAI ---")
            # Need waGNO to test this, check balance first or skip if none
            balances_before_wagno_sell = bot.get_balances()
            wagno_test_sell_amount = float(balances_before_wagno_sell['wagno']['wallet'])
            if wagno_test_sell_amount >= test_amount: # Ensure enough waGNO
                balancer_res2 = swap_manager.swap_balancer('waGNO', 'sDAI', test_amount)
                results['wagno_to_sdai'] = balancer_res2 and balancer_res2.get('success', False)
            else:
                 print(f"   Skipping waGNO -> sDAI test, insufficient waGNO ({wagno_test_sell_amount:.6f} < {test_amount})")
                 results['wagno_to_sdai'] = 'Skipped'


            # Print summary
            print("\n\n============================================")
            print("\U0001f9ea Swap Tests Summary")
            print("============================================")
            for name, success in results.items():
                 if success == 'Skipped':
                    status = '\u23e9 Skipped'
                 else:
                    status = '\u2705 Success' if success else '\u274c Failed'
                 print(f"{name.replace('_', ' ').title()}: {status}")

            # Show final balances
            bot.print_balances(bot.get_balances())

        # --- Arbitrage Flows ---
        elif args.command == 'arbitrage_sell_synthetic_gno':
            execute_arbitrage_sell_synthetic_gno(bot, args.amount, swap_manager, token_manager, gno_wrapper)

        elif args.command == 'arbitrage_buy_synthetic_gno':
            execute_arbitrage_buy_synthetic_gno(bot, args.amount, swap_manager, token_manager, gno_wrapper)

        elif args.command == 'interactive':
             print("Interactive mode is not yet fully implemented in this refactored version.")
             # Placeholder for future interactive loop

        else:
            # Default to showing help if no command matched and not interactive
            if args.command: # Only print if an invalid command was given
                 print(f"Unknown command: {args.command}")
            parser.print_help() # Use parser's help function
            sys.exit(1)

    except Exception as e:
        print(f"\n\u274c An error occurred: {e}")
        traceback.print_exc()
        sys.exit(1)
    

# --- Refactored Arbitrage Functions ---

def execute_arbitrage_sell_synthetic_gno(bot, sdai_amount, swap_manager, token_manager, gno_wrapper):
    """
    Execute a full arbitrage operation (Sell Synthetic GNO direction).
    Uses manager classes for simplified logic.
    """
    print(f"\n\U0001f504 Starting Sell Synthetic GNO Arbitrage with {sdai_amount} sDAI")
    initial_balances = bot.get_balances()
    initial_sdai = float(initial_balances['currency']['wallet'])
    initial_wagno = float(initial_balances['wagno']['wallet']) # Track initial waGNO for accurate received amount
    initial_gno = float(initial_balances['company']['wallet']) # Track initial GNO
    initial_gno_yes = float(initial_balances['company']['yes']) # Track initial GNO YES
    initial_gno_no = float(initial_balances['company']['no']) # Track initial GNO NO
    initial_sdai_yes = float(initial_balances['currency']['yes']) # Track initial sDAI YES
    initial_sdai_no = float(initial_balances['currency']['no']) # Track initial sDAI NO


    if initial_sdai < sdai_amount:
        print(f"\u274c Insufficient sDAI balance. Required: {sdai_amount}, Available: {initial_sdai}")
        return

    print("\n\U0001f4ca Initial market prices:")
    market_prices = bot.get_market_prices()
    if not market_prices: return # Stop if prices can't be fetched
    bot.print_market_prices(market_prices)
    synthetic_price, spot_price = bot.calculate_synthetic_price()

    # Step 1: Buy waGNO with sDAI
    print(f"\n\U0001f539 Step 1: Buying waGNO with {sdai_amount} sDAI...")
    buy_result = swap_manager.swap_balancer('sDAI', 'waGNO', sdai_amount)
    if not buy_result or not buy_result.get('success'):
        print("\u274c Failed to buy waGNO. Aborting.")
        return

    # Calculate waGNO received accurately
    balances_after_buy = bot.get_balances()
    wagno_after_buy = float(balances_after_buy['wagno']['wallet'])
    wagno_received = wagno_after_buy - initial_wagno

    if wagno_received <= 0.000001: # Use a small threshold for floating point comparison
        print("❌ No waGNO received or balance calculation error. Aborting.")
        # Optional: Add more debug info like initial/final balances
        return
    print(f"\u2705 Successfully received {wagno_received:.6f} waGNO")

    # Step 2: Unwrap waGNO to GNO
    print(f"\n\U0001f539 Step 2: Unwrapping {wagno_received:.6f} waGNO...")
    # gno_before_unwrap = float(balances_after_buy['company']['wallet']) # Already captured as initial_gno if buy was first step
    unwrap_tx = gno_wrapper.unwrap(wagno_received)
    if not unwrap_tx:
        print("⚠️ Failed to unwrap waGNO, but attempting to continue by checking balance...")

    # Verify GNO received
    balances_after_unwrap = bot.get_balances()
    gno_after_unwrap = float(balances_after_unwrap['company']['wallet'])
    # gno_amount_unwrapped = gno_after_unwrap - gno_before_unwrap # Calculation depends on initial state
    gno_amount_unwrapped = gno_after_unwrap - initial_gno # More robust if initial state is known

    if gno_amount_unwrapped <= 0.000001:
        print("❌ No GNO received after unwrapping or balance error. Aborting.")
        return
    print(f"\u2705 Successfully received {gno_amount_unwrapped:.6f} GNO")

    # Step 3: Split GNO into YES/NO tokens
    print(f"\n\U0001f539 Step 3: Splitting {gno_amount_unwrapped:.6f} GNO...")
    # gno_yes_before_split = float(balances_after_unwrap['company']['yes']) # Captured as initial if first step
    # gno_no_before_split = float(balances_after_unwrap['company']['no']) # Captured as initial if first step

    if not token_manager.split('GNO', gno_amount_unwrapped):
        print("❌ Failed to split GNO. Aborting.")
        return

    # Get amounts received from split
    balances_after_split = bot.get_balances()
    gno_yes_to_sell = float(balances_after_split['company']['yes']) - initial_gno_yes
    gno_no_to_sell = float(balances_after_split['company']['no']) - initial_gno_no

    if gno_yes_to_sell <= 0.000001 or gno_no_to_sell <= 0.000001:
        print("❌ Failed to receive GNO-YES/NO tokens after split or balance error. Aborting.")
        return
    print(f"\u2705 Received {gno_yes_to_sell:.6f} GNO-YES and {gno_no_to_sell:.6f} GNO-NO")

    # Step 4: Sell GNO-YES for sDAI-YES
    print(f"\n\U0001f539 Step 4: Selling {gno_yes_to_sell:.6f} GNO-YES...")
    # sdai_yes_before_swap = float(balances_after_split['currency']['yes']) # Captured initially

    success_sell_yes = swap_manager.swap_conditional(
        pool_address=POOL_CONFIG_YES["address"],
        token_in=TOKEN_CONFIG["company"]["yes_address"],
        token_out=TOKEN_CONFIG["currency"]["yes_address"],
        amount=gno_yes_to_sell,
        zero_for_one=True
    )
    if not success_sell_yes: print("⚠️ Failed to sell GNO-YES, continuing...")

    # Step 5: Sell GNO-NO for sDAI-NO
    print(f"\n\U0001f539 Step 5: Selling {gno_no_to_sell:.6f} GNO-NO...")
    # sdai_no_before_swap = float(balances_after_split['currency']['no']) # Captured initially
    print("   Waiting briefly before next swap...")
    time.sleep(3) # Slightly longer wait for nonce issues

    success_sell_no = swap_manager.swap_conditional(
        pool_address=POOL_CONFIG_NO["address"],
        token_in=TOKEN_CONFIG["company"]["no_address"],
        token_out=TOKEN_CONFIG["currency"]["no_address"],
        amount=gno_no_to_sell,
        zero_for_one=False # GNO-NO is token1, sDAI-NO is token0 in NO pool
    )
    if not success_sell_no: print("⚠️ Failed to sell GNO-NO, continuing...")

    # Step 6: Balance sDAI-YES and sDAI-NO
    print("\n\U0001f539 Step 6: Balancing sDAI-YES/NO tokens...")
    balances_after_swaps = bot.get_balances()
    sdai_yes_after = float(balances_after_swaps['currency']['yes'])
    sdai_no_after = float(balances_after_swaps['currency']['no'])
    sdai_wallet_balance = float(balances_after_swaps['currency']['wallet']) # Use current wallet balance

    print(f"   Current sDAI-YES: {sdai_yes_after:.6f} (Initial: {initial_sdai_yes:.6f})")
    print(f"   Current sDAI-NO: {sdai_no_after:.6f} (Initial: {initial_sdai_no:.6f})")

    sdai_yes_gained = sdai_yes_after - initial_sdai_yes
    sdai_no_gained = sdai_no_after - initial_sdai_no
    print(f"   Gained sDAI-YES: {sdai_yes_gained:.6f}")
    print(f"   Gained sDAI-NO: {sdai_no_gained:.6f}")


    # Calculate the amount needed to balance based on *gained* amounts
    target_merge_amount = min(sdai_yes_gained, sdai_no_gained)
    if target_merge_amount < 0: target_merge_amount = 0 # Can't merge negative amounts

    if sdai_yes_gained > sdai_no_gained:
        difference = sdai_yes_gained - sdai_no_gained
        print(f"   Have {difference:.6f} excess sDAI-YES (relative to gained NO). Selling excess...")
        if not swap_manager.sell_sdai_yes(difference):
            print("⚠️ Failed to sell excess sDAI-YES.")
    elif sdai_no_gained > sdai_yes_gained:
        difference = sdai_no_gained - sdai_yes_gained
        print(f"   Need {difference:.6f} more sDAI-YES (relative to gained NO).")
        # Check sDAI balance *before* buying
        if sdai_wallet_balance >= difference: # Check if current wallet balance is enough
             print(f"   Buying {difference:.6f} sDAI-YES using wallet sDAI...")
             if not swap_manager.buy_sdai_yes(difference):
                 print("⚠️ Failed to buy required sDAI-YES.")
        else:
             print(f"   Insufficient sDAI ({sdai_wallet_balance:.6f}) to buy {difference:.6f} sDAI-YES.")

    else:
        print("   sDAI-YES and sDAI-NO gained are balanced.")

    # Step 7: Merge sDAI-YES and sDAI-NO
    print("\n\U0001f539 Step 7: Merging sDAI-YES/NO pairs...")
    balances_after_balance = bot.get_balances() # Re-fetch after potential balancing swap
    sdai_yes_final = float(balances_after_balance['currency']['yes'])
    sdai_no_final = float(balances_after_balance['currency']['no'])
    # Merge the minimum of the *current total* balances
    merge_amount = min(sdai_yes_final, sdai_no_final)

    if merge_amount > 0.000001: # Use threshold
        print(f"   Merging {merge_amount:.6f} sDAI-YES/NO pairs...")
        if not token_manager.merge('sDAI', merge_amount):
            print("⚠️ Failed to merge sDAI tokens.")
    else:
        print("   No pairs available to merge or amount too small.")

    # Step 8: Final Report
    print("\n\U0001f4c8 Arbitrage Operation Summary")
    print("=" * 40)
    final_balances = bot.get_balances() # Fetch final state
    final_sdai = float(final_balances['currency']['wallet'])
    profit_loss = final_sdai - initial_sdai
    profit_loss_percent = (profit_loss / sdai_amount) * 100 if sdai_amount > 0 else 0

    print(f"Initial sDAI: {initial_sdai:.6f}")
    print(f"Final sDAI:   {final_sdai:.6f}")
    print(f"------------------------------------")
    print(f"Direct Profit/Loss: {profit_loss:+.6f} sDAI ({profit_loss_percent:+.2f}%)")
    # Add estimation of remaining token values if desired
    print("\nRemaining Conditional Token Balances:")
    print(f"  sDAI-YES: {final_balances['currency']['yes']:.6f}")
    print(f"  sDAI-NO:  {final_balances['currency']['no']:.6f}")
    print(f"  GNO-YES:  {final_balances['company']['yes']:.6f}")
    print(f"  GNO-NO:   {final_balances['company']['no']:.6f}")


    try: # Wrap price calculation in try-except
        synthetic_price_final, spot_price_final = bot.calculate_synthetic_price()
        print("\nMarket Prices:")
        print(f"Initial GNO Spot:      {spot_price:.6f} -> Final: {spot_price_final:.6f}")
        print(f"Initial GNO Synthetic: {synthetic_price:.6f} -> Final: {synthetic_price_final:.6f}")
    except Exception as price_error:
        print(f"\n⚠️ Error calculating final market prices: {price_error}")


    if profit_loss > 0:
        print("\n\u2705 Arbitrage appears profitable based on direct sDAI change!")
    else:
        print("\n⚠️ Arbitrage does not appear profitable based on direct sDAI change.")


def execute_arbitrage_buy_synthetic_gno(bot, sdai_amount, swap_manager, token_manager, gno_wrapper):
    """
    Execute a full arbitrage operation (Buy Synthetic GNO direction).
    Uses manager classes for simplified logic.
    """
    print(f"\n\U0001f504 Starting Buy Synthetic GNO Arbitrage with {sdai_amount} sDAI")
    initial_balances = bot.get_balances()
    initial_sdai = float(initial_balances['currency']['wallet'])
    initial_sdai_yes = float(initial_balances['currency']['yes'])
    initial_sdai_no = float(initial_balances['currency']['no'])
    initial_gno_yes = float(initial_balances['company']['yes'])
    initial_gno_no = float(initial_balances['company']['no'])
    initial_gno = float(initial_balances['company']['wallet'])
    initial_wagno = float(initial_balances['wagno']['wallet'])


    if initial_sdai < sdai_amount:
        print(f"\u274c Insufficient sDAI balance. Required: {sdai_amount}, Available: {initial_sdai}")
        return

    # Step 1 & 2: Get prices and calculate optimal amounts
    print("\n\U0001f539 Step 1 & 2: Calculating optimal amounts...")
    market_prices = bot.get_market_prices()
    if not market_prices: return
    bot.print_market_prices(market_prices)

    yes_price = market_prices.get('yes_price') # Use .get for safety
    no_price = market_prices.get('no_price')
    probability = market_prices.get('probability')
    if yes_price is None or no_price is None or probability is None:
         print("❌ Cannot calculate optimal amounts, missing price data.")
         return

    synthetic_price, spot_price = bot.calculate_synthetic_price()

    if no_price <= 0 or yes_price <= 0: # Check for non-positive prices
        print("❌ Cannot calculate optimal amounts due to zero or negative price for YES or NO tokens.")
        return

    # Denominator calculation - ensure probability is between 0 and 1
    probability = max(0.0, min(1.0, probability)) # Clamp probability
    term1 = (yes_price * probability) / no_price
    term2 = (1 - probability)
    denominator = term1 + term2

    if denominator <= 1e-9: # Check for near-zero denominator
        print("❌ Cannot calculate optimal amounts due to near-zero denominator.")
        return

    # Calculate target amounts of sDAI-YES and sDAI-NO needed *from* the initial sdai_amount
    # y represents the amount of sDAI needed to generate the target sDAI-NO via split/buy
    # x represents the amount of sDAI needed to generate the target sDAI-YES via split/buy
    # The total sDAI used should approximate sdai_amount
    # Let's rethink this: we have sdai_amount to *spend*.
    # We want to end up with amounts of GNO-YES and GNO-NO that can be merged.
    # This requires buying GNO-YES with sDAI-YES and GNO-NO with sDAI-NO.
    # Let g_yes be amount of GNO-YES bought, g_no be amount of GNO-NO bought. We want g_yes = g_no.
    # Cost of g_yes GNO-YES is roughly g_yes * yes_price (in sDAI-YES terms)
    # Cost of g_no GNO-NO is roughly g_no * no_price (in sDAI-NO terms)
    # To get sDAI-YES and sDAI-NO:
    #   - Split sDAI: 1 sDAI -> 1 sDAI-YES + 1 sDAI-NO
    #   - Buy sDAI-YES pool: Cost depends on pool price (let's call it p_sdai_yes)
    # This calculation is complex due to interdependent pool prices.
    # Let's simplify the initial approach: Aim to acquire balanced sDAI-YES/NO first using sdai_amount.

    # Approach 1: Split half, buy/sell YES to balance
    # split_amount = sdai_amount / 2
    # buy_yes_amount = sdai_amount / 2

    # Approach 2: Use probability-weighted split (original logic interpretation)
    # Assume 'y' is the amount of sDAI to *split*
    # Assume 'x' represents the target *value* of sDAI-YES relative to sDAI-NO
    # Let's use the simpler strategy: Split X sDAI, use remaining (sdai_amount - X) sDAI to buy/sell sDAI-YES to balance.
    # Simplest: Split all sdai_amount, then sell excess of whichever conditional token is cheaper.

    print(f"   Strategy: Splitting {sdai_amount:.6f} sDAI, then balancing...")


    # Step 3: Split sDAI
    print(f"\n\U0001f539 Step 3: Splitting {sdai_amount:.6f} sDAI into YES/NO...")
    if not token_manager.split('sDAI', sdai_amount):
        print("❌ Failed to split sDAI. Aborting.")
        return
    
    # Step 4 & 5: Balance sDAI-YES/NO by selling the cheaper one
    print("\n\U0001f539 Step 4 & 5: Balancing sDAI-YES/NO...")
    balances_after_split = bot.get_balances()
    sdai_yes_after_split = float(balances_after_split['currency']['yes'])
    sdai_no_after_split = float(balances_after_split['currency']['no'])

    sdai_yes_gained = sdai_yes_after_split - initial_sdai_yes
    sdai_no_gained = sdai_no_after_split - initial_sdai_no

    print(f"   Gained sDAI-YES: {sdai_yes_gained:.6f}")
    print(f"   Gained sDAI-NO: {sdai_no_gained:.6f}")

    # Determine which to sell/buy based on which amount is larger (assuming split gives equal amounts)
    # If yes_price > no_price (probability > 0.5), YES is more expensive, NO is cheaper. Sell YES? No, buy NO?
    # If we split 1 sDAI -> 1 YES + 1 NO.
    # If YES price is 0.7, NO price is 0.3. We have 0.7 value in YES, 0.3 in NO.
    # To get equal value? No, we need equal *amounts* to merge later.
    # The split gives equal amounts. Any imbalance comes from *initial* balances.
    # Let's target merging the *gained* amounts.

    amount_to_balance = abs(sdai_yes_gained - sdai_no_gained) / 2 # Amount to shift

    if amount_to_balance > 0.000001: # Only balance if difference is significant
        # Fetch the price of sDAI-YES in the dedicated pool
        sdai_yes_pool_price = bot.get_sdai_yes_pool_price() # Assume this helper exists or implement it

        if sdai_yes_pool_price is None:
             print("⚠️ Could not get sDAI/sDAI-YES pool price. Skipping balancing.")
        else:
            print(f"   sDAI/sDAI-YES pool price: {sdai_yes_pool_price:.6f} (sDAI per sDAI-YES)")
            if sdai_yes_gained > sdai_no_gained:
                print(f"   Have excess sDAI-YES ({sdai_yes_gained - sdai_no_gained:.6f}). Selling {amount_to_balance:.6f}...")
                if not swap_manager.sell_sdai_yes(amount_to_balance):
                     print("⚠️ Failed to sell excess sDAI-YES for balancing.")
            else: # sdai_no_gained > sdai_yes_gained
                 print(f"   Have excess sDAI-NO ({sdai_no_gained - sdai_yes_gained:.6f}). Buying {amount_to_balance:.6f} sDAI-YES...")
                 # Calculate sDAI needed to buy
                 sdai_needed_for_buy = amount_to_balance * sdai_yes_pool_price # Estimate cost
                 current_sdai_balance = float(balances_after_split['currency']['wallet']) # Check current wallet
                 if current_sdai_balance >= sdai_needed_for_buy:
                     if not swap_manager.buy_sdai_yes(sdai_needed_for_buy): # Buy using estimated sDAI cost
                         print("⚠️ Failed to buy sDAI-YES for balancing.")
                 else:
                     print(f"   Insufficient sDAI ({current_sdai_balance:.6f}) to buy required sDAI-YES ({sdai_needed_for_buy:.6f}). Skipping balance.")
    else:
        print("   sDAI-YES and sDAI-NO gained are already balanced.")


    # Get final available amounts for swapping to GNO conditionals
    balances_before_gno_swap = bot.get_balances() # Re-fetch after potential balancing
    sdai_yes_available = float(balances_before_gno_swap['currency']['yes'])
    sdai_no_available = float(balances_before_gno_swap['currency']['no'])

    print(f"   Available for GNO swap - sDAI-YES: {sdai_yes_available:.6f}")
    print(f"   Available for GNO swap - sDAI-NO: {sdai_no_available:.6f}")


    # Step 6: Buy GNO-YES with sDAI-YES
    print(f"\n\U0001f539 Step 6: Buying GNO-YES with {sdai_yes_available:.6f} sDAI-YES...")
    if sdai_yes_available > 0.000001:
        success_buy_gno_yes = swap_manager.swap_conditional(
            pool_address=POOL_CONFIG_YES["address"],
            token_in=TOKEN_CONFIG["currency"]["yes_address"],
            token_out=TOKEN_CONFIG["company"]["yes_address"],
            amount=sdai_yes_available,
            zero_for_one=False # sDAI-YES is token1, GNO-YES is token0
        )
        if not success_buy_gno_yes: print("⚠️ Failed to buy GNO-YES, continuing...")
    else:
        print("   Skipping GNO-YES buy, insufficient sDAI-YES.")

    # Step 7: Buy GNO-NO with sDAI-NO
    print(f"\n\U0001f539 Step 7: Buying GNO-NO with {sdai_no_available:.6f} sDAI-NO...")
    if sdai_no_available > 0.000001:
        print("   Waiting briefly before next swap...")
        time.sleep(3) # Avoid nonce issues
        success_buy_gno_no = swap_manager.swap_conditional(
            pool_address=POOL_CONFIG_NO["address"],
            token_in=TOKEN_CONFIG["currency"]["no_address"],
            token_out=TOKEN_CONFIG["company"]["no_address"],
            amount=sdai_no_available,
            zero_for_one=True # sDAI-NO is token0, GNO-NO is token1
        )
        if not success_buy_gno_no: print("⚠️ Failed to buy GNO-NO, continuing...")
    else:
        print("   Skipping GNO-NO buy, insufficient sDAI-NO.")


    # Step 8: Merge GNO-YES/NO into GNO
    print("\n\U0001f539 Step 8: Merging GNO-YES/NO pairs...")
    balances_after_gno_buy = bot.get_balances()
    gno_yes_final = float(balances_after_gno_buy['company']['yes'])
    gno_no_final = float(balances_after_gno_buy['company']['no'])
    # Merge the minimum of the *total* current balances
    merge_gno_amount = min(gno_yes_final, gno_no_final)

    if merge_gno_amount > 0.000001:
         print(f"   Merging {merge_gno_amount:.6f} GNO-YES/NO pairs...")
         if not token_manager.merge('GNO', merge_gno_amount):
             print("⚠️ Failed to merge GNO tokens.")
    else:
        print("   No GNO pairs available to merge or amount too small.")

    # Step 9: Wrap GNO into waGNO
    balances_after_gno_merge = bot.get_balances()
    # Calculate GNO received from merge vs initial
    gno_after_merge = float(balances_after_gno_merge['company']['wallet'])
    gno_to_wrap = gno_after_merge - initial_gno # Only wrap the GNO obtained in this arb

    print(f"\n\U0001f539 Step 9: Wrapping {gno_to_wrap:.6f} GNO...")
    if gno_to_wrap > 0.000001:
        wrap_tx = gno_wrapper.wrap(gno_to_wrap)
        if not wrap_tx: print("⚠️ Failed to wrap GNO.")
    else:
        print("   No GNO gained in this arbitrage to wrap.")

    # Step 10: Sell waGNO for sDAI
    balances_after_wrap = bot.get_balances()
    # Calculate waGNO available from wrap vs initial
    wagno_after_wrap = float(balances_after_wrap['wagno']['wallet'])
    wagno_to_sell = wagno_after_wrap - initial_wagno # Only sell waGNO obtained

    print(f"\n\U0001f539 Step 10: Selling {wagno_to_sell:.6f} waGNO...")
    if wagno_to_sell > 0.000001:
        sell_result = swap_manager.swap_balancer('waGNO', 'sDAI', wagno_to_sell)
        if not sell_result or not sell_result.get('success'):
            print("⚠️ Failed to sell waGNO.")
    else:
        print("   No waGNO gained in this arbitrage to sell.")

    # Step 11: Final Report
    print("\n\U0001f4c8 Arbitrage Operation Summary")
    print("=" * 40)
    final_balances = bot.get_balances() # Fetch final state
    final_sdai = float(final_balances['currency']['wallet'])
    profit_loss = final_sdai - initial_sdai
    profit_loss_percent = (profit_loss / sdai_amount) * 100 if sdai_amount > 0 else 0

    print(f"Initial sDAI: {initial_sdai:.6f}")
    print(f"Final sDAI:   {final_sdai:.6f}")
    print(f"------------------------------------")
    print(f"Direct Profit/Loss: {profit_loss:+.6f} sDAI ({profit_loss_percent:+.2f}%)")
    print("\nRemaining Conditional Token Balances:")
    print(f"  sDAI-YES: {final_balances['currency']['yes']:.6f}")
    print(f"  sDAI-NO:  {final_balances['currency']['no']:.6f}")
    print(f"  GNO-YES:  {final_balances['company']['yes']:.6f}")
    print(f"  GNO-NO:   {final_balances['company']['no']:.6f}")

    try:
        synthetic_price_final, spot_price_final = bot.calculate_synthetic_price()
        print("\nMarket Prices:")
        print(f"Initial GNO Spot:      {spot_price:.6f} -> Final: {spot_price_final:.6f}")
        print(f"Initial GNO Synthetic: {synthetic_price:.6f} -> Final: {synthetic_price_final:.6f}")
    except Exception as price_error:
        print(f"\n⚠️ Error calculating final market prices: {price_error}")

    if profit_loss > 0:
        print("\n\u2705 Arbitrage appears profitable based on direct sDAI change!")
    else:
        print("\n⚠️ Arbitrage does not appear profitable based on direct sDAI change.")


# --- Entry Point ---
if __name__ == "__main__":
    main() 