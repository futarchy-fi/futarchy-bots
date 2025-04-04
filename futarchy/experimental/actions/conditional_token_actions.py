import os
import math
from futarchy.experimental.exchanges.passthrough_router import PassthroughRouter
from futarchy.experimental.config.constants import (
    CONTRACT_ADDRESSES,
    TOKEN_CONFIG,
    UNISWAP_V3_POOL_ABI,
    UNISWAP_V3_PASSTHROUGH_ROUTER_ABI
)
# Import the helper function
from futarchy.experimental.utils.web3_utils import get_raw_transaction
# TODO: Add FutarchyBot type hint if available
# from futarchy.experimental.core.futarchy_bot import FutarchyBot

def sell_sdai_yes(bot, amount): # Add type hint: bot: FutarchyBot
    """
    Sell sDAI-YES tokens for sDAI.

    Args:
        bot: FutarchyBot instance
        amount: Amount of sDAI-YES to sell
    """
    # Function to floor a number to 6 decimal places
    def floor_to_6(val):
        str_val = str(float(val))
        if '.' in str_val:
            integer_part, decimal_part = str_val.split('.')
            decimal_part = decimal_part[:6]
            return float(f"{integer_part}.{decimal_part}")
        return float(val)

    amount = float(round(float(amount), 6))
    print(f"\n🔄 Selling {amount:.6f} sDAI-YES for sDAI...")

    balances = bot.get_balances()
    sdai_yes_balance = balances['currency']['yes']
    sdai_balance = balances['currency']['wallet']

    sdai_yes_display = floor_to_6(sdai_yes_balance)
    sdai_display = floor_to_6(sdai_balance)

    print("Balance before swap:")
    print(f"sDAI-YES: {sdai_yes_display:.6f}")
    print(f"sDAI: {sdai_display:.6f}")

    pool_address = bot.w3.to_checksum_address(CONTRACT_ADDRESSES["sdaiYesPool"])
    pool_contract = bot.w3.eth.contract(address=pool_address, abi=UNISWAP_V3_POOL_ABI)
    slot0 = pool_contract.functions.slot0().call()
    current_sqrt_price = slot0[0]
    print(f"Current pool sqrtPriceX96: {current_sqrt_price}")

    token0 = pool_contract.functions.token0().call()
    token1 = pool_contract.functions.token1().call()
    print(f"Pool token0: {token0}")
    print(f"Pool token1: {token1}")
    print(f"sDAI-YES: {TOKEN_CONFIG['currency']['yes_address']}")
    print(f"sDAI: {TOKEN_CONFIG['currency']['address']}")

    price = (current_sqrt_price ** 2) / (2 ** 192)
    print(f"Current price: {price:.6f} (price of token1 in terms of token0)")

    sdai_yes_address = TOKEN_CONFIG['currency']['yes_address'].lower()
    sdai_address = TOKEN_CONFIG['currency']['address'].lower()

    if token0.lower() == sdai_yes_address and token1.lower() == sdai_address:
        print(f"Pool order: token0=sDAI-YES, token1=sDAI")
        print(f"This means 1 sDAI-YES = {1/price:.6f} sDAI")
        zero_for_one = True
        sqrt_price_limit_x96 = int(current_sqrt_price * 0.95)
        print(f"Using price limit of 95% of current price: {sqrt_price_limit_x96}")
    elif token0.lower() == sdai_address and token1.lower() == sdai_yes_address:
        print(f"Pool order: token0=sDAI, token1=sDAI-YES")
        print(f"This means 1 sDAI-YES = {price:.6f} sDAI")
        zero_for_one = False
        sqrt_price_limit_x96 = int(current_sqrt_price * 1.05)
        print(f"Using price limit of 105% of current price: {sqrt_price_limit_x96}")
    else:
        print(f"⚠️ Unexpected token configuration in the pool")
        return False

    if float(sdai_yes_balance) < float(amount):
        print(f"❌ Insufficient balance of sDAI-YES tokens.")
        print(f"   Required: {amount:.6f}")
        print(f"   Available: {sdai_yes_display:.6f}")
        return False

    router = PassthroughRouter(
        bot.w3,
        os.environ.get("PRIVATE_KEY"),
        os.environ.get("V3_PASSTHROUGH_ROUTER_ADDRESS")
    )

    success = router.execute_swap(
        pool_address=pool_address,
        token_in=TOKEN_CONFIG["currency"]["yes_address"],
        token_out=TOKEN_CONFIG["currency"]["address"],
        amount=amount,
        zero_for_one=zero_for_one,
        sqrt_price_limit_x96=sqrt_price_limit_x96
    )

    if success:
        print("✅ Swap successful!")
        updated_balances = bot.get_balances()
        sdai_yes_balance_float = float(sdai_yes_balance)
        updated_sdai_yes_balance_float = float(updated_balances['currency']['yes'])
        sdai_balance_float = float(sdai_balance)
        updated_sdai_balance_float = float(updated_balances['currency']['wallet'])

        sdai_yes_change = updated_sdai_yes_balance_float - sdai_yes_balance_float
        sdai_change = updated_sdai_balance_float - sdai_balance_float

        print("\nBalance Changes:")
        print(f"sDAI-YES: {sdai_yes_change:+.6f}")
        print(f"sDAI: {sdai_change:+.6f}")

        if sdai_yes_change != 0:
            effective_price = abs(float(sdai_change) / float(sdai_yes_change))
            effective_percent = effective_price * 100
            event_probability = bot.get_sdai_yes_probability()
            event_percent = event_probability * 100

            print(f"\nEffective price: {effective_price:.6f} sDAI per sDAI-YES ({effective_percent:.2f}%)")
            print(f"Current pool price ratio: {event_probability:.6f} ({event_percent:.2f}%)")

            price_diff_pct = ((effective_price / event_probability) - 1) * 100 if event_probability != 0 else float('inf')
            print(f"Price difference from pool: {price_diff_pct:.2f}%")

        bot.print_balances(updated_balances)
        return True
    else:
        print("❌ Swap failed!")
        return False

