from futarchy.experimental.models.market_data_model import MarketDataModel
# Import View once it's created in cli/view.py
from futarchy.experimental.cli.view import View

class TokenManagementController:
    """Handles commands related to token balances, wrapping, splitting, etc."""

    def __init__(self, bot_context, view: View):
        self.bot = bot_context
        self.view = view
        # Instantiate necessary models
        self.market_data_model = MarketDataModel(bot_context)
        # self.conditional_token_model = ConditionalTokenModel(bot_context) # Add later
        # self.gno_wrapper_model = GnoWrapperModel(bot_context) # Add later

    def show_balances(self):
        """Fetches and displays token balances."""
        self.view.display_message("Fetching balances...")
        try:
            balances = self.market_data_model.get_all_balances()
            if not balances:
                self.view.display_error("Could not retrieve balances.")
            else:
                self.view.display_balances(balances)
        except Exception as e:
            self.view.display_error(f"An error occurred while fetching balances: {e}")

    # --- Add other methods (wrap, unwrap, split, merge) here later ---
