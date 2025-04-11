# Example test script (e.g., save as test_swapr_sim.py)
import os
from web3 import Web3
from decimal import Decimal
from dotenv import load_dotenv
from eth_account import Account

# Adjust these imports based on your project structure
from ...exchanges.swapr.swap import SwaprV3Handler
# Assume you have a way to load necessary config/constants
from ...config.constants import (
    CONTRACT_ADDRESSES, 
    ERC20_ABI, 
)

# Need this for sending raw tx
from ...utils.web3_utils import get_raw_transaction

# --- Configuration ---
load_dotenv() # Load environment variables from .env file
RPC_URL = os.environ.get("RPC_URL") # Load RPC_URL from environment
if not RPC_URL:
    print("⚠️ RPC_URL environment variable not set. Please ensure .env is sourced or variable is exported.")

BOT_ADDRESS = os.environ.get("BOT_ADDRESS")
if not BOT_ADDRESS:
    print("⚠️ BOT_ADDRESS environment variable not set.")
    
SWAPR_SDAI_YES_ADDRESS = os.environ.get("SWAPR_SDAI_YES_ADDRESS")
if not SWAPR_SDAI_YES_ADDRESS:
    print("⚠️ SWAPR_SDAI_YES_ADDRESS environment variable not set.")

SWAPR_GNO_YES_ADDRESS = os.environ.get("SWAPR_GNO_YES_ADDRESS")
if not SWAPR_GNO_YES_ADDRESS:
    print("⚠️ SWAPR_GNO_YES_ADDRESS environment variable not set.")
    # Consider exiting or handling this case appropriately
    # exit()

SDAI_YES_ADDRESS = os.environ.get("SDAI_YES_ADDRESS")
if not SDAI_YES_ADDRESS:
    print("⚠️ SDAI_YES_ADDRESS environment variable not set.")

GNO_YES_ADDRESS = os.environ.get("GNO_YES_ADDRESS")
if not GNO_YES_ADDRESS:
    print("⚠️ GNO_YES_ADDRESS environment variable not set.")
    # exit()

PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
if not PRIVATE_KEY:
    print("⚠️ PRIVATE_KEY environment variable not set.")

# --- Mock Bot Context ---
# You might need a more sophisticated mock or a real instance
class MockFutarchyBot:
    def __init__(self, w3_instance, address, private_key):
        self.w3 = w3_instance
        # The simulation needs a 'from' address, even if no tx is sent
        self.address = w3_instance.to_checksum_address(address) 
        if private_key:
            self.account = Account.from_key(private_key)
            # Verify address matches key
            if self.account.address.lower() != self.address.lower():
                print(f"⚠️ WARNING: Provided BOT_ADDRESS {self.address} does not match PRIVATE_KEY address {self.account.address}")
        else:
            self.account = None
        self.verbose = True # Enable verbose logging from the handler
        
    def approve_token(self, token_contract, spender_address, amount_wei):
        """Builds, signs, and sends a real ERC20 approve transaction."""
        if not self.account:
            print("❌ [Approve] Cannot approve token: Private key not provided.")
            return False

        try:
            print(f"   [Approve] Building approval tx: spender={spender_address}, amount={amount_wei}, token={token_contract.address}")
            nonce = self.w3.eth.get_transaction_count(self.address)
            gas_price = self.w3.eth.gas_price
            # Estimate gas for approval
            try:
                gas_estimate = token_contract.functions.approve(spender_address, amount_wei).estimate_gas({
                    'from': self.address,
                    'nonce': nonce,
                })
                gas_estimate = int(gas_estimate * 1.2) # Add buffer
                print(f"   [Approve] Gas estimate: {gas_estimate}")
            except Exception as estimate_err:
                print(f"   [Approve] ⚠️ Gas estimation failed: {estimate_err}. Using default: 100000")
                gas_estimate = 100000
                
            tx_params = {
                'from': self.address,
                'nonce': nonce,
                'gas': gas_estimate,
                'gasPrice': gas_price,
                'chainId': self.w3.eth.chain_id, # Use chain ID from connection
            }

            approve_tx = token_contract.functions.approve(spender_address, amount_wei).build_transaction(tx_params)
            print(f"   [Approve] Signing transaction...")
            signed_tx = self.w3.eth.account.sign_transaction(approve_tx, self.account.key)
            print(f"   [Approve] Sending transaction...")
            tx_hash = self.w3.eth.send_raw_transaction(get_raw_transaction(signed_tx))
            print(f"   [Approve] Tx sent: {tx_hash.hex()}. Waiting for receipt...")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            print(f"   [Approve] Receipt received. Status: {receipt.status}")
            if receipt.status != 1:
                 print(f"   [Approve] ❌ Approval transaction failed on-chain. Hash: {tx_hash.hex()}")
                 return False
            print(f"   [Approve] ✅ Approval successful. Tx: {tx_hash.hex()}")
            return True
        except Exception as e:
            print(f"   [Approve] ❌ Error during approval transaction: {e}")
            import traceback
            traceback.print_exc()
            return False

