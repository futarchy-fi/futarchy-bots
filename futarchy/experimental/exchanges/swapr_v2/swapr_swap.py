import os
from web3 import Web3
# NOTE: Assuming the ABI location is correct relative to the new structure
from futarchy.experimental.config.abis.swapr import SWAPR_ROUTER_ABI 
from .tenderly_api import TenderlyClient

w3 = Web3(Web3.HTTPProvider(os.environ["RPC_URL"]))

router_addr = w3.to_checksum_address(os.environ["SWAPR_ROUTER_ADDRESS"])
router = w3.eth.contract(address=router_addr, abi=SWAPR_ROUTER_ABI)

client = TenderlyClient(w3)


def tx_exact_in(params, sender):
    data = client.encode_exact_in(router, params)
    return client.build_tx(router.address, data, sender)


def tx_exact_out(params, sender):
    data = client.encode_exact_out(router, params)
    return client.build_tx(router.address, data, sender)
