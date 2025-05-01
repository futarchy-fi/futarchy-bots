import os
import time
from decimal import Decimal
from web3 import Web3
from .tenderly_api import TenderlyAPIClient
from .swap_transaction import build_swap_tx
import json

# --- Import ABIs ---
# Use absolute import path from project root
from futarchy.experimental.config.abis.swapr import SWAPR_ROUTER_ABI, ALGEBRA_POOL_ABI

web3 = Web3(Web3.HTTPProvider(os.getenv("RPC_URL")))
router_address = web3.to_checksum_address(os.environ.get("SWAPR_ROUTER_ADDRESS"))
router = web3.eth.contract(address=router_address, abi=SWAPR_ROUTER_ABI)

def simulate_swap(account, params_tuple, exact_in=True):
    """
    Simulates and potentially executes a swap based on input parameters.
    params_tuple: (address, address, address, uint256, uint256, uint256, uint160)
    """
    # The params_tuple is now passed directly
    token_in_addr = params_tuple[0]
    token_out_addr = params_tuple[1]
    recipient_addr = params_tuple[2]
    amount_in_wei = params_tuple[4]

    # --- Determine Pool Address --- 
    token_in_addr_cs = web3.to_checksum_address(token_in_addr)
    token_out_addr_cs = web3.to_checksum_address(token_out_addr)
    pool_address = None

    # Get conditional token addresses from env for matching
    # Assuming these env vars hold the *token* addresses, not pool addresses
    sdai_yes_token = os.environ.get("SWAPR_SDAI_YES_ADDRESS") # Token Address
    sdai_no_token = os.environ.get("SWAPR_SDAI_NO_ADDRESS")   # Token Address
    gno_yes_token = os.environ.get("SWAPR_GNO_YES_ADDRESS")    # Token Address
    gno_no_token = os.environ.get("SWAPR_GNO_NO_ADDRESS")     # Token Address

    sdai_yes_token_cs = web3.to_checksum_address(sdai_yes_token) if sdai_yes_token else None
    sdai_no_token_cs = web3.to_checksum_address(sdai_no_token) if sdai_no_token else None
    gno_yes_token_cs = web3.to_checksum_address(gno_yes_token) if gno_yes_token else None
    gno_no_token_cs = web3.to_checksum_address(gno_no_token) if gno_no_token else None

    # Use YES pool if either token is a conditional YES token
    if (token_in_addr_cs in [sdai_yes_token_cs, gno_yes_token_cs] or 
        token_out_addr_cs in [sdai_yes_token_cs, gno_yes_token_cs]):
        swapr_pool_yes = os.environ.get("SWAPR_POOL_YES_ADDRESS") # Pool Address
        if swapr_pool_yes:
            pool_address = web3.to_checksum_address(swapr_pool_yes)
            print(f"INFO: Determined YES pool address: {pool_address}")
    # Use NO pool if either token is a conditional NO token
    elif (token_in_addr_cs in [sdai_no_token_cs, gno_no_token_cs] or 
          token_out_addr_cs in [sdai_no_token_cs, gno_no_token_cs]):
        swapr_pool_no = os.environ.get("SWAPR_POOL_NO_ADDRESS") # Pool Address
        if swapr_pool_no:
            pool_address = web3.to_checksum_address(swapr_pool_no)
            print(f"INFO: Determined NO pool address: {pool_address}")
    
    if not pool_address:
        print(f"ERROR: Could not determine Swapr pool address for token pair: {token_in_addr_cs} <-> {token_out_addr_cs}")
        print("Ensure SWAPR_POOL_YES_ADDRESS or SWAPR_POOL_NO_ADDRESS environment variables are set correctly.")
        exit(1)
        
    # Initialize the pool contract object *after* finding the address
    pool_contract = web3.eth.contract(address=pool_address, abi=ALGEBRA_POOL_ABI)
    # --- End Determine Pool Address ---

    # Initialize Tenderly Client
    try:
        tenderly_client = TenderlyAPIClient()
    except ValueError as e:
        print(f"Error initializing Tenderly client: {e}")
        exit(1)

    # --- Build Simulation Bundle --- 
    print("Building simulation bundle...")

    if exact_in:
        encoded_swap_input = router.encodeABI(fn_name="exactInputSingle", args=[params_tuple])
    else:
        encoded_swap_input = router.encodeABI(fn_name="exactOutputSingle", args=[params_tuple])

    tx_swap_sim = {
        "network_id": str(web3.eth.chain_id),
        "from": account.address, # Use passed account object
        "to": router.address, # Target the router contract
        "input": encoded_swap_input,
        "gas": 3000000, # Generous gas limit for swap simulation
        "value": "0",
        "save": True, # Optional: Save to Tenderly dashboard
        "save_if_fails": True, # Optional: Save even if it fails
    }

    # Add this print statement
    print("--- tx_swap_sim inside simulate_swap (before calling simulate_single) ---")
    print(json.dumps(tx_swap_sim, indent=2))
    print("-----------------------------------------------------------------------")

    # --- Simulate SINGLE Transaction using Tenderly Client --- 
    print("Simulating SINGLE transaction with Tenderly...")
    # Call the new simulate_single method with only the swap transaction
    results = tenderly_client.simulate_single(tx_swap_sim)

    # --- Process SINGLE Simulation Result --- 
    # The response structure for /simulate is different: it returns the result directly
    if results: 
        swap_result = results # The result object itself
        
        # Check for Tenderly simulation error field first
        if swap_result.get('error'):
             print(f"Tenderly simulation error: {swap_result['error'].get('message', 'Unknown error')}")
             print(f"Full error details: {swap_result['error']}")
        # Check if the transaction itself reverted during simulation
        # The structure might be nested under 'transaction' and 'transaction_info'
        elif swap_result.get('transaction') and swap_result['transaction'].get('status') is False:
             print("Simulation successful, but swap transaction REVERTED.")
             tx_info = swap_result['transaction'].get('transaction_info', {})
             print(f"  Revert reason: {tx_info.get('error_message', tx_info.get('revert_reason', 'N/A'))}")
        # Check for successful simulation (transaction didn't revert)
        elif swap_result.get('transaction') and swap_result['transaction'].get('status') is True:
            print("Simulation successful and swap transaction did NOT revert.")
            # Process successful swap simulation
            output_hex = None
            try:
                # Navigate the structure carefully
                tx_info = swap_result.get('transaction', {}).get('transaction_info', {})
                call_trace = tx_info.get('call_trace', {})
                output_hex = call_trace.get('output')
            except AttributeError:
                 print("  Could not access nested output data in simulation result.")

            if output_hex and output_hex != "0x":
                print(f"  Raw output hex: {output_hex}") # Print the raw hex found

                if exact_in:
                    # For exactInput, output is amountOut, input amount is known
                    amount_out_wei = int(output_hex, 16)
                    amount_in_wei = params_tuple[5] # amountIn is the 6th element (index 5)
                    print(f"  Simulated amountOut: {web3.from_wei(amount_out_wei, 'ether')} {token_out_addr}")
                else:
                    # For exactOutput, output is amountIn, output amount is known
                    amount_in_wei = int(output_hex, 16)
                    amount_out_wei = params_tuple[5] # amountOut is the 6th element (index 5)
                    print(f"  Simulated amountIn: {web3.from_wei(amount_in_wei, 'ether')} {token_in_addr}")

                amount_out_whole = web3.from_wei(amount_out_wei, 'ether')
                amount_in_whole = web3.from_wei(amount_in_wei, 'ether')

                # Use Decimal for precision, especially for price
                amount_in_decimal = Decimal(amount_in_whole)
                amount_out_decimal = Decimal(amount_out_whole)

                price = amount_out_decimal / amount_in_decimal if amount_in_decimal != Decimal(0) else None
                print(f"  Simulated price: {price} {token_out_addr}/{token_in_addr}")

                return {
                    'success': True,
                    'amount_in': amount_in_decimal,
                    'amount_out': amount_out_decimal,
                    'price': price
                }
            else:
                print("  No output data returned from simulation.")
        else:
             # Unexpected response structure
             print("Simulation returned an unexpected structure. Cannot determine success/failure.")

    else:
        print("Simulation failed or returned no results.")
        # Error logging is handled within tenderly_client.simulate_single

