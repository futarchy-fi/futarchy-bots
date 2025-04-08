import math
from decimal import Decimal, ROUND_DOWN

# Import config for token names (can be refactored later if needed)
from futarchy.experimental.config.constants import TOKEN_CONFIG

class View:
    """Handles all console output and presentation."""

    def __init__(self, verbose=False):
        self.verbose = verbose

    def _floor_to_6(self, val):
        """Floor a number to 6 decimal places for safe display."""
        if val is None:
            return 0.0
        try:
            d_val = Decimal(str(val))
            rounded = d_val.quantize(Decimal('0.000001'), rounding=ROUND_DOWN)
            return float(rounded)
        except Exception:
            # Fallback for non-numeric types or conversion errors
            return 0.0


    def display_balances(self, balances_data: dict):
        """Prints token balances in a formatted way."""
        if not balances_data:
            print("Could not retrieve balance data.")
            return

        print("\n=== Token Balances ===")

        # Display Currency Tokens (sDAI)
        currency_data = balances_data.get("currency", {})
        currency_name = TOKEN_CONFIG.get("currency", {}).get("name", "Currency")
        print(f"\n🟢 {currency_name}:")
        print(f"  Wallet: {self._floor_to_6(currency_data.get('wallet')):.6f}")
        print(f"  YES Tokens: {self._floor_to_6(currency_data.get('yes')):.6f}")
        print(f"  NO Tokens: {self._floor_to_6(currency_data.get('no')):.6f}")

        # Display Company Tokens (GNO)
        company_data = balances_data.get("company", {})
        company_name = TOKEN_CONFIG.get("company", {}).get("name", "Company")
        print(f"\n🔵 {company_name}:")
        print(f"  Wallet: {self._floor_to_6(company_data.get('wallet')):.6f}")
        print(f"  YES Tokens: {self._floor_to_6(company_data.get('yes')):.6f}")
        print(f"  NO Tokens: {self._floor_to_6(company_data.get('no')):.6f}")

        # Display Wrapped GNO (waGNO)
        wagno_data = balances_data.get("wagno", {})
        wagno_name = TOKEN_CONFIG.get("wagno", {}).get("name", "Wrapped GNO")
        print(f"\n🟣 {wagno_name}:")
        print(f"  Wallet: {self._floor_to_6(wagno_data.get('wallet')):.6f}")
        print("="*22)


    def display_error(self, message: str):
        """Displays an error message."""
        print(f"❌ ERROR: {message}")

    def display_message(self, message: str):
        """Displays a general message."""
        print(message)

    def display_verbose(self, message: str):
        """Displays a message only if verbose mode is enabled."""
        if self.verbose:
            print(f"[VERBOSE] {message}")

    def confirm_action(self, prompt: str) -> bool:
        """Asks the user for confirmation."""
        response = input(f"{prompt} (y/n): ").lower().strip()
        return response == 'y'
