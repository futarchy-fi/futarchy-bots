"""
Permit2 handler for Balancer swaps.
This module provides functionality to check and create Permit2 authorizations.
"""

from web3 import Web3
import json
import os
from hexbytes import HexBytes
from config.constants import CONTRACT_ADDRESSES

# eth-account >=0.7 renamed encode_typed_data -> encode_structured_data
# Provide a compatibility shim so the rest of the code can stay unchanged.
try:
    # eth-account <0.7
    from eth_account.messages import encode_typed_data  # type: ignore
except ImportError:  # pragma: no cover
    # eth-account >=0.7
    from eth_account.messages import encode_structured_data as encode_typed_data  # type: ignore

class BalancerPermit2Handler:
    """Handler for Permit2 operations with Balancer."""
    
    def __init__(self, bot, verbose=False):
        """
        Initialize the Permit2 handler.
        
        Args:
            bot: FutarchyBot instance with web3 connection and account
            verbose: Whether to print verbose debug information
        """
        self.bot = bot
        self.w3 = bot.w3
        self.account = bot.account
        self.address = bot.address
        self.verbose = verbose
        
        # Get Permit2 address from constants
        self.permit2_address = self.w3.to_checksum_address(
            os.environ.get('PERMIT2_ADDRESS', CONTRACT_ADDRESSES["permit2"])
        )
        
        # Initialize Permit2 contract
        self.permit2_abi = [
            {
                "inputs": [
                    {
                        "internalType": "address",
                        "name": "owner",
                        "type": "address"
                    },
                    {
                        "components": [
                            {
                                "components": [
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address"
                                    },
                                    {
                                        "internalType": "uint160",
                                        "name": "amount",
                                        "type": "uint160"
                                    },
                                    {
                                        "internalType": "uint48",
                                        "name": "expiration",
                                        "type": "uint48"
                                    },
                                    {
                                        "internalType": "uint48",
                                        "name": "nonce",
                                        "type": "uint48"
                                    }
                                ],
                                "internalType": "struct IAllowanceTransfer.PermitDetails",
                                "name": "details",
                                "type": "tuple"
                            },
                            {
                                "internalType": "address",
                                "name": "spender",
                                "type": "address"
                            },
                            {
                                "internalType": "uint256",
                                "name": "sigDeadline",
                                "type": "uint256"
                            }
                        ],
                        "internalType": "struct IAllowanceTransfer.PermitSingle",
                        "name": "permitSingle",
                        "type": "tuple"
                    },
                    {
                        "internalType": "bytes",
                        "name": "signature",
                        "type": "bytes"
                    }
                ],
                "name": "permit",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {
                        "internalType": "address",
                        "name": "owner",
                        "type": "address"
                    },
                    {
                        "internalType": "address",
                        "name": "token",
                        "type": "address"
                    },
                    {
                        "internalType": "address",
                        "name": "spender",
                        "type": "address"
                    }
                ],
                "name": "allowance",
                "outputs": [
                    {
                        "internalType": "uint160",
                        "name": "amount",
                        "type": "uint160"
                    },
                    {
                        "internalType": "uint48",
                        "name": "expiration",
                        "type": "uint48"
                    },
                    {
                        "internalType": "uint48",
                        "name": "nonce",
                        "type": "uint48"
                    }
                ],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        self.permit2 = self.w3.eth.contract(address=self.permit2_address, abi=self.permit2_abi)
        
        if self.verbose:
            print(f"Initialized Permit2 handler with address: {self.permit2_address}")
    
    def check_permit(self, token_address, spender_address, required_amount=None):
        """
        Check if a valid Permit2 authorization exists.
        
        Args:
            token_address: Address of the token to check
            spender_address: Address of the spender to check
            required_amount: Minimum amount required (optional)
            
        Returns:
            dict: Permit status information
        """
        token_address = self.w3.to_checksum_address(token_address)
        spender_address = self.w3.to_checksum_address(spender_address)
        
        # First check if token is approved for Permit2
        token_contract = self.bot.get_token_contract(token_address)
        permit2_allowance = token_contract.functions.allowance(self.address, self.permit2_address).call()
        
        # Get token balance
        token_balance = token_contract.functions.balanceOf(self.address).call()
        
        # Check Permit2 allowance for spender
        try:
            current_allowance = self.permit2.functions.allowance(
                self.address, token_address, spender_address
            ).call()
            amount, expiration, nonce = current_allowance
            
            current_time = self.w3.eth.get_block('latest')['timestamp']
            is_valid = amount > 0 and expiration > current_time
            
            if required_amount is not None:
                required_amount_wei = self.w3.to_wei(required_amount, 'ether')
                is_sufficient = amount >= required_amount_wei
            else:
                is_sufficient = True
            
            result = {
                "token_approved_for_permit2": permit2_allowance > 0,
                "token_balance": token_balance,
                "token_balance_eth": self.w3.from_wei(token_balance, 'ether'),
                "permit2_allowance": {
                    "amount": amount,
                    "amount_eth": self.w3.from_wei(amount, 'ether'),
                    "expiration": expiration,
                    "nonce": nonce,
                    "is_valid": is_valid,
                    "is_sufficient": is_sufficient
                },
                "needs_permit": not (is_valid and is_sufficient)
            }
            
            if self.verbose:
                print(f"\nPermit2 check for {token_address}:")
                print(f"Token approved for Permit2: {result['token_approved_for_permit2']}")
                print(f"Token balance: {result['token_balance_eth']}")
                print(f"Permit2 allowance amount: {result['permit2_allowance']['amount_eth']}")
                print(f"Permit2 allowance expiration: {result['permit2_allowance']['expiration']}")
                print(f"Permit2 allowance valid: {result['permit2_allowance']['is_valid']}")
                print(f"Permit2 allowance sufficient: {result['permit2_allowance']['is_sufficient']}")
                print(f"Needs new permit: {result['needs_permit']}")
            
            return result
            
        except Exception as e:
            if self.verbose:
                print(f"Error checking Permit2 allowance: {e}")
            
            return {
                "token_approved_for_permit2": permit2_allowance > 0,
                "token_balance": token_balance,
                "token_balance_eth": self.w3.from_wei(token_balance, 'ether'),
                "permit2_allowance": None,
                "needs_permit": True,
                "error": str(e)
            }
    
    def create_permit(self, token_address, spender_address, amount, expiration_hours=24, sig_deadline_hours=1):
        """
        Create a Permit2 authorization.
        
        Args:
            token_address: Address of the token to permit
            spender_address: Address of the spender to permit
            amount: Amount to permit (in ether units)
            expiration_hours: How many hours until the permit expires
            sig_deadline_hours: How many hours until the signature expires
            
        Returns:
            str: Transaction hash if successful, None otherwise
        """
        token_address = self.w3.to_checksum_address(token_address)
        spender_address = self.w3.to_checksum_address(spender_address)
        
        # Convert amount to wei
        amount_wei = self.w3.to_wei(amount, 'ether')
        
        # Check if token is approved for Permit2
        token_contract = self.bot.get_token_contract(token_address)
        permit2_allowance = token_contract.functions.allowance(self.address, self.permit2_address).call()
        
        if permit2_allowance == 0:
            print(f"Token not approved for Permit2. Approving...")
            if not self.bot.approve_token(token_contract, self.permit2_address, 2**256 - 1):  # Max approval
                print("❌ Failed to approve token for Permit2")
                return None
        
        # 1. Check current allowance and nonce
        try:
            current_allowance = self.permit2.functions.allowance(
                self.address, token_address, spender_address
            ).call()
            current_amount, expiration, current_nonce = current_allowance
            
            if self.verbose:
                print("\nCurrent Permit2 allowance:")
                print(f"Amount: {current_amount}")
                print(f"Expiration: {expiration}")
                print(f"Nonce from allowance: {current_nonce}")
                
                timestamp = self.w3.eth.get_block('latest')['timestamp']
                print(f"Current timestamp: {timestamp}")
                
                if expiration > timestamp:
                    print("Status: VALID - Allowance is still valid")
                else:
                    print("Status: EXPIRED - Allowance has expired")
                
        except Exception as e:
            if self.verbose:
                print(f"Error checking allowance: {e}")
            return None

        # 2. Create and sign a permit message
        # Permit2 expects the exact current nonce
        expiration_time = int(self.w3.eth.get_block('latest')['timestamp'] + 60 * 60 * expiration_hours)
        sig_deadline = int(self.w3.eth.get_block('latest')['timestamp'] + 60 * 60 * sig_deadline_hours)

        if self.verbose:
            print(f"\nCreating permit with:")
            print(f"Amount: {amount_wei}")
            print(f"Expiration: {expiration_time} ({expiration_hours} hours from now)")
            print(f"Using nonce value: {current_nonce}")

        # Prepare the typed data structure according to EIP-712 for Permit2
        typed_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"}
                ],
                "PermitDetails": [
                    {"name": "token", "type": "address"},
                    {"name": "amount", "type": "uint160"},
                    {"name": "expiration", "type": "uint48"},
                    {"name": "nonce", "type": "uint48"}
                ],
                "PermitSingle": [
                    {"name": "details", "type": "PermitDetails"},
                    {"name": "spender", "type": "address"},
                    {"name": "sigDeadline", "type": "uint256"}
                ]
            },
            "domain": {
                "name": "Permit2",
                "chainId": self.w3.eth.chain_id,
                "verifyingContract": self.permit2_address
            },
            "primaryType": "PermitSingle",
            "message": {
                "details": {
                    "token": token_address,
                    "amount": amount_wei,
                    "expiration": expiration_time,
                    "nonce": current_nonce
                },
                "spender": spender_address,
                "sigDeadline": sig_deadline
            }
        }

        if self.verbose:
            print("\nTyped data for signing:", json.dumps(typed_data, indent=2))

        # Sign the message
        encoded_message = encode_typed_data(full_message=typed_data)
        signed_message = self.account.sign_message(encoded_message)
        signature = signed_message.signature.hex()

        if self.verbose:
            print(f"Signature: {signature}")

        # 3. Send the permit transaction directly to Permit2
        permit_single = (
            (token_address, amount_wei, expiration_time, current_nonce),  # details - using current nonce
            spender_address,  # spender
            sig_deadline  # sigDeadline
        )

        print("\nSending permit transaction to Permit2...")
        try:
            # Convert hex signature to bytes
            signature_bytes = HexBytes(signature)
            
            tx = self.permit2.functions.permit(
                self.address,
                permit_single,
                signature_bytes
            ).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
                'gas': 300000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.w3.eth.chain_id
            })
            
            signed_tx = self.w3.eth.account.sign_transaction(tx, private_key=self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            tx_hash_hex = tx_hash.hex()
            print(f"Transaction sent: {tx_hash_hex}")
            
            # Wait for the transaction to be mined
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            print(f"Transaction status: {'SUCCESS' if receipt.status == 1 else 'FAILED'}")
            
            if self.verbose:
                print(f"Gas used: {receipt.gasUsed}")
            
            # 4. Verify the allowance was updated
            if self.verbose:
                print("\nVerifying allowance after permit...")
            
            new_allowance = self.permit2.functions.allowance(self.address, token_address, spender_address).call()
            new_amount, new_expiration, new_nonce = new_allowance
            
            if self.verbose:
                print(f"New amount: {new_amount}")
                print(f"New expiration: {new_expiration}")
                print(f"New nonce: {new_nonce}")
            
            if new_amount > 0 and new_expiration > self.w3.eth.get_block('latest')['timestamp']:
                print("✅ PERMIT SUCCESSFUL: Spender now has permission to spend your tokens through Permit2")
                return tx_hash_hex
            else:
                print("❌ PERMIT FAILED: Spender still doesn't have permission")
                return None
                
        except Exception as e:
            print(f"Error sending permit transaction: {e}")
            return None
    
    def ensure_permit(self, token_address, spender_address, amount):
        """
        Ensure a valid Permit2 authorization exists, creating one if needed.
        
        Args:
            token_address: Address of the token to permit
            spender_address: Address of the spender to permit
            amount: Amount to permit (in ether units)
            
        Returns:
            bool: True if a valid permit exists or was created, False otherwise
        """
        # Check current permit status
        permit_status = self.check_permit(token_address, spender_address, amount)
        
        # If permit is not needed, we're good
        if not permit_status["needs_permit"]:
            print("✅ Valid Permit2 authorization already exists")
            return True
        
        # If token is not approved for Permit2, we need to approve it
        if not permit_status["token_approved_for_permit2"]:
            print("Token not approved for Permit2. Approving...")
            token_contract = self.bot.get_token_contract(token_address)
            if not self.bot.approve_token(token_contract, self.permit2_address, 2**256 - 1):  # Max approval
                print("❌ Failed to approve token for Permit2")
                return False
        
        # Create a new permit
        print("Creating new Permit2 authorization...")
        tx_hash = self.create_permit(token_address, spender_address, amount)
        
        # Check if permit was created successfully
        if tx_hash:
            print(f"✅ Permit2 authorization created successfully: {tx_hash}")
            return True
        else:
            print("❌ Failed to create Permit2 authorization")
            return False

    def ensure_permit2_approval(self, token_address, amount):
        """
        Ensure Permit2 has approval to spend the specified token amount.
        
        Args:
            token_address: Address of the token to approve
            amount: Amount to approve (in wei)
            
        Returns:
            bool: True if approval is successful or already approved
        """
        try:
            # Check if BatchRouter is already approved
            token_contract = self.bot.get_token_contract(token_address)
            current_allowance = token_contract.functions.allowance(
                self.address,
                self.permit2_address
            ).call()
            
            if current_allowance >= amount:
                if self.verbose:
                    print(f"✅ Permit2 already approved for {self.w3.from_wei(current_allowance, 'ether')} tokens")
                return True
            
            print(f"Approving Permit2 to spend {self.w3.from_wei(amount, 'ether')} tokens...")
            
            # Approve Permit2 to spend tokens
            approve_tx = token_contract.functions.approve(
                self.permit2_address,
                amount
            ).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
                'gas': 100000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.w3.eth.chain_id
            })
            
            # Sign and send transaction
            signed_tx = self.account.sign_transaction(approve_tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            print(f"⏳ Waiting for Permit2 approval transaction: {tx_hash.hex()}")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt['status'] == 1:
                print("✅ Permit2 approval successful!")
                return True
            else:
                print("❌ Permit2 approval failed!")
                return False
                
        except Exception as e:
            print(f"❌ Error in Permit2 approval: {e}")
            return False 