import argparse
import sys

# Import Controllers and View
from .view import View
from ..controllers.token_management_controller import TokenManagementController
from ..controllers.trading_controller import TradingController
# from ..controllers.arbitrage_controller import ArbitrageController # Add later
# from ..controllers.strategy_controller import StrategyController # Add later
# Import Models (needed for controller instantiation)
from ..models.market_data_model import MarketDataModel
from ..models.swap_model import SwapModel
from ..models.conditional_token_model import ConditionalTokenModel
from ..models.gno_wrapper_model import GnoWrapperModel


class Router:
    """Parses CLI arguments and dispatches commands to controllers."""

    def __init__(self):
        self.parser = self._create_parser()

    def _create_parser(self):
        parser = argparse.ArgumentParser(
            description='Futarchy Trading Bot (Refactored)',
            # Allow overriding bot args here
            parents=[argparse.ArgumentParser(add_help=False)]
        )

        subparsers = parser.add_subparsers(dest='command', help='Command to run', required=True)

        # --- Balances Command ---
        balances_parser = subparsers.add_parser('balances', help='Show token balances')
        balances_parser.add_argument('--address', type=str, help='(Optional) Check balances for a specific address') # Example optional arg

        # --- Buy/Sell GNO Commands ---
        buy_gno_parser = subparsers.add_parser('buy_gno', help='Buy GNO using sDAI (swaps sDAI->waGNO, unwraps waGNO->GNO)')
        buy_gno_parser.add_argument('amount', type=float, help='Amount of sDAI to spend')

        sell_gno_parser = subparsers.add_parser('sell_gno', help='Sell GNO for sDAI (wraps GNO->waGNO, swaps waGNO->sDAI)')
        sell_gno_parser.add_argument('amount', type=float, help='Amount of GNO to sell')

        # --- Add other commands here later ---
        # Example:
        # prices_parser = subparsers.add_parser('prices', help='Show market prices')
        # wrap_parser = subparsers.add_parser('wrap_gno', help='Wrap GNO')
        # wrap_parser.add_argument('amount', type=float, help='Amount of GNO to wrap')

        return parser

    def dispatch(self, bot_context, argv=None):
        """Parses arguments and calls the appropriate controller method."""
        if argv is None:
            argv = sys.argv[1:] # Use system args if none provided

        try:
            # Re-parse arguments using the defined parser structure
            args = self.parser.parse_args(argv)
            
            # Use verbose flag from bot_context if available, else from args
            verbose_flag = getattr(bot_context, 'verbose', False) # Access from bot if set there
            view = View(verbose=verbose_flag)

            # Instantiate Models needed by controllers
            market_data_model = MarketDataModel(bot_context)
            swap_model = SwapModel(bot_context)
            conditional_token_model = ConditionalTokenModel(bot_context)
            gno_wrapper_model = GnoWrapperModel(bot_context)

            # Instantiate Controllers (pass bot context, view, and models)
            token_controller = TokenManagementController(bot_context, view, market_data_model, gno_wrapper_model, conditional_token_model)
            trading_controller = TradingController(bot_context, view, swap_model, gno_wrapper_model)
            # arb_controller = ArbitrageController(bot_context, view) # Add later
            # strategy_controller = StrategyController(bot_context, view) # Add later


            # --- Command Dispatch Logic ---
            if args.command == 'balances':
                # Potentially override address if provided in args
                if args.address:
                    bot_context.address = bot_context.w3.to_checksum_address(args.address)
                    view.display_message(f"Checking balances for specified address: {bot_context.address}")
                token_controller.show_balances()
            elif args.command == 'buy_gno':
                trading_controller.buy_gno(args.amount)
            elif args.command == 'sell_gno':
                trading_controller.sell_gno(args.amount)
            # elif args.command == 'prices':
            #     strategy_controller.show_prices()
            # elif args.command == 'wrap_gno':
            #     token_controller.wrap_gno(args.amount)
            else:
                view.display_error(f"Unknown command: {args.command}")
                self.parser.print_help()
        except SystemExit: # Prevent argparse SystemExit from stopping execution
            pass
        except argparse.ArgumentError as e:
            print(f"Argument Error: {e}")
            self.parser.print_help()
        except Exception as e:
            # General error handling
            if 'view' in locals():
                view.display_error(f"An unexpected error occurred: {e}")
            else:
                print(f"❌ An unexpected error occurred during setup: {e}")
            import traceback
            traceback.print_exc()