def buy_sdai_yes(bot, amount_in_sdai): # Add type hint: bot: FutarchyBot
    """
    Buy sDAI-YES tokens using sDAI directly from the sDAI/sDAI-YES pool.

    Args:
        bot: FutarchyBot instance
        amount_in_sdai (float): Amount of sDAI to use for buying sDAI-YES
    """
    def floor_to_6(num):
        if hasattr(num, 'is_finite') and num.is_finite():
            num = float(num)
        return math.floor(num * 1e6) / 1e6

    amount_in_sdai = float(amount_in_sdai)
    print(f"\n🔄 Buying sDAI-YES with {amount_in_sdai:.6f} sDAI...")

    balances = bot.get_balances()
    sdai_balance = balances['currency']['wallet']
    sdai_yes_balance = balances['currency']['yes']
    print("Balance before swap:")
    print(f"sDAI-YES: {sdai_yes_balance}")
    print(f"sDAI: {sdai_balance}")

    if float(sdai_balance) < amount_in_sdai:
        print(f"❌ Insufficient sDAI balance. You have {sdai_balance} sDAI, but need {amount_in_sdai} sDAI.")
        return False

    pool_address = CONTRACT_ADDRESSES["sdaiYesPool"]
    print(f"Using sDAI/sDAI-YES pool: {pool_address}")

    account = bot.account.address

    router_address = CONTRACT_ADDRESSES["uniswapV3PassthroughRouter"]
    router = bot.w3.eth.contract(
        address=bot.w3.to_checksum_address(router_address),
        abi=UNISWAP_V3_PASSTHROUGH_ROUTER_ABI
    )
    print(f"Using router: {router_address}")

    pool_contract = bot.w3.eth.contract(
        address=bot.w3.to_checksum_address(pool_address),
        abi=UNISWAP_V3_POOL_ABI
    )

    token0_address = bot.w3.to_checksum_address(pool_contract.functions.token0().call())
    token1_address = bot.w3.to_checksum_address(pool_contract.functions.token1().call())
    print(f"Pool token0: {token0_address}")
    print(f"Pool token1: {token1_address}")

    sdai_address = bot.w3.to_checksum_address(TOKEN_CONFIG["currency"]["address"])
    sdai_yes_address = bot.w3.to_checksum_address(TOKEN_CONFIG["currency"]["yes_address"])
    print(f"sDAI address: {sdai_address}")
    print(f"sDAI-YES address: {sdai_yes_address}")

    if token0_address.lower() == sdai_yes_address.lower() and token1_address.lower() == sdai_address.lower():
        zero_for_one = False
        print("sDAI-YES is token0, sDAI is token1 => using zero_for_one=FALSE to buy sDAI-YES with sDAI")
    elif token0_address.lower() == sdai_address.lower() and token1_address.lower() == sdai_yes_address.lower():
        zero_for_one = True
        print("sDAI is token0, sDAI-YES is token1 => using zero_for_one=TRUE to buy sDAI-YES with sDAI")
    else:
        print(f"❌ Pool does not contain the expected tokens.")
        print(f"Expected tokens: sDAI ({sdai_address}) and sDAI-YES ({sdai_yes_address})")
        print(f"Pool tokens: token0 ({token0_address}) and token1 ({token1_address})")
        return False

    try:
        slot0 = pool_contract.functions.slot0().call()
        current_sqrt_price_x96 = slot0[0]
        print(f"Current pool sqrtPriceX96: {current_sqrt_price_x96}")

        if zero_for_one:
            price_limit = int(current_sqrt_price_x96 * 0.8)
        else:
            price_limit = int(current_sqrt_price_x96 * 1.2)
        print(f"Using price limit of {'80%' if zero_for_one else '120%'} of current price: {price_limit}")

        print(f"\n🔑 Authorizing pool for router...")
        try:
            tx = router.functions.authorizePool(pool_address).build_transaction({
                'from': account,
                'gas': 500000,
                'gasPrice': bot.w3.eth.gas_price,
                'nonce': bot.w3.eth.get_transaction_count(account),
                'chainId': bot.w3.eth.chain_id,
            })
            # Standardize signing
            signed_tx = bot.w3.eth.account.sign_transaction(tx, bot.account.key)
            # Use helper function to get raw transaction bytes
            tx_hash = bot.w3.eth.send_raw_transaction(get_raw_transaction(signed_tx))
            receipt = bot.w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 1:
                print(f"✅ Pool authorization successful!")
            else:
                print(f"⚠️ Pool authorization failed. But this may be because it's already authorized.")
        except Exception as e:
            print(f"⚠️ Pool authorization error: {e}. But we'll continue as it might already be authorized.")

        # First test with a small amount
        test_amount = min(amount_in_sdai * 0.1, 1e-5)
        print(f"\n🧪 Testing with small amount ({test_amount} sDAI) first...")
        test_amount_wei = bot.w3.to_wei(test_amount, 'ether')

        try:
            token_to_approve = sdai_address # We are always spending sDAI in this function
            # Get contract instance before approving
            token_contract_instance = bot.get_token_contract(token_to_approve)
            bot.approve_token(token_contract_instance, router_address, test_amount_wei)
        except Exception as e:
            print(f"⚠️ Error in token approval: {e}")
            print("Continuing anyway as it might be approved already...")

        amount_specified = test_amount_wei
        empty_bytes = b''

        tx = router.functions.swap(
            pool_address,
            account,
            zero_for_one,
            amount_specified,
            price_limit,
            empty_bytes
        ).build_transaction({
            'from': account,
            'gas': 500000,
            'gasPrice': bot.w3.eth.gas_price,
            'nonce': bot.w3.eth.get_transaction_count(account),
            'chainId': bot.w3.eth.chain_id,
        })
        # Standardize signing
        signed_tx = bot.w3.eth.account.sign_transaction(tx, bot.account.key)
        # Use helper function to get raw transaction bytes
        tx_hash = bot.w3.eth.send_raw_transaction(get_raw_transaction(signed_tx))
        receipt = bot.w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status != 1:
            print(f"❌ Test swap failed. See transaction for details.")
            print(f"Consider using the split_sdai command to split sDAI into YES/NO tokens at 1:1 ratio.")
            return False
        print(f"✅ Test swap successful!")

        print(f"\n💱 Executing swap with {amount_in_sdai} sDAI...")
        amount_wei = bot.w3.to_wei(amount_in_sdai, 'ether')

        try:
            token_to_approve = sdai_address # We are always spending sDAI in this function
            token_contract_instance = bot.get_token_contract(token_to_approve)
            bot.approve_token(token_contract_instance, router_address, amount_wei)
        except Exception as e:
            print(f"⚠️ Error in token approval: {e}")
            print("Continuing anyway as it might be approved already...")
            
        # Fetch the pending nonce explicitly
        current_nonce = bot.w3.eth.get_transaction_count(account, 'pending')
        print(f"Using nonce: {current_nonce}")

        tx = router.functions.swap(
            pool_address,
            account,
            zero_for_one,
            amount_wei,
            price_limit,
            empty_bytes
        ).build_transaction({
            'from': account,
            'gas': 500000,
            'gasPrice': bot.w3.eth.gas_price,
            'nonce': current_nonce, # Use the fetched pending nonce
            'chainId': bot.w3.eth.chain_id,
        })

        # Standardize signing
        signed_tx = bot.w3.eth.account.sign_transaction(tx, bot.account.key)
        # Use helper function to get raw transaction bytes
        tx_hash = bot.w3.eth.send_raw_transaction(get_raw_transaction(signed_tx))
        receipt = bot.w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            print(f"✅ Swap successful!")
            print(f"Transaction hash: {tx_hash.hex()}")

            try:
                updated_balances = bot.get_balances()
                new_sdai_balance = updated_balances['currency']['wallet']
                new_sdai_yes_balance = updated_balances['currency']['yes']

                sdai_balance_float = float(sdai_balance)
                new_sdai_balance_float = float(new_sdai_balance)
                sdai_yes_balance_float = float(sdai_yes_balance)
                new_sdai_yes_balance_float = float(new_sdai_yes_balance)

                sdai_spent = floor_to_6(sdai_balance_float - new_sdai_balance_float)
                sdai_yes_gained = floor_to_6(new_sdai_yes_balance_float - sdai_yes_balance_float)

                print("\n📊 Swap Summary:")
                print(f"sDAI spent: {sdai_spent}")
                print(f"sDAI-YES gained: {sdai_yes_gained}")

                if sdai_spent > 0 and sdai_yes_gained > 0:
                    effective_price = sdai_spent / sdai_yes_gained
                    print(f"Effective price: {effective_price:.6f} sDAI per sDAI-YES")
                else:
                    print("Effective price: Unable to calculate (no sDAI spent or no sDAI-YES gained)")

                probability = bot.get_sdai_yes_probability()
                print(f"Current pool price ratio: {probability:.6f}")
                bot.print_balances(updated_balances)
                return True
            except Exception as e:
                print(f"⚠️ Error calculating swap summary: {e}")
                print("But the swap was successful!")
                return True
        else:
            print(f"❌ Swap failed. See transaction for details.")
            return False

    except Exception as e:
        print(f"❌ Error during swap: {e}")
        # Check if the error suggests pool authorization might be the issue
        if "Pool not authorized" in str(e) or "Pool authorization error" in str(e):
            print("The pool might require authorization. Try running the authorize command if available.")
        else:
            print(f"The pool may have low liquidity or the parameters are incorrect.")
            print(f"Consider using the split_sdai command to split sDAI into YES/NO tokens at 1:1 ratio.")
        return False 