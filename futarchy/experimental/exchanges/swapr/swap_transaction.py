import time
from web3 import Web3
from web3.contract.contract import Contract
from eth_account.signers.local import LocalAccount

def build_swap_tx(web3: Web3, router_contract: Contract, account: LocalAccount, params_tuple: tuple, gas_limit=500000):
    # params_tuple now matches the exactInputSingle signature:
    # (address tokenIn, address tokenOut, address recipient, uint256 deadline, 
    #  uint256 amountIn, uint256 amountOutMinimum, uint160 sqrtPriceLimitX96)
    tx = router_contract.functions.exactInputSingle(params_tuple).build_transaction({
        'from': account.address,
        'nonce': web3.eth.get_transaction_count(account.address),
        'chainId': web3.eth.chain_id,
        'gas': gas_limit,
        'gasPrice': web3.eth.gas_price, # Consider using maxFeePerGas/maxPriorityFeePerGas for EIP-1559
    })
    return tx

def sign_and_send(web3, account, transaction):
    signed_tx = web3.eth.account.sign_transaction(transaction, account.key)
    tx_hash = web3.eth.send_raw_transaction(signed_tx.rawTransaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt
