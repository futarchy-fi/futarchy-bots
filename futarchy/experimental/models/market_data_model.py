from web3 import Web3
from web3.exceptions import ContractLogicError
from futarchy.experimental.config.constants import TOKEN_CONFIG, ERC20_ABI

class MarketDataModel:
    """Handles fetching market data like balances and prices."""

    def __init__(self, bot_context):
        """Initializes with bot context containing w3 and address."""
        self.bot = bot_context
        self.w3 = bot_context.w3
        self.address = bot_context.address

    def get_token_balance(self, token_address: str, owner_address: str) -> int:
        """Gets the balance of a specific token for an owner."""
        try:
            checksum_token_addr = self.w3.to_checksum_address(token_address)
            checksum_owner_addr = self.w3.to_checksum_address(owner_address)
            contract = self.w3.eth.contract(address=checksum_token_addr, abi=ERC20_ABI)
            balance = contract.functions.balanceOf(checksum_owner_addr).call()
            return balance
        except (ContractLogicError, ValueError) as e:
            print(f"Warning: Could not get balance for {token_address}. Error: {e}")
            return 0
        except Exception as e:
            print(f"Unexpected error getting balance for {token_address}: {e}")
            return 0


    def get_all_balances(self) -> dict:
        """
        Get all token balances for the configured address.
        Returns balances in native token units (ether).
        """
        if self.address is None:
            print("Warning: No owner address configured to fetch balances.")
            return {}

        balances = {
            "currency": {"wallet": 0, "yes": 0, "no": 0},
            "company": {"wallet": 0, "yes": 0, "no": 0},
            "wagno": {"wallet": 0}
        }

        # Helper to safely get balance and convert to ether
        def _get_and_convert(token_key, sub_key="address"):
            address_str = TOKEN_CONFIG.get(token_key, {}).get(sub_key)
            if address_str:
                wei_balance = self.get_token_balance(address_str, self.address)
                return self.w3.from_wei(wei_balance, 'ether')
            return 0

        balances["currency"]["wallet"] = _get_and_convert("currency")
        balances["currency"]["yes"] = _get_and_convert("currency", "yes_address")
        balances["currency"]["no"] = _get_and_convert("currency", "no_address")

        balances["company"]["wallet"] = _get_and_convert("company")
        balances["company"]["yes"] = _get_and_convert("company", "yes_address")
        balances["company"]["no"] = _get_and_convert("company", "no_address")

        balances["wagno"]["wallet"] = _get_and_convert("wagno")

        return balances

    # --- Add other market data methods here later (get_prices, etc.) ---
