import requests
import json
import os
from typing import List, Dict, Any, Optional

# Optional: Requires web3.py for ABI encoding helper
try:
    from web3 import Web3
    from web3.contract import Contract
    from dotenv import load_dotenv # Added for example usage
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False
    # Define dummy types if web3 is not installed,
    # so the type hints still work
    class Web3: pass
    class Contract: pass
    # Define load_dotenv if it wasn't imported
    def load_dotenv(): print("Warning: dotenv not installed, cannot load .env in example")

class TenderlySimulationClient:
    """
    A reusable client for interacting with the Tenderly simulate-bundle API endpoint.

    This client facilitates sending bundled transactions for simulation
    and handles ABI encoding for transaction input data if web3.py is installed.

    Note: This implementation specifically excludes the 'state_objects' parameter
    for state overrides, as per the requirement.
    """

    BASE_API_URL = "https://api.tenderly.co/api/v1"

    def __init__(self, access_key: str, account_slug: str, project_slug: str, web3_provider_url: Optional[str] = None):
        """
        Initializes the TenderlySimulationClient.

        Args:
            access_key: Your Tenderly API Access Key.
            account_slug: Your Tenderly account or organization slug.
            project_slug: Your Tenderly project slug.
            web3_provider_url: Optional URL for a Web3 provider (e.g., Infura, Alchemy, or local node)
                               required for ABI encoding helper method.
        """
        if not all([access_key, account_slug, project_slug]):
            raise ValueError("Tenderly access key, account slug, and project slug are required.")

        self.access_key = access_key
        self.account_slug = account_slug
        self.project_slug = project_slug

        self.simulate_bundle_url = (
            f"{self.BASE_API_URL}/account/{self.account_slug}"
            f"/project/{self.project_slug}/simulate-bundle"
        )

        self.headers = {
            "Accept": "application/json",
            "X-Access-Key": self.access_key
            # Content-Type: application/json is added automatically by requests when using json=payload
        }

        self.w3: Optional[Web3] = None
        if WEB3_AVAILABLE and web3_provider_url:
            try:
                self.w3 = Web3(Web3.HTTPProvider(web3_provider_url))
                if not self.w3.is_connected():
                    print(f"Warning: Could not connect to Web3 provider at {web3_provider_url}")
                    self.w3 = None
            except Exception as e:
                print(f"Warning: Failed to initialize Web3 with provider {web3_provider_url}. ABI encoding helper will not work. Error: {e}")
                self.w3 = None
        elif not WEB3_AVAILABLE and web3_provider_url:
            print("Warning: web3.py library not found. ABI encoding helper method (`encode_input`) requires 'pip install web3'.")


    def encode_input(self, abi: List[Dict[str, Any]], function_name: str, args: List[Any]) -> Optional[str]:
        """
        Helper method to ABI-encode function call data using web3.py.

        Requires web3.py to be installed and a valid web3_provider_url
        to have been provided during initialization.

        Args:
            abi: The contract ABI (list of dictionaries).
            function_name: The name of the function to call.
            args: A list of arguments for the function call.

        Returns:
            The hex-encoded input data string (e.g., "0x..."), or None if encoding fails
            or web3 is unavailable.
        """
        if not self.w3:
            print("Error: Web3 provider not available or not connected. Cannot encode input.")
            return None
        if not WEB3_AVAILABLE:
             print("Error: web3.py library not installed. Cannot encode input.")
             return None

        print(f"[encode_input] Called for function: {function_name}") # DEBUG
        print(f"[encode_input] Args: {args}") # DEBUG
        print(f"[encode_input] Type of self.w3: {type(self.w3)}") # DEBUG
        print(f"[encode_input] Is self.w3 connected: {self.w3.is_connected() if self.w3 else 'N/A'}") # DEBUG

        try:
            print("[encode_input] Trying to create temp contract...") # DEBUG
            temp_contract = self.w3.eth.contract(abi=abi)
            print(f"[encode_input] Type of temp_contract: {type(temp_contract)}") # DEBUG

            # --- Alternative Encoding --- 
            print(f"[encode_input] Trying to get function '{function_name}' by name...") # DEBUG
            func_obj = temp_contract.get_function_by_name(function_name)
            print(f"[encode_input] Type of func_obj: {type(func_obj)}") # DEBUG
            print(f"[encode_input] Trying to call func_obj with args...") # DEBUG
            # Build the transaction data using the function object
            encoded_data = func_obj(*args)._encode_transaction_data()
            # --- End Alternative Encoding ---

            # print(f"[encode_input] Trying to call temp_contract.encodeABI...") # DEBUG
            # # Now encode the function call using this temporary instance
            # encoded_data = temp_contract.encodeABI(fn_name=function_name, args=args)
            print(f"[encode_input] Encoding successful: {encoded_data}") # DEBUG
            return encoded_data
        except Exception as e:
            # Print the specific error during encoding for better debugging
            print(f"Error encoding function '{function_name}' with args {args}: {e}")
            # You might want to raise the exception here or log it more formally depending on your needs
            # raise e
            return None

    def build_transaction(self, network_id: str, from_address: str, to_address: str,
                          gas: int, value: str = "0", input_data: str = "0x",
                          save: bool = False, save_if_fails: bool = False,
                          simulation_type: str = "full") -> Dict[str, Any]:
        """
        Constructs a dictionary representing a single transaction for the simulation bundle.

        Note: This helper does NOT include 'state_objects'.

        Args:
            network_id: The target network ID (e.g., "1" for Mainnet, "100" for Gnosis).
            from_address: The sender address.
            to_address: The recipient address (contract or EOA).
            gas: The gas limit for the transaction.
            value: The native currency amount in Wei (string). Defaults to "0".
            input_data: The hex-encoded transaction data. Defaults to "0x".
            save: Whether to save the simulation to the Tenderly dashboard. Defaults to False.
            save_if_fails: Save even if reverted (requires save=True). Defaults to False.
            simulation_type: Simulation detail ("full", "quick", "abi"). Defaults to "full".

        Returns:
            A dictionary representing the transaction payload.
        """
        tx = {
            "network_id": str(network_id),
            "from": from_address,
            "to": to_address,
            "input": input_data,
            "gas": gas,
            "value": value,
            "save": save,
            "simulation_type": simulation_type,
            # state_objects is intentionally omitted
        }
        if save and save_if_fails:
            tx["save_if_fails"] = save_if_fails

        # Ensure gas is an integer for JSON serialization if it isn't already
        tx["gas"] = int(tx["gas"])

        return tx


    def simulate_bundle(self, transactions: List[Dict[str, Any]], timeout: int = 60) -> Optional[List[Dict[str, Any]]]:
        """
        Sends a bundle of transactions to the Tenderly API for simulation.

        Args:
            transactions: A list of transaction dictionaries. Each dictionary
                          should conform to the Tenderly API specification for a
                          single simulation object within the 'simulations' array
                          (as created by `build_transaction` or manually).
                          The order in the list defines the execution order.
            timeout: Request timeout in seconds. Defaults to 60.

        Returns:
            A list containing the parsed JSON response objects for each simulation
            in the bundle, mirroring the input order. Returns None if the API
            request fails.
        """
        if not transactions:
            print("Error: No transactions provided for simulation.")
            return None

        api_payload = {"simulations": transactions}

        print(f"Sending simulation request for {len(transactions)} transactions to: {self.simulate_bundle_url}")
        # Uncomment for deep debugging:
        # print(f"Payload: {json.dumps(api_payload, indent=2)}")

        try:
            response = requests.post(
                self.simulate_bundle_url,
                headers=self.headers,
                json=api_payload, # requests handles Content-Type and JSON serialization
                timeout=timeout
            )
            response.raise_for_status() # Raises HTTPError for 4xx/5xx responses

            print(f"API Response Status Code: {response.status_code}")
            simulation_results = response.json()

            # Basic validation: Expecting a list in response containing simulation objects
            # The API returns a dictionary like {"simulation_results": [...] }
            if isinstance(simulation_results, dict) and 'simulation_results' in simulation_results:
                 results_list = simulation_results['simulation_results']
                 if isinstance(results_list, list):
                     print(f"Successfully received results for {len(results_list)} simulations.")
                     return results_list # Return the list of simulation results
                 else:
                     print(f"Error: Unexpected format for 'simulation_results'. Expected a list, got {type(results_list)}.")
                     print(f"Response Body: {simulation_results}")
                     return None
            elif isinstance(simulation_results, list):
                 # Handle cases where the API might just return a list directly (less common based on docs)
                 print(f"Successfully received results for {len(simulation_results)} simulations (direct list response).")
                 return simulation_results
            else:
                 print(f"Error: Unexpected API response format. Expected a list, got {type(simulation_results)}.")
                 print(f"Response Body: {simulation_results}")
                 return None


        except requests.exceptions.Timeout:
            print(f"Error: API request timed out after {timeout} seconds.")
            return None
        except requests.exceptions.HTTPError as e:
            print(f"Error: HTTP Error {e.response.status_code} calling Tenderly API.")
            try:
                # Try to print the error response from Tenderly
                print(f"Response Body: {e.response.json()}")
            except json.JSONDecodeError:
                print(f"Response Body: {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Error: API Request failed: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during simulation: {e}")
            return None

