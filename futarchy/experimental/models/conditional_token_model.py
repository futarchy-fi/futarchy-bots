# futarchy/experimental/models/conditional_token_model.py
# Placeholder for future split/merge logic

import traceback
from typing import TYPE_CHECKING
from futarchy.experimental.config.constants import TOKEN_CONFIG, CONTRACT_ADDRESSES
from futarchy.experimental.utils.web3_utils import get_raw_transaction

if TYPE_CHECKING:
    from ..core.futarchy_bot import FutarchyBot


class ConditionalTokenModel:
    def __init__(self, bot_context: "FutarchyBot"):
        self.bot = bot_context
        # Initialize necessary contracts/handlers here later
        pass

    def split_position(self, token_symbol: str, amount: float, simulate: bool = False):
        """
        Split a base token (e.g., sDAI, GNO) into its corresponding YES and NO tokens.

        Args:
            token_symbol: Symbol of the base token ("sDAI" or "GNO").
            amount: Amount of the base token to split (in ether units).
            simulate: If True, perform checks but do not send transaction.

        Returns:
            bool: True if the operation was successful (or simulation passed), False otherwise.
            Transaction hash (str) if not simulating and successful, None otherwise.
        """
        if self.bot.account is None:
            print("❌ No account configured for transactions.")
            return False, None

        # Determine token type (currency/company) from symbol
        token_type = None
        token_config_entry = None
        if token_symbol.upper() == TOKEN_CONFIG["currency"]["name"].upper():
            token_type = "currency"
            token_config_entry = TOKEN_CONFIG["currency"]
            token_contract = self.bot.sdai_token
        elif token_symbol.upper() == TOKEN_CONFIG["company"]["name"].upper():
            token_type = "company"
            token_config_entry = TOKEN_CONFIG["company"]
            token_contract = self.bot.gno_token
        else:
            print(f"❌ Invalid token symbol for splitting: {token_symbol}. Use 'sDAI' or 'GNO'.")
            return False, None

        token_address = token_config_entry["address"]
        token_name = token_config_entry["name"]
        yes_token_address = token_config_entry["yes_address"]
        no_token_address = token_config_entry["no_address"]

        if self.bot.verbose:
            print("\nContract Addresses:")
            print(f"Base Token ({token_name}): {token_address}")
            print(f"{token_name} YES: {yes_token_address}")
            print(f"{token_name} NO: {no_token_address}")
            print(f"Futarchy Router: {CONTRACT_ADDRESSES['futarchyRouter']}")
            print(f"Market: {CONTRACT_ADDRESSES['market']}\n")

        # Convert amount to wei
        try:
            amount_wei = self.bot.w3.to_wei(amount, 'ether')
        except ValueError:
            print(f"❌ Invalid amount provided: {amount}")
            return False, None

        # Check balance
        has_balance, actual_balance = self.bot.check_token_balance(token_address, amount_wei)
        if self.bot.verbose:
            print(f"\nCurrent Balances:")
            print(f"{token_name}: {self.bot.w3.from_wei(actual_balance, 'ether')} ({actual_balance} wei)")
            print(f"Amount to split: {amount} {token_name} ({amount_wei} wei)\n")

        if not has_balance:
            print(f"❌ Insufficient {token_name} balance")
            print(f"   Required: {self.bot.w3.from_wei(amount_wei, 'ether')} {token_name}")
            print(f"   Available: {self.bot.w3.from_wei(actual_balance, 'ether')} {token_name}")
            return False, None

        # Check allowance
        try:
            allowance = token_contract.functions.allowance(
                self.bot.address,
                CONTRACT_ADDRESSES["futarchyRouter"]
            ).call()
            if self.bot.verbose:
                print(f"{token_name} allowance for Router: {self.bot.w3.from_wei(allowance, 'ether')} {token_name}")
        except Exception as e:
            print(f"❌ Error checking allowance for {token_name}: {e}")
            return False, None

        # Approve router if needed
        needs_approval = allowance < amount_wei
        if needs_approval:
            if simulate:
                print(f"Simulation: Approval needed for {token_name}.")
            else:
                print(f"Approving {token_name} for Router...")
                if not self.bot.approve_token(token_contract, CONTRACT_ADDRESSES["futarchyRouter"], amount_wei):
                    return False, None # Approval failed
        else:
             if self.bot.verbose:
                print(f"✅ {token_name} already approved for Router")

        # --- Simulation Checkpoint ---
        if simulate:
            print(f"✅ Simulation successful: Sufficient balance and approval (or would be requested) for splitting {amount} {token_symbol}.")
            return True, None

        print(f"\n📝 Splitting {amount} {token_name} into YES/NO tokens...")

        try:
            # Build transaction
            tx_params = {
                'from': self.bot.address,
                'nonce': self.bot.w3.eth.get_transaction_count(self.bot.address),
                'gas': 500000,  # Adjust gas limit if needed
                'gasPrice': self.bot.w3.eth.gas_price,
                'chainId': self.bot.w3.eth.chain_id,
            }
            tx = self.bot.futarchy_router.functions.splitPosition(
                self.bot.w3.to_checksum_address(CONTRACT_ADDRESSES["market"]),
                self.bot.w3.to_checksum_address(token_address),
                amount_wei
            ).build_transaction(tx_params)

            # Sign and send transaction
            signed_tx = self.bot.w3.eth.account.sign_transaction(tx, self.bot.account.key)
            tx_hash = self.bot.w3.eth.send_raw_transaction(get_raw_transaction(signed_tx))

            print(f"\n⏳ Split transaction sent: {tx_hash.hex()}")
            print(f"Transaction: https://gnosisscan.io/tx/{tx_hash.hex()}")

            # Wait for transaction confirmation
            receipt = self.bot.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120) # Add timeout

            if receipt['status'] == 1:
                if self.bot.verbose:
                    # Check new balances (optional, can be slow)
                    yes_token = self.bot.get_token_contract(yes_token_address)
                    no_token = self.bot.get_token_contract(no_token_address)
                    yes_balance = yes_token.functions.balanceOf(self.bot.address).call()
                    no_balance = no_token.functions.balanceOf(self.bot.address).call()
                    print(f"\n✅ Successfully split {token_name}!")
                    print(f"New balances:")
                    print(f"{token_name} YES: {self.bot.w3.from_wei(yes_balance, 'ether')}")
                    print(f"{token_name} NO: {self.bot.w3.from_wei(no_balance, 'ether')}")
                else:
                    print(f"\n✅ Successfully split {amount} {token_name} into conditional tokens!")
                return True, tx_hash.hex()
            else:
                print(f"❌ Split transaction failed! Status: {receipt['status']}")
                print(f"Check transaction details at: https://gnosisscan.io/tx/{tx_hash.hex()}")
                return False, tx_hash.hex()

        except Exception as e:
            print(f"❌ Error splitting {token_name} into conditional tokens: {e}")
            traceback.print_exc()
            return False, None

    def merge_position(self, token_symbol: str, amount: float, simulate: bool = False):
        """
        Merge YES and NO tokens back into the base token (e.g., sDAI, GNO).

        Args:
            token_symbol: Symbol of the base token ("sDAI" or "GNO").
            amount: Amount of YES/NO pairs to merge (in ether units).
            simulate: If True, perform checks but do not send transaction.

        Returns:
            bool: True if the operation was successful (or simulation passed), False otherwise.
            Transaction hash (str) if not simulating and successful, None otherwise.
        """
        if self.bot.account is None:
            print("❌ No account configured for transactions.")
            return False, None

        # Determine token type (currency/company) from symbol
        token_type = None
        token_config_entry = None
        if token_symbol.upper() == TOKEN_CONFIG["currency"]["name"].upper():
            token_type = "currency"
            token_config_entry = TOKEN_CONFIG["currency"]
            yes_token_contract = self.bot.sdai_yes_token
            no_token_contract = self.bot.sdai_no_token
        elif token_symbol.upper() == TOKEN_CONFIG["company"]["name"].upper():
            token_type = "company"
            token_config_entry = TOKEN_CONFIG["company"]
            yes_token_contract = self.bot.gno_yes_token
            no_token_contract = self.bot.gno_no_token
        else:
            print(f"❌ Invalid token symbol for merging: {token_symbol}. Use 'sDAI' or 'GNO'.")
            return False, None

        base_token_address = token_config_entry["address"]
        token_name = token_config_entry["name"]
        yes_token_address = token_config_entry["yes_address"]
        no_token_address = token_config_entry["no_address"]

        # Convert amount to wei
        try:
            amount_wei = self.bot.w3.to_wei(amount, 'ether')
        except ValueError:
            print(f"❌ Invalid amount provided: {amount}")
            return False, None

        # Check YES and NO token balances
        try:
            yes_balance = yes_token_contract.functions.balanceOf(self.bot.address).call()
            no_balance = no_token_contract.functions.balanceOf(self.bot.address).call()
        except Exception as e:
            print(f"❌ Error checking YES/NO balances for {token_name}: {e}")
            return False, None

        if self.bot.verbose:
            print(f"\nCurrent Balances:")
            print(f"{token_name} YES: {self.bot.w3.from_wei(yes_balance, 'ether')} ({yes_balance} wei)")
            print(f"{token_name} NO: {self.bot.w3.from_wei(no_balance, 'ether')} ({no_balance} wei)")
            print(f"Amount to merge: {amount} {token_name} ({amount_wei} wei)\n")

        if yes_balance < amount_wei or no_balance < amount_wei:
            print(f"❌ Insufficient YES/NO token balance for merge")
            print(f"   Required: {self.bot.w3.from_wei(amount_wei, 'ether')} {token_name} YES and NO each")
            print(f"   Available: YES={self.bot.w3.from_wei(yes_balance, 'ether')}, NO={self.bot.w3.from_wei(no_balance, 'ether')}")
            return False, None

        # Check and approve YES token for the router
        needs_yes_approval = True
        try:
            yes_allowance = yes_token_contract.functions.allowance(
                self.bot.address,
                CONTRACT_ADDRESSES["futarchyRouter"]
            ).call()
            needs_yes_approval = yes_allowance < amount_wei
            if self.bot.verbose:
                 print(f"{token_name} YES allowance for Router: {self.bot.w3.from_wei(yes_allowance, 'ether')}")
        except Exception as e:
             print(f"❌ Error checking YES allowance for {token_name}: {e}")
             return False, None

        if needs_yes_approval:
            if simulate:
                print(f"Simulation: Approval needed for {token_name} YES.")
            else:
                print(f"Approving {token_name} YES for Router...")
                if not self.bot.approve_token(yes_token_contract, CONTRACT_ADDRESSES["futarchyRouter"], amount_wei):
                    return False, None # Approval failed
        else:
            if self.bot.verbose:
                print(f"✅ {token_name} YES already approved for Router")

        # Check and approve NO token for the router
        needs_no_approval = True
        try:
            no_allowance = no_token_contract.functions.allowance(
                self.bot.address,
                CONTRACT_ADDRESSES["futarchyRouter"]
            ).call()
            needs_no_approval = no_allowance < amount_wei
            if self.bot.verbose:
                print(f"{token_name} NO allowance for Router: {self.bot.w3.from_wei(no_allowance, 'ether')}")
        except Exception as e:
             print(f"❌ Error checking NO allowance for {token_name}: {e}")
             return False, None

        if needs_no_approval:
            if simulate:
                print(f"Simulation: Approval needed for {token_name} NO.")
            else:
                print(f"Approving {token_name} NO for Router...")
                if not self.bot.approve_token(no_token_contract, CONTRACT_ADDRESSES["futarchyRouter"], amount_wei):
                    return False, None # Approval failed
        else:
            if self.bot.verbose:
                print(f"✅ {token_name} NO already approved for Router")

        # --- Simulation Checkpoint ---
        if simulate:
            print(f"✅ Simulation successful: Sufficient balances and approvals (or would be requested) for merging {amount} {token_symbol}.")
            return True, None

        print(f"\n📝 Merging {amount} {token_name} YES/NO back into {token_name}...")

        try:
            # Build transaction
            tx_params = {
                'from': self.bot.address,
                'nonce': self.bot.w3.eth.get_transaction_count(self.bot.address),
                'gas': 500000,  # Adjust gas limit if needed
                'gasPrice': self.bot.w3.eth.gas_price,
                'chainId': self.bot.w3.eth.chain_id,
            }
            tx = self.bot.futarchy_router.functions.mergePositions(
                self.bot.w3.to_checksum_address(CONTRACT_ADDRESSES["market"]),
                self.bot.w3.to_checksum_address(base_token_address),
                amount_wei
            ).build_transaction(tx_params)

            # Sign and send transaction
            signed_tx = self.bot.w3.eth.account.sign_transaction(tx, self.bot.account.key)
            tx_hash = self.bot.w3.eth.send_raw_transaction(get_raw_transaction(signed_tx))

            print(f"\n⏳ Merge transaction sent: {tx_hash.hex()}")
            print(f"Transaction: https://gnosisscan.io/tx/{tx_hash.hex()}")

            # Wait for transaction confirmation
            receipt = self.bot.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            if receipt['status'] == 1:
                if self.bot.verbose:
                    # Check new base token balance (optional)
                    base_token_contract = self.bot.get_token_contract(base_token_address)
                    new_balance = base_token_contract.functions.balanceOf(self.bot.address).call()
                    print(f"\n✅ Successfully merged {token_name}!")
                    print(f"New {token_name} balance: {self.bot.w3.from_wei(new_balance, 'ether')}")
                else:
                    print(f"\n✅ Successfully merged {amount} {token_name} YES/NO back into {token_name}!")
                return True, tx_hash.hex()
            else:
                print(f"❌ Merge transaction failed! Status: {receipt['status']}")
                print(f"Check transaction details at: https://gnosisscan.io/tx/{tx_hash.hex()}")
                return False, tx_hash.hex()

        except Exception as e:
            print(f"❌ Error merging {token_name} positions: {e}")
            traceback.print_exc()
            return False, None 