def execute_swap(account, params_tuple):
    tx = build_swap_tx(web3, router, account, params_tuple)
    signed_tx = account.sign_transaction(tx)
    tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt


if __name__ == "__main__":
    # web3.auto is deprecated, avoid using it if web3 is already initialized
    # from web3.auto import w3 
    from eth_account import Account
    import dotenv
    dotenv.load_dotenv()

    # Debug: Print environment variables
    priv_key = os.getenv("PRIVATE_KEY")
    token_in_addr = os.getenv("SWAPR_GNO_YES_ADDRESS")
    token_out_addr = os.getenv("SWAPR_SDAI_YES_ADDRESS")
    print(f"DEBUG: PRIVATE_KEY: {'Set' if priv_key else 'Not Set'}") # Avoid printing the key itself
    print(f"DEBUG: TOKEN_IN_ADDRESS: {token_in_addr}")
    print(f"DEBUG: TOKEN_OUT_ADDRESS: {token_out_addr}")

    # Add check for None before proceeding
    if not priv_key or not token_in_addr or not token_out_addr:
        print("\nERROR: Required environment variables (PRIVATE_KEY, TOKEN_IN_ADDRESS, TOKEN_OUT_ADDRESS) must be set.")
        import sys
        sys.exit(1) # Exit gracefully instead of crashing
        
    account = Account.from_key(priv_key)
    amount_in = 0.000000001  # Example swap amount

    # Prepare parameters correctly according to ABI
    token_in_checksum = web3.to_checksum_address(token_in_addr)
    token_out_checksum = web3.to_checksum_address(token_out_addr)
    recipient_checksum = account.address # Already checksummed by Account object
    deadline = int(time.time()) + 300 # Example deadline 5 mins from now
    amount_in_wei = web3.to_wei(Decimal(str(amount_in)), 'ether')
    amount_in_wei_maximum = int(amount_in_wei*1.1)
    amount_out_wei = 83988380025
    amount_out_minimum = int(amount_out_wei*0.9)
    sqrt_price_limit_x96 = 0 # For simulation/basic swap
    fee = 500

    # Construct the tuple matching exactInputSingle signature
    params_tuple_exact_in = (
        token_in_checksum,
        token_out_checksum,
        recipient_checksum,
        deadline,
        amount_in_wei,
        amount_out_minimum,
        sqrt_price_limit_x96
    )

    params_tuple_exact_out = (
        token_in_checksum,
        token_out_checksum,
        fee,
        recipient_checksum,
        deadline,
        amount_out_wei,
        amount_in_wei_maximum,
        sqrt_price_limit_x96
    )



    print(f"\nAttempting simulation for {amount_in} {token_in_addr} -> {token_out_addr}...")
    # Pass the correctly structured tuple
    print(simulate_swap(account, params_tuple_exact_in, exact_in=True))
    print(simulate_swap(account, params_tuple_exact_out, exact_in=False))

    # Pass the correctly structured tuple to execute_swap as well
    # receipt = execute_swap(account, params_tuple)
    # print(f"Executed swap: {receipt.transactionHash.hex()}")
    print("\nNOTE: Actual swap execution is commented out in main.py.")
