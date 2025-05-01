import os
import requests
from typing import List
from web3 import Web3

BASE = "https://api.tenderly.co/api/v1"


class TenderlyClient:
    def __init__(self, w3: Web3):
        self.w3 = w3
        self.key = os.environ["TENDERLY_ACCESS_KEY"]
        self.account = os.environ["TENDERLY_ACCOUNT_SLUG"]
        self.project = os.environ["TENDERLY_PROJECT_SLUG"]
        self.url = f"{BASE}/account/{self.account}/project/{self.project}/simulate-bundle"
        self.headers = {
            "X-Access-Key": self.key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ---------- helpers ----------

    def build_tx(self, to: str, data: str, sender: str, gas: int = 3_000_000, value: str = "0"):
        return {
            "network_id": str(self.w3.eth.chain_id),
            "from": sender,
            "to": to,
            "input": data,
            "gas": gas,
            "value": value,
        }

    def encode_exact_in(self, router, params):
        return router.encodeABI(fn_name="exactInputSingle", args=[params])

    def encode_exact_out(self, router, params):
        return router.encodeABI(fn_name="exactOutputSingle", args=[params])

    # ---------- core ----------

    def simulate(self, txs: List[dict]):
        """Simulate a bundle of transactions on Tenderly.

        Each transaction is enriched with flags that instruct Tenderly to persist
        the simulation to the dashboard, regardless of success or failure. We
        also specify ``simulation_type`` = "full" to get full traces and decoded
        logs in the response and UI.
        """
        enriched_txs = [
            {
                **tx,
                "save": True,
                "save_if_fails": True,
                "simulation_type": "full",
            }
            for tx in txs
        ]

        payload = {"simulations": enriched_txs}

        print("--- Sending to Tenderly ---")
        print(f"URL: {self.url}")
        print(f"Headers: {self.headers}")
        print(f"Payload: {payload}")

        response = requests.post(self.url, json=payload, headers=self.headers)

        print("--- Received from Tenderly ---")
        print(f"Status Code: {response.status_code}")

        try:
            return response.json()
        except requests.exceptions.JSONDecodeError:
            print("ERROR: Could not decode JSON response from Tenderly.")
            return None
