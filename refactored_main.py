#!/usr/bin/env python3
"""
Futarchy Trading Bot - Refactored Main Entry Point (Experimental)
"""

import sys
import os
import argparse
from dotenv import load_dotenv

# Add the project root to the path BEFORE importing local modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Now import local modules
from futarchy.experimental.core.futarchy_bot import FutarchyBot
from futarchy.experimental.cli.router import Router

def main():
    """Main entry point for the refactored structure."""
    # Load environment variables
    load_dotenv()

    # Initialize the core bot context (holds w3, account, etc.)
    # Pass command-line args for potential overrides like --rpc, --verbose
    parser = argparse.ArgumentParser(add_help=False) # Temporary parser for bot init args
    parser.add_argument('--rpc', type=str, help='RPC URL for Gnosis Chain')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose output')
    bot_args, remaining_argv = parser.parse_known_args()

    try:
        bot = FutarchyBot(rpc_url=bot_args.rpc, verbose=bot_args.verbose)
        if bot.w3 is None or not bot.w3.is_connected():
            print("❌ Failed to establish blockchain connection in FutarchyBot.")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error initializing FutarchyBot: {e}")
        sys.exit(1)

    # Initialize the CLI Router and dispatch the command
    router = Router()
    router.dispatch(bot, remaining_argv) # Pass the bot context and remaining args

if __name__ == '__main__':
    main() 