# --- Test Parameters ---
# Example: Simulate swapping WETH for GNO on Gnosis Chain
# Replace with actual checksummed addresses if different
# Ensure these keys exist in your CONTRACT_ADDRESSES dict
# Use specific conditional token addresses from .env
TOKEN_IN_ADDR = SDAI_YES_ADDRESS
TOKEN_OUT_ADDR = GNO_YES_ADDRESS
AMOUNT_IN = 0.2 # Match user's successful amount

# Use a placeholder 'from' address for simulation purposes
# It doesn't need funds for simulation via .call()
SIMULATE_FROM_ADDRESS = BOT_ADDRESS

def run_simulation_test():
    print(f"Attempting to connect to Gnosis Chain RPC: {RPC_URL}...") # Debug
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print(f"❌ Failed to connect to Web3 provider at {RPC_URL}.")
        return

    print(f"Connected! Chain ID: {w3.eth.chain_id}")

    print("Initializing MockFutarchyBot...") # Debug
    # Create mock bot context
    mock_bot = MockFutarchyBot(w3, BOT_ADDRESS, PRIVATE_KEY)
    print("MockFutarchyBot initialized.") # Debug

    print("Initializing SwaprV3Handler...") # Debug
    # Initialize the handler
    try:
        swapr_handler = SwaprV3Handler(mock_bot)
        print("SwaprV3Handler initialized.") # Debug
    except Exception as e:
        print(f"❌ Error initializing SwaprV3Handler: {e}")
        return

    print(f"\n--- Testing swap_exact_in ---")
    print(f"Swapping {AMOUNT_IN} {TOKEN_IN_ADDR} for {TOKEN_OUT_ADDR}")

    print("Calling swap_exact_in...") # Changed from simulate
    exec_result = swapr_handler.swap_exact_in(
        token_in_addr=TOKEN_IN_ADDR,
        token_out_addr=TOKEN_OUT_ADDR,
        amount_in=AMOUNT_IN
    )
    print(f"Raw execution result dictionary: {exec_result}") # Debug

    print("\n--- Execution Result ---")
    if exec_result and exec_result.get('success'):
        print(f"✅ Swap successful! (Based on receipt status)")
        tx_hash = exec_result.get('tx_hash')
        print(f"   Transaction Hash: {tx_hash}")
        if tx_hash:
            print(f"   GnosisScan: https://gnosisscan.io/tx/{tx_hash}")
        # Note: Actual amount out is not available without parsing logs or pre-simulation
    else:
        print(f"❌ Swap failed or reverted!")
        print(f"   Error: {exec_result.get('error', 'Unknown error')}")
        tx_hash = exec_result.get('tx_hash')
        if tx_hash:
             print(f"   Failed Tx Hash: {tx_hash}")
             print(f"   GnosisScan: https://gnosisscan.io/tx/{tx_hash}")

if __name__ == "__main__":
    # Basic checks before running
    if not RPC_URL:
         print("❌ RPC_URL not found in environment. Please source .env or export RPC_URL.")
    elif not isinstance(CONTRACT_ADDRESSES, dict) or not CONTRACT_ADDRESSES:
         print("❌ CONTRACT_ADDRESSES not loaded correctly from constants.")
    elif not ERC20_ABI: # Example check, ensure necessary ABIs like ERC20 are loaded if needed by test
         print("❌ Required ABIs (e.g., ERC20_ABI) not loaded from constants.")
    # Check if the keys were found in CONTRACT_ADDRESSES
    elif not BOT_ADDRESS:
         print(f"❌ BOT_ADDRESS not found in environment.")
    elif not SWAPR_SDAI_YES_ADDRESS:
         print(f"❌ SWAPR_SDAI_YES_ADDRESS not found in environment.")
    elif not SWAPR_GNO_YES_ADDRESS:
         print(f"❌ SWAPR_GNO_YES_ADDRESS not found in environment.")
    elif not SDAI_YES_ADDRESS:
         print(f"❌ SDAI_YES_ADDRESS not found in environment.")
    elif not GNO_YES_ADDRESS:
         print(f"❌ GNO_YES_ADDRESS not found in environment.")
    elif not PRIVATE_KEY:
         print(f"❌ PRIVATE_KEY not found in environment.")
    else:
        run_simulation_test() 