# --- Example Usage ---

if __name__ == "__main__":
    # --- Configuration (Load securely, e.g., from environment variables) ---
    TENDERLY_ACCESS_KEY = os.environ.get("TENDERLY_ACCESS_KEY")
    TENDERLY_ACCOUNT_SLUG = os.environ.get("TENDERLY_ACCOUNT_SLUG") # Your account/org slug
    TENDERLY_PROJECT_SLUG = os.environ.get("TENDERLY_PROJECT_SLUG") # Your project slug
    # Optional: Web3 provider URL needed for client.encode_input() helper
    WEB3_PROVIDER_URL = os.environ.get("WEB3_PROVIDER_URL", None) # e.g., "https://mainnet.infura.io/v3/YOUR_INFURA_KEY"

    if not all([TENDERLY_ACCESS_KEY, TENDERLY_ACCOUNT_SLUG, TENDERLY_PROJECT_SLUG]):
        print("Error: Set TENDERLY_ACCESS_KEY, TENDERLY_ACCOUNT_SLUG, and TENDERLY_PROJECT_SLUG environment variables.")
        exit(1)

    # --- Initialize the Client ---
    # If you need ABI encoding, provide a web3_provider_url
    client = TenderlySimulationClient(
        access_key=TENDERLY_ACCESS_KEY,
        account_slug=TENDERLY_ACCOUNT_SLUG,
        project_slug=TENDERLY_PROJECT_SLUG,
        web3_provider_url=WEB3_PROVIDER_URL # Set to None if not using encode_input
    )

    # --- Define Transaction Details (Example: Approve WETH and Wrap ETH on Mainnet) ---
    USER_ADDRESS = "0xd8dA6BF26964aF9D7eEd9e03e53415D37aA96045" # Example: Vitalik's address
    WETH_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
    SOME_SPENDER = "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D" # Example: Uniswap V2 Router
    NETWORK_ID = "1" # Ethereum Mainnet

    # Example ERC20 ABI subset for approve and deposit (WETH)
    WETH_ABI = [
        {"constant": False, "inputs": [{"name": "guy", "type": "address"}, {"name": "wad", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "payable": False, "stateMutability": "nonpayable", "type": "function"},
        {"constant": False, "inputs": [], "name": "deposit", "outputs": [], "payable": True, "stateMutability": "payable", "type": "function"}
    ]

    # --- Transaction 1: Approve WETH spending ---
    amount_to_approve = Web3.to_wei(1, 'ether') if WEB3_AVAILABLE else 1 * 10**18 # 1 WETH in Wei
    approve_input_data = None
    if client.w3: # Check if Web3 is available and connected
        approve_input_data = client.encode_input(
            abi=WETH_ABI,
            function_name="approve",
            args=[SOME_SPENDER, amount_to_approve]
        )

    if approve_input_data:
        tx1_approve = client.build_transaction(
            network_id=NETWORK_ID,
            from_address=USER_ADDRESS,
            to_address=WETH_ADDRESS,
            gas=100000,
            input_data=approve_input_data,
            save=True # Optional: Save to dashboard for inspection
        )
    else:
        print("Skipping Approve Tx: Could not encode input data (Web3 unavailable or encoding failed).")
        tx1_approve = None # Indicate failure to create tx

    # --- Transaction 2: Wrap 0.5 ETH into WETH ---
    amount_to_wrap_wei_str = str(Web3.to_wei(0.5, 'ether') if WEB3_AVAILABLE else int(0.5 * 10**18))
    deposit_input_data = None
    if client.w3: # Check if Web3 is available and connected
         deposit_input_data = client.encode_input(
             abi=WETH_ABI,
             function_name="deposit",
             args=[] # Deposit takes no arguments, ETH is sent via 'value'
         )

    if deposit_input_data:
         tx2_wrap_eth = client.build_transaction(
             network_id=NETWORK_ID,
             from_address=USER_ADDRESS,
             to_address=WETH_ADDRESS,
             gas=100000,
             value=amount_to_wrap_wei_str, # Sending 0.5 ETH
             input_data=deposit_input_data,
             save=True
         )
    else:
         print("Skipping Wrap ETH Tx: Could not encode input data (Web3 unavailable or encoding failed).")
         tx2_wrap_eth = None # Indicate failure to create tx

    # --- Assemble the Bundle ---
    # Filter out any transactions that failed to be created (e.g., due to encoding issues)
    simulation_bundle = [tx for tx in [tx1_approve, tx2_wrap_eth] if tx is not None]

    # --- Execute the Simulation ---
    if simulation_bundle:
        results = client.simulate_bundle(simulation_bundle)

        # --- Process Results ---
        if results:
            print("\n--- Simulation Results ---")
            print(json.dumps(results, indent=2))

            # Example: Check status of each transaction
            print("\n--- Transaction Status Summary ---")
            all_succeeded = True
            for i, tx_result in enumerate(results):
                tx_status = tx_result.get('status', False)
                print(f"  Transaction {i+1}: {'Success' if tx_status else 'Failed'}")
                if not tx_status:
                    all_succeeded = False
                    error_info = tx_result.get('error_info') or tx_result.get('error')
                    print(f"    Reason: {error_info}")
                    break # Bundle simulation stops on first failure

            if all_succeeded:
                print("\nBundle simulated successfully!")
            else:
                print("\nBundle simulation failed.")
        else:
            print("Simulation execution failed.")
    else:
        print("No valid transactions were created for the simulation bundle.")
