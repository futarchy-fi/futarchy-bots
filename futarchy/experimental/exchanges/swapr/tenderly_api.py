import os
import requests
import json
from typing import List, Dict, Any, Optional

class TenderlyAPIClient:
    """
    A client for interacting with the Tenderly simulate-bundle API endpoint.
    Reads configuration from environment variables.
    """
    BASE_API_URL = "https://api.tenderly.co/api/v1"

    def __init__(self):
        """
        Initializes the TenderlyAPIClient, loading configuration from environment variables.
        """
        self.access_key = os.environ.get("TENDERLY_ACCESS_KEY")
        self.account_slug = os.environ.get("TENDERLY_ACCOUNT_SLUG")
        self.project_slug = os.environ.get("TENDERLY_PROJECT_SLUG")

        if not all([self.access_key, self.account_slug, self.project_slug]):
            raise ValueError(
                "Tenderly environment variables not set: "
                "TENDERLY_ACCESS_KEY, TENDERLY_ACCOUNT_SLUG, TENDERLY_PROJECT_SLUG"
            )

        self.simulate_bundle_url = (
            f"{self.BASE_API_URL}/account/{self.account_slug}"
            f"/project/{self.project_slug}/simulate-bundle"
        )

        self.headers = {
            "Accept": "application/json",
            "X-Access-Key": self.access_key,
            "Content-Type": "application/json"
        }
        print(f"Tenderly Client Initialized. URL: {self.simulate_bundle_url}")


    def _post_request(self, url: str, payload: Dict[str, Any], timeout: int = 60) -> Optional[Dict[str, Any]]:
        """
        Internal method to handle POST requests and basic error checking.
        """
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=timeout)
            # response.raise_for_status()

            response_data = response.json()

            # Check for the specific {'simulation_results': None} case
            if response_data == {'simulation_results': None}:
                # Provide context-specific error message
                if "/simulate-bundle" in url:
                    print(f"Tenderly API (bundle endpoint) returned 'simulation_results: null'. This might indicate an issue with the request or a Tenderly-side error.")
                elif "/simulate" in url:
                     print(f"Tenderly API (single simulate endpoint) unexpectedly returned 'simulation_results: null'. This usually indicates an internal error or invalid request format for single simulation.")
                else:
                     print(f"Tenderly API unexpectedly returned 'simulation_results: null' from URL: {url}")
                     
                # Log details regardless of endpoint
                print("--- Request details leading to this response ---")
                print(f"URL: {url}")
                print(f"Headers: {{'Accept': '{self.headers.get('Accept')}', 'Content-Type': '{self.headers.get('Content-Type')}'}}")
                print(f"Payload: {json.dumps(payload)}")
                print("--- End Request details ---")
                return None # Indicate failure

            # Check for explicit error field in response (common pattern)
            if isinstance(response_data, dict) and "error" in response_data:
                print(f"Tenderly API returned an error: {response_data['error']}")
                return None

            # Check for the expected response
            return response_data

        except requests.exceptions.RequestException as e:
            print(f"Error simulating bundle: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    print(f"Response status code: {e.response.status_code}")
                    print(f"Response content: {e.response.text}")
                except Exception:
                    print("Could not parse error response details.")
            return None
        except json.JSONDecodeError as e:
             print(f"Error decoding JSON response from Tenderly: {e}")
             print(f"Raw response text: {response.text}")
             return None


    def simulate_bundle(self, transactions: List[Dict[str, Any]], timeout: int = 60) -> Optional[List[Dict[str, Any]]]:
        """
        Sends a bundle of transactions to the Tenderly API for simulation.

        Args:
            transactions: A list of transaction dictionaries to simulate.
            timeout: Request timeout in seconds (default: 60).

        Returns:
            A list of simulation result dictionaries if successful, otherwise None.
            Parses the 'results' key from the Tenderly response.
        """
        payload = {"transactions": transactions}
        print(f"Sending simulation bundle to {self.simulate_bundle_url}")
        response_data = self._post_request(self.simulate_bundle_url, payload, timeout)

        if response_data is None:
            return None

        # Check for the expected 'results' key
        if "results" in response_data:
            return response_data["results"]
        else:
            # If 'results' key is missing and no other known error pattern matched
            print(f"Unexpected Tenderly response format. 'results' key not found.")
            print(f"Raw response: {response_data}")
            return None


    def simulate_single(self, transaction: Dict[str, Any], timeout: int = 60) -> Optional[Dict[str, Any]]:
        """
        Sends a single transaction to the Tenderly API for simulation.

        Args:
            transaction: A transaction dictionary to simulate.
            timeout: Request timeout in seconds (default: 60).

        Returns:
            A simulation result dictionary if successful, otherwise None.
        """
        url = f"{self.BASE_API_URL}/account/{self.account_slug}/project/{self.project_slug}/simulate"
        payload = transaction
        print(f"Sending single simulation to {url}")
        return self._post_request(url, payload, timeout)


# --- Example Usage (Optional, can be removed or kept for testing) ---
if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        print("Loading environment variables from .env file...")
        dotenv_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env_proposal')
        print(f"Looking for .env at: {os.path.abspath(dotenv_path)}")
        loaded = load_dotenv(dotenv_path=dotenv_path, override=True)
        if loaded:
            print(".env file loaded successfully.")
        else:
            print("Warning: .env file not found or empty.")
            if not all([os.environ.get("TENDERLY_ACCESS_KEY"), os.environ.get("TENDERLY_ACCOUNT_SLUG"), os.environ.get("TENDERLY_PROJECT_SLUG")]):
                 print("Error: Required Tenderly variables not found in environment either.")
                 exit(1)
            else:
                 print("Found required Tenderly variables in existing environment.")

    except ImportError:
        print("dotenv library not installed (`pip install python-dotenv`). Cannot load .env file.")
        if not all([os.environ.get("TENDERLY_ACCESS_KEY"), os.environ.get("TENDERLY_ACCOUNT_SLUG"), os.environ.get("TENDERLY_PROJECT_SLUG")]):
             print("Error: Required Tenderly variables not found in environment either.")
             exit(1)
        else:
             print("Found required Tenderly variables in existing environment.")


    try:
        client = TenderlyAPIClient()

        example_tx = {
            "network_id": "100", 
            "from": "0xYOUR_ADDRESS", 
            "to": "0x...", 
            "input": "0x...", 
            "gas": 3000000,
            "value": "0"
        }

        print("\nAttempting to simulate bundle...")
        results = client.simulate_bundle(transactions=[example_tx])

        if results:
            print("\n--- Simulation Results ---")
            print(json.dumps(results, indent=2))
        else:
            print("\n--- Simulation Failed ---")

        print("\nAttempting to simulate single transaction...")
        result = client.simulate_single(transaction=example_tx)

        if result:
            print("\n--- Simulation Result ---")
            print(json.dumps(result, indent=2))
        else:
            print("\n--- Simulation Failed ---")

    except ValueError as e:
        print(f"Error initializing client: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
