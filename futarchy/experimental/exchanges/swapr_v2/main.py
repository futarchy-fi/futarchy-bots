import os, time
from decimal import Decimal
from eth_account import Account
from .swapr_swap import w3, client, tx_exact_in, tx_exact_out

acct = Account.from_key(os.environ["PRIVATE_KEY"])

token_in  = w3.to_checksum_address(os.environ["SWAPR_GNO_YES_ADDRESS"])
token_out = w3.to_checksum_address(os.environ["SWAPR_SDAI_YES_ADDRESS"])

deadline          = int(time.time()) + 600
amount_in_wei     = w3.to_wei(Decimal("0.001"), "ether")
amount_in_max     = int(amount_in_wei * 1.2)
amount_out_expected = int(amount_in_wei * 81)
amount_out_min    = int(amount_out_expected * 0.9)
sqrt_price_limit  = 0

params_in  = (token_in, token_out, acct.address, deadline, amount_in_wei,
              amount_out_min, sqrt_price_limit)
params_out = (token_in, token_out, 500, acct.address, deadline,
              amount_out_expected, amount_in_max, sqrt_price_limit)

bundle = [
    tx_exact_in(params_in,  acct.address),
    tx_exact_out(params_out, acct.address),
]

print(f"--- Prepared Bundle ---")
print(bundle)

result = client.simulate(bundle)

# --- Simple parsing of simulation results ---
if result and result.get("simulation_results"):
    sims = result["simulation_results"]
    param_list = [params_in, params_out]

    for idx, swap_result in enumerate(sims):
        print(f"\n--- Simulation Result #{idx+1} ---")

        if swap_result.get("error"):
            print("Tenderly simulation error:", swap_result["error"].get("message", "Unknown error"))
            print("Full error details:", swap_result["error"])
            continue

        tx = swap_result.get("transaction")
        if not tx:
            print("No transaction data in result.")
            continue

        if tx.get("status") is False:
            tx_info = tx.get("transaction_info", {})
            print("Swap transaction REVERTED.")
            print("  Revert reason:", tx_info.get("error_message", tx_info.get("revert_reason", "N/A")))
            continue

        # Successful transaction
        print("Swap transaction did NOT revert.")
        tx_info = tx.get("transaction_info", {})
        call_trace = tx_info.get("call_trace", {})
        output_hex = call_trace.get("output")

        if output_hex and output_hex != "0x":
            amount_out_wei = int(output_hex, 16)
            # pick corresponding params tuple if available
            if idx < len(param_list):
                amount_in_wei_local = param_list[idx][4]
            else:
                amount_in_wei_local = amount_in_wei  # fallback

            print("  Simulated amountOut:", w3.from_wei(amount_out_wei, "ether"), token_out)
            price = Decimal(w3.from_wei(amount_out_wei, "ether")) / Decimal(w3.from_wei(amount_in_wei_local, "ether"))
            print("  Simulated price:", price, f"{token_out}/{token_in}")
        else:
            print("  No output data returned from simulation.")
else:
    print("Simulation failed or returned no results.")
