import os
import time
from decimal import Decimal
from web3 import Web3
from .tenderly_api import TenderlyAPIClient
from .swap_transaction import build_swap_tx

# --- Import ABIs ---
# Use absolute import path from project root
from futarchy.experimental.config.abis.swapr import SWAPR_ROUTER_ABI, ALGEBRA_POOL_ABI

web3 = Web3(Web3.HTTPProvider(os.getenv("RPC_URL")))
router_address = web3.to_checksum_address(os.environ.get("SWAPR_ROUTER_ADDRESS"))
router = web3.eth.contract(address=router_address, abi=SWAPR_ROUTER_ABI)


def simulate_swap_exact_in(params_tuple):
    pass