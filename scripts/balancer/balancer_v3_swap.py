import json
import os
import time
import traceback
from web3 import Web3
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_account.messages import encode_typed_data
from dotenv import load_dotenv
from eth_utils import to_hex, encode_hex

# Load environment variables
load_dotenv()

# Connect to Gnosis Chain
rpc_url = os.getenv('GNOSIS_RPC_URL')
w3 = Web3(Web3.HTTPProvider(rpc_url))

# Enable debug mode
DEBUG = True

def debug_print(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")

# Check connection
if not w3.is_connected():
    print("❌ Failed to connect to Gnosis Chain")
    exit(1)

print(f"✅ Connected to Gnosis Chain (Chain ID: {w3.eth.chain_id})")

# Load private key
private_key = os.getenv('PRIVATE_KEY')
if not private_key:
    print("❌ No private key found in .env file")
    exit(1)

account: LocalAccount = Account.from_key(private_key)
address = account.address
print(f"🔑 Using account: {address}")

# Contract addresses
BATCH_ROUTER_ADDRESS = w3.to_checksum_address('0xe2fa4e1d17725e72dcdafe943ecf45df4b9e285b')
SDAI_ADDRESS = w3.to_checksum_address('0xaf204776c7245bF4147c2612BF6e5972Ee483701')
WAGNO_ADDRESS = w3.to_checksum_address('0x7c16F0185A26Db0AE7a9377f23BC18ea7ce5d644')
SDAI_WAGNO_POOL_ADDRESS = w3.to_checksum_address('0xD1D7Fa8871d84d0E77020fc28B7Cd5718C446522')
PERMIT2_ADDRESS = w3.to_checksum_address('0x000000000022D473030F116dDEE9F6B43aC78BA3')

# Load contract ABIs
with open('config/batch_router_abi.json', 'r') as f:
    batch_router_abi = json.load(f)

with open('config/permit2_abi.json', 'r') as f:
    permit2_abi = json.load(f)

# Initialize contracts
batch_router = w3.eth.contract(address=BATCH_ROUTER_ADDRESS, abi=batch_router_abi)
permit2 = w3.eth.contract(address=PERMIT2_ADDRESS, abi=permit2_abi)

# ERC20 ABI with balanceOf and other needed functions
erc20_abi = [
    {
        "inputs": [{"name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Initialize token contracts
sdai_token = w3.eth.contract(address=SDAI_ADDRESS, abi=erc20_abi)
wagno_token = w3.eth.contract(address=WAGNO_ADDRESS, abi=erc20_abi)

# Check sDAI balance
sdai_balance = sdai_token.functions.balanceOf(address).call()
print(f"💰 sDAI Balance: {w3.from_wei(sdai_balance, 'ether')}")

# Check WAGNO balance
wagno_balance = wagno_token.functions.balanceOf(address).call()
print(f"💰 WAGNO Balance before swap: {w3.from_wei(wagno_balance, 'ether')}")

# Amount to swap (0.3904 sDAI)
amount_to_swap = w3.to_wei(0.3904, 'ether')

if sdai_balance < amount_to_swap:
    print("❌ Insufficient sDAI balance")
    exit(1)

try:
    print("\n1. Verifying swap path from sDAI to WAGNO...")
    
    # Define the swap path
    swap_paths = [{
        'tokenIn': SDAI_ADDRESS,
        'steps': [
            {
                'pool': SDAI_WAGNO_POOL_ADDRESS,
                'tokenOut': WAGNO_ADDRESS,
                'isBuffer': False
            }
        ],
        'exactAmountIn': amount_to_swap,
        'minAmountOut': 0  # Set to 0 for testing, calculate in production
    }]
    
    # Query the expected output
    debug_print("About to call querySwapExactIn...")
    expected_output = batch_router.functions.querySwapExactIn(
        swap_paths,
        address,
        '0x'  # empty user data
    ).call()
    
    debug_print(f"querySwapExactIn output: {expected_output}")
    
    print(f"\nSwap query successful!")
    
    if expected_output and expected_output[0]:
        expected_amount_out = expected_output[0][0]
        print(f"✅ Expected WAGNO output: {w3.from_wei(expected_amount_out, 'ether')} WAGNO")
        
        # Let's set a lower minAmountOut (80% of expected) to account for price movement
        min_amount_out = int(expected_amount_out * 0.8)
        swap_paths[0]['minAmountOut'] = min_amount_out
        print(f"Setting minAmountOut to 80% of expected: {w3.from_wei(min_amount_out, 'ether')} WAGNO")
        
        # First check if we already have approval through standard ERC20
        print("\n2. Checking if SDAI is already approved for BatchRouter...")
        
        # Check current approval through standard ERC20
        current_allowance = sdai_token.functions.allowance(
            address,
            BATCH_ROUTER_ADDRESS
        ).call()
        
        if current_allowance >= amount_to_swap:
            print(f"✅ SDAI already approved for BatchRouter ({w3.from_wei(current_allowance, 'ether')} approved)")
            
            # Use standard swapExactIn directly
            print("\n3. Executing swap with existing approval...")
            
            # Set a longer deadline (1 hour from now) to ensure it doesn't expire
            deadline = w3.eth.get_block('latest')['timestamp'] + (10 * 60)
            debug_print(f"Setting deadline to: {deadline}")
            
            # Get the latest gas price and increase it
            gas_price = w3.eth.gas_price
            max_fee_per_gas = int(gas_price * 2)  # Double the current gas price
            max_priority_fee_per_gas = int(gas_price * 1.5)  # 1.5x the current gas price
            
            debug_print(f"Current gas price: {gas_price}")
            debug_print(f"Setting maxFeePerGas to: {max_fee_per_gas}")
            debug_print(f"Setting maxPriorityFeePerGas to: {max_priority_fee_per_gas}")
            
            # Get latest nonce
            nonce = w3.eth.get_transaction_count(address)
            debug_print(f"Using nonce: {nonce}")
            
            # Estimate gas for the transaction
            try:
                estimated_gas = batch_router.functions.swapExactIn(
                    swap_paths,
                    deadline,
                    False,  # wethIsEth
                    '0x'    # userData
                ).estimate_gas({
                    'from': address,
                    'nonce': nonce,
                })
                debug_print(f"Estimated gas: {estimated_gas}")
                # Add 50% buffer to the estimated gas
                gas_limit = int(estimated_gas * 1.5)
            except Exception as e:
                debug_print(f"Gas estimation failed: {str(e)}")
                debug_print("Using default gas limit of 3 million")
                gas_limit = 3000000  # Use a higher gas limit if estimation fails
            
            debug_print(f"Setting gas limit to: {gas_limit}")
            
            swap_tx = batch_router.functions.swapExactIn(
                swap_paths,
                deadline,
                False,  # wethIsEth
                '0x'    # userData
            ).build_transaction({
                'from': address,
                'nonce': nonce,
                'gas': gas_limit,
                'type': '0x2',  # EIP-1559 transaction
                'maxFeePerGas': max_fee_per_gas,
                'maxPriorityFeePerGas': max_priority_fee_per_gas,
                'chainId': w3.eth.chain_id,
            })
            
            debug_print(f"Built transaction: {swap_tx}")
            
            # Sign and send the transaction
            signed_tx = w3.eth.account.sign_transaction(swap_tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)  # Use rawTransaction instead of raw_transaction
            print(f"⏳ Transaction sent: {tx_hash.hex()}")
            
            # Wait for the transaction to complete
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            print(f"\nTransaction receipt status: {receipt['status']}")
            
            debug_print(f"Full receipt: {receipt}")
            
            if receipt['status'] == 1:
                print("✅ Swap successful!")
                
                # Check WAGNO balance after swap
                new_wagno_balance = wagno_token.functions.balanceOf(address).call()
                wagno_increase = new_wagno_balance - wagno_balance
                
                print(f"🔹 WAGNO Balance after swap: {w3.from_wei(new_wagno_balance, 'ether')}")
                print(f"🔹 WAGNO Increase: {w3.from_wei(wagno_increase, 'ether')}")
                
                print(f"\nTransaction hash: {tx_hash.hex()}")
                print(f"View on explorer: https://gnosisscan.io/tx/{tx_hash.hex()}")
            else:
                print("❌ Swap failed!")
                print(f"Transaction hash: {tx_hash.hex()}")
                print(f"Gas used: {receipt.get('gasUsed', 'unknown')}")
                
                # Try to get the revert reason if available
                try:
                    # Try to replay the transaction to get the revert reason
                    debug_print("Attempting to get revert reason...")
                    result = w3.eth.call({
                        'to': BATCH_ROUTER_ADDRESS,
                        'from': address,
                        'data': swap_tx['data'],
                        'value': 0
                    }, receipt['blockNumber'] - 1)
                    debug_print(f"Call result: {result}")
                except Exception as call_error:
                    error_str = str(call_error)
                    debug_print(f"Error during call: {error_str}")
                    if "execution reverted" in error_str and "reason" in error_str:
                        revert_reason = error_str.split("reason", 1)[1].strip()
                        print(f"Revert reason: {revert_reason}")
                
                print(f"View details on: https://gnosisscan.io/tx/{tx_hash.hex()}")
                print("Consider checking transaction details on https://gnosis.blockscout.com or using Tenderly for deeper debugging")
        else:
            print(f"Current allowance ({w3.from_wei(current_allowance, 'ether')}) is insufficient")
            print("Approving SDAI for BatchRouter...")
            
            # Approve SDAI to be spent by BatchRouter
            approve_tx = sdai_token.functions.approve(
                BATCH_ROUTER_ADDRESS,
                amount_to_swap * 10  # Approve 10x the amount to reduce future approvals
            ).build_transaction({
                'from': address,
                'nonce': w3.eth.get_transaction_count(address),
                'gas': 100000,
                'type': '0x2',  # EIP-1559 transaction
                'maxFeePerGas': w3.eth.gas_price * 2,
                'maxPriorityFeePerGas': w3.eth.gas_price,
                'chainId': w3.eth.chain_id,
            })
            
            # Sign and send the approval transaction
            signed_tx = w3.eth.account.sign_transaction(approve_tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)  # Use rawTransaction instead of raw_transaction
            print(f"⏳ Approval transaction sent: {tx_hash.hex()}")
            
            # Wait for the transaction to complete
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt['status'] == 1:
                print("✅ SDAI approved for BatchRouter")
                
                # Now execute the swap using swapExactIn
                print("\n3. Executing swap transaction...")
                
                # Set a longer deadline (1 hour from now)
                deadline = w3.eth.get_block('latest')['timestamp'] + (60 * 60)
                
                swap_tx = batch_router.functions.swapExactIn(
                    swap_paths,
                    deadline,
                    False,  # wethIsEth
                    '0x'    # userData
                ).build_transaction({
                    'from': address,
                    'nonce': w3.eth.get_transaction_count(address),
                    'gas': 3000000,  # Increased gas limit to 3 million
                    'type': '0x2',  # EIP-1559 transaction
                    'maxFeePerGas': w3.eth.gas_price * 2,
                    'maxPriorityFeePerGas': w3.eth.gas_price,
                    'chainId': w3.eth.chain_id,
                })
                
                # Sign and send the transaction
                signed_tx = w3.eth.account.sign_transaction(swap_tx, private_key)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)  # Use rawTransaction instead of raw_transaction
                print(f"⏳ Transaction sent: {tx_hash.hex()}")
                
                # Wait for the transaction to complete
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                print(f"\nTransaction receipt status: {receipt['status']}")
                
                if receipt['status'] == 1:
                    print("✅ Swap successful!")
                    
                    # Check WAGNO balance after swap
                    new_wagno_balance = wagno_token.functions.balanceOf(address).call()
                    print(f"🔹 WAGNO Balance after swap: {w3.from_wei(new_wagno_balance, 'ether')}")
                    print(f"🔹 WAGNO Increase: {w3.from_wei(new_wagno_balance - wagno_balance, 'ether')}")
                    
                    print(f"\nTransaction hash: {tx_hash.hex()}")
                    print(f"View on explorer: https://gnosisscan.io/tx/{tx_hash.hex()}")
                else:
                    print("❌ Swap failed!")
                    print(f"Transaction hash: {tx_hash.hex()}")
                    print(f"Gas used: {receipt.get('gasUsed', 'unknown')}")
                    print(f"View details on: https://gnosisscan.io/tx/{tx_hash.hex()}")
            else:
                print("❌ Approval failed!")
                print(f"Transaction hash: {tx_hash.hex()}")
                print(f"View details on: https://gnosisscan.io/tx/{tx_hash.hex()}")
                
    else:
        print("❌ Couldn't determine expected output amount")

except Exception as e:
    print(f"❌ Error during execution: {str(e)}")
    if hasattr(e, 'args') and len(e.args) > 0:
        print("Error details:", e.args[0])
    print("\nTraceback:")
    traceback.print_exc()
    exit(1)