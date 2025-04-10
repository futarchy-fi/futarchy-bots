# Test script focused only on simulate_swap_exact_in
import os
from web3 import Web3
from decimal import Decimal
from dotenv import load_dotenv
# Removed Account import as private key not needed for simulation

# Adjust these imports based on your project structure
from ...exchanges.swapr.swap import SwaprV3Handler
from ...services.tenderly_client import TenderlySimulationClient
# Assume you have a way to load necessary config/constants
from ...config.constants import (
    CONTRACT_ADDRESSES, 
    ERC20_ABI, 
)

# Removed get_raw_transaction import

# --- Configuration ---
load_dotenv() # Load environment variables from .env file
RPC_URL = os.environ.get("RPC_URL") # Load RPC_URL from environment
if not RPC_URL:
    print("⚠️ RPC_URL environment variable not set. Please ensure .env is sourced or variable is exported.")

BOT_ADDRESS = os.environ.get("BOT_ADDRESS")
if not BOT_ADDRESS:
    print("⚠️ BOT_ADDRESS environment variable not set.")
    
# Removed PRIVATE_KEY loading

SDAI_YES_ADDRESS = os.environ.get("SDAI_YES_ADDRESS")
if not SDAI_YES_ADDRESS:
    print("⚠️ SDAI_YES_ADDRESS environment variable not set.")

GNO_YES_ADDRESS = os.environ.get("GNO_YES_ADDRESS")
if not GNO_YES_ADDRESS:
    print("⚠️ GNO_YES_ADDRESS environment variable not set.")
    # exit()

# Removed SWAPR_* address loading as they are not used

# --- Add Tenderly Credentials --- 
TENDERLY_ACCESS_KEY = os.environ.get("TENDERLY_ACCESS_KEY")
TENDERLY_ACCOUNT_SLUG = os.environ.get("TENDERLY_ACCOUNT_SLUG")
TENDERLY_PROJECT_SLUG = os.environ.get("TENDERLY_PROJECT_SLUG")
# --- End Tenderly Credentials --- 

# --- Mock Bot Context ---
# Simplified for simulation only
class MockFutarchyBot:
    def __init__(self, w3_instance, address):
        self.w3 = w3_instance
        self.address = w3_instance.to_checksum_address(address) 
        self.account = None # Not needed for simulation
        self.verbose = True # Enable verbose logging from the handler
        
    # Removed approve_token method

# --- Test Parameters ---
# Use the correct conditional token pair that worked for the user
TOKEN_IN_ADDR = SDAI_YES_ADDRESS
TOKEN_OUT_ADDR = GNO_YES_ADDRESS
AMOUNT_IN = 0.0000002 # Match user's successful amount

# Renamed main function to reflect simulation focus
def run_simulation_only_test(): 
    print(f"Attempting to connect to Gnosis Chain RPC: {RPC_URL}...") # Debug
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print(f"❌ Failed to connect to Web3 provider at {RPC_URL}.")
        return

    print(f"Connected! Chain ID: {w3.eth.chain_id}")

    print("Initializing MockFutarchyBot (Simulation Mode)...") # Debug
    # Create mock bot context (no private key needed)
    mock_bot = MockFutarchyBot(w3, BOT_ADDRESS)

    # --- Initialize and Attach Tenderly Client --- 
    if all([TENDERLY_ACCESS_KEY, TENDERLY_ACCOUNT_SLUG, TENDERLY_PROJECT_SLUG]):
        print("Initializing TenderlySimulationClient...")
        try:
            tenderly_client = TenderlySimulationClient(
                access_key=TENDERLY_ACCESS_KEY,
                account_slug=TENDERLY_ACCOUNT_SLUG,
                project_slug=TENDERLY_PROJECT_SLUG,
                web3_provider_url=RPC_URL # Use the same RPC URL for Tenderly's Web3 needs
            )
            mock_bot.tenderly_client = tenderly_client # Attach client to the bot
            print("TenderlySimulationClient initialized and attached to mock_bot.")
        except Exception as e:
            print(f"❌ Error initializing TenderlySimulationClient: {e}")
            # Decide if you want to exit or just warn
            # return 
    else:
        print("⚠️ Tenderly credentials not fully set in environment. Skipping Tenderly client initialization.")
        mock_bot.tenderly_client = None # Explicitly set to None
    # --- End Tenderly Client Initialization --- 

    print("MockFutarchyBot initialized.") # Debug

    print("Initializing SwaprV3Handler...") # Debug
    # Initialize the handler
    try:
        swapr_handler = SwaprV3Handler(mock_bot)
        print("SwaprV3Handler initialized.") # Debug
    except Exception as e:
        print(f"❌ Error initializing SwaprV3Handler: {e}")
        return

    print(f"\n--- Testing simulate_swap_exact_in ---")
    print(f"Simulating Swap: {AMOUNT_IN} {TOKEN_IN_ADDR} for {TOKEN_OUT_ADDR}")

    print("Calling simulate_swap_exact_in...") # Debug
    sim_result = swapr_handler.simulate_swap_exact_in(
        token_in_addr=TOKEN_IN_ADDR,
        token_out_addr=TOKEN_OUT_ADDR,
        amount_in=AMOUNT_IN
    )
    print(f"Raw simulation result dictionary: {sim_result}") # Debug

    print("\n--- Simulation Result ---")
    if sim_result and sim_result.get('success'):
        print(f"✅ Simulation successful!")
        sim_amount_out = sim_result.get('simulated_amount_out', 0)
        est_price = sim_result.get('estimated_price', 0)
        print(f"   Estimated Amount Out: {sim_amount_out:.8f} {TOKEN_OUT_ADDR}")
        if est_price > 0:
             # Display price as TOKEN_OUT per TOKEN_IN
             print(f"   Estimated Price: {1/Decimal(est_price):.6f} {TOKEN_OUT_ADDR} per {TOKEN_IN_ADDR}") 
        else:
             print(f"   Estimated Price: N/A (zero output)")
    else:
        print(f"❌ Simulation failed!")
        print(f"   Error: {sim_result.get('error', 'Unknown error')}")

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
    # Removed PRIVATE_KEY check
    elif not SDAI_YES_ADDRESS:
         print(f"❌ SDAI_YES_ADDRESS not found in environment.")
    elif not GNO_YES_ADDRESS:
         print(f"❌ GNO_YES_ADDRESS not found in environment.")
    # --- Add Tenderly Env Var Checks ---
    elif not TENDERLY_ACCESS_KEY:
        print(f"❌ TENDERLY_ACCESS_KEY not found in environment.")
    elif not TENDERLY_ACCOUNT_SLUG:
        print(f"❌ TENDERLY_ACCOUNT_SLUG not found in environment.")
    elif not TENDERLY_PROJECT_SLUG:
        print(f"❌ TENDERLY_PROJECT_SLUG not found in environment.")
    # --- End Tenderly Env Var Checks ---
    # Removed SWAPR_* address checks
    else:
        run_simulation_only_test() # Call the simulation-specific function 