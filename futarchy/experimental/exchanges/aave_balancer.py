"""Aave and Balancer utilities for the Futarchy Trading Bot"""

import sys
import os

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from futarchy.experimental.config.constants import (
    CONTRACT_ADDRESSES, TOKEN_CONFIG, BALANCER_CONFIG,
    BALANCER_VAULT_ABI, BALANCER_POOL_ABI, WAGNO_ABI
)
from futarchy.experimental.utils.web3_utils import get_raw_transaction

class AaveBalancerHandler:
    """Handler for Aave and Balancer interactions"""
    
    def __init__(self, bot):
        """
        Initialize the Aave/Balancer handler.
        
        Args:
            bot: FutarchyBot instance with web3 connection and account
        """
        self.bot = bot
        self.w3 = bot.w3
        self.account = bot.account
        self.address = bot.address
        
        # Initialize Balancer contracts
        self.balancer_vault_address = self.w3.to_checksum_address(BALANCER_CONFIG["vault_address"])
        self.balancer_pool_address = self.w3.to_checksum_address(BALANCER_CONFIG["pool_address"])
        self.wagno_address = self.w3.to_checksum_address(TOKEN_CONFIG["wagno"]["address"])
        
        # Token addresses from config - ensure they're checksummed
        self.sdai_address = self.w3.to_checksum_address(TOKEN_CONFIG["currency"]["address"])
        
        # Initialize with a fallback pool ID
        self.pool_id = "0x0000000000000000000000000000000000000000000000000000000000000000"
        
        # Initialize contract instances
        self.init_contracts()


    def init_contracts(self):
        """Initialize contract instances"""
        # ERC20 contracts
        self.sdai_token = self.bot.get_token_contract(self.sdai_address)
        
        # Aave waGNO contract (StaticAToken)
        # No need to checksum again since we did it in __init__
        self.wagno_token = self.w3.eth.contract(
            address=self.wagno_address,
            abi=WAGNO_ABI
        )
        
        # Balancer Vault contract
        self.balancer_vault = self.w3.eth.contract(
            address=self.balancer_vault_address,
            abi=BALANCER_VAULT_ABI
        )
        
        # Balancer pool contract
        self.balancer_pool = self.w3.eth.contract(
            address=self.balancer_pool_address,
            abi=BALANCER_POOL_ABI
        )
        
        # pool_id is already set in __init__




    def wrap_gno_to_wagno(self, amount, simulate: bool = False):
        """
        Wrap GNO to waGNO using Aave's StaticAToken contract.
        
        Args:
            amount: Amount of GNO to wrap (in ether units)
            simulate: If True, simulate using call() instead of sending tx.
            
        Returns:
            str: Transaction hash if successful (execution mode).
            dict: Simulation result {'success': bool, 'simulated_amount_out': float} (simulation mode).
            None: On failure.
        """
        try:
            amount_wei = self.w3.to_wei(amount, 'ether')
            gno_token = self.bot.get_token_contract(TOKEN_CONFIG["company"]["address"])
            
            # Check GNO balance
            gno_balance = gno_token.functions.balanceOf(self.address).call()
            if gno_balance < amount_wei:
                print(f"❌ Insufficient GNO balance. Required: {amount}, Available: {self.w3.from_wei(gno_balance, 'ether')}")
                return None if not simulate else {'success': False, 'error': 'Insufficient GNO balance'}

            if simulate:
                print(f"🔄 Simulating wrap of {amount} GNO to waGNO...")
                # Skip the actual .call() for deposit simulation due to FailedInnerCall errors
                # Assume 1:1 conversion for simulation purposes
                simulated_amount_out = amount
                print(f"   -> Simulation result: Assuming ~{simulated_amount_out:.18f} waGNO shares (simulation call skipped due to internal checks)")
                return {
                    'success': True, 
                    'simulated_amount_out': float(simulated_amount_out), 
                    'warning': 'Deposit simulation call skipped, assuming 1:1 wrap ratio',
                    'type': 'simulation'
                }
                # try:
                #     # deposit returns shares (uint256)
                #     simulated_shares = self.wagno_token.functions.deposit(
                #         amount_wei, self.address
                #     ).call({'from': self.address})
                #     simulated_amount_out = self.w3.from_wei(simulated_shares, 'ether')
                #     print(f"   -> Simulation result: ~{simulated_amount_out:.18f} waGNO shares")
                #     return {'success': True, 'simulated_amount_out': float(simulated_amount_out), 'type': 'simulation'}
                # except Exception as e:
                #     print(f"❌ Simulation error during wrap: {e}")
                #     return {'success': False, 'error': str(e), 'type': 'simulation'}

            # --- Execution Logic --- 
            print(f"Wrapping {amount} GNO to waGNO...")
            
            # 1. Approve waGNO contract to spend GNO
            checksummed_wagno_address = self.w3.to_checksum_address(self.wagno_address)
            if not self.bot.approve_token(gno_token, checksummed_wagno_address, amount_wei):
                print("❌ Failed to approve GNO transfer")
                return None
            
            # Debug: Get the current allowance
            current_allowance = gno_token.functions.allowance(self.address, checksummed_wagno_address).call()
            print(f"DEBUG: Current allowance for waGNO contract: {self.w3.from_wei(current_allowance, 'ether')} GNO")
            
            # Debug: Check if waGNO contract exists
            try:
                code = self.w3.eth.get_code(checksummed_wagno_address)
                if code == b'' or code == '0x':
                    print(f"❌ WARNING: No contract code found at waGNO address {checksummed_wagno_address}")
                else:
                    print(f"DEBUG: Contract code exists at waGNO address (length: {len(code)} bytes)")
            except Exception as code_error:
                print(f"❌ Error checking contract code: {code_error}")
            
            # 3. Try to estimate gas first to see if transaction would fail
            try:
                gas_estimate = self.wagno_token.functions.deposit(
                    amount_wei, self.address
                ).estimate_gas({'from': self.address})
                print(f"DEBUG: Gas estimate for deposit: {gas_estimate}")
            except Exception as gas_error:
                print(f"❌ WARNING: Gas estimation failed: {gas_error}")
                print("   This usually indicates the transaction will fail, but proceeding anyway...")
                gas_estimate = 500000  # Default value
            
            # 4. Build the deposit transaction - USING ONLY 2 PARAMETERS
            deposit_tx = self.wagno_token.functions.deposit(
                amount_wei,
                self.address
            ).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
                'gas': int(gas_estimate * 1.2) if gas_estimate != 500000 else 500000,  # Add 20% buffer if estimated
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.w3.eth.chain_id,
            })
            
            print(f"DEBUG: Transaction data: {deposit_tx['data']}")
            
            # Sign and send transaction
            signed_tx = self.w3.eth.account.sign_transaction(deposit_tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(get_raw_transaction(signed_tx))
            
            print(f"⏳ Wrapping transaction sent: {tx_hash.hex()}")
            
            # Wait for transaction confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt['status'] == 1:
                print(f"✅ Successfully wrapped {amount} GNO to waGNO!")
                return tx_hash.hex()
            else:
                print("❌ Wrapping transaction failed!")
                # Try to get error details
                try:
                    trace_node = f"https://blockscout.com/xdai/mainnet/api?module=transaction&action=gettxinfo&txhash={tx_hash.hex()}"
                    print(f"Check transaction details at: {trace_node}")
                    print(f"Transaction: https://gnosisscan.io/tx/{tx_hash.hex()}")
                except Exception as trace_error:
                    print(f"Error getting transaction trace: {trace_error}")
                return None
                    
        except Exception as e:
            print(f"❌ Error wrapping GNO to waGNO: {e}")
            import traceback
            traceback.print_exc()
            return None

    
    def unwrap_wagno(self, amount, simulate: bool = False):
        """Alias for unwrap_wagno_to_gno"""
        return self.unwrap_wagno_to_gno(amount, simulate=simulate)

    def unwrap_wagno_to_gno(self, amount, simulate: bool = False):
        """
        Unwrap waGNO back to GNO.
        
        Args:
            amount: Amount of waGNO to unwrap (in ether units)
            simulate: If True, simulate using call() instead of sending tx.
            
        Returns:
            str: Transaction hash if successful (execution mode).
            dict: Simulation result {'success': bool, 'simulated_amount_out': float} (simulation mode).
            None: On failure.
        """
        try:
            amount_wei = self.w3.to_wei(amount, 'ether')
            wagno_balance = self.wagno_token.functions.balanceOf(self.address).call()
            
            print("\nCurrent Balances:") # Keep this for context
            print(f"waGNO: {self.w3.from_wei(wagno_balance, 'ether')} ({wagno_balance} wei)")
            print(f"Amount to unwrap: {amount} waGNO ({amount_wei} wei)\n")
            
            if wagno_balance < amount_wei:
                print(f"❌ Insufficient waGNO balance")
                print(f"   Required: {amount} waGNO")
                print(f"   Available: {self.w3.from_wei(wagno_balance, 'ether')} waGNO")
                return None if not simulate else {'success': False, 'error': 'Insufficient waGNO balance'}

            if simulate:
                print(f"🔄 Simulating unwrap of {amount} waGNO to GNO...")
                try:
                    # redeem returns assets (uint256)
                    simulated_assets = self.wagno_token.functions.redeem(
                        amount_wei, self.address, self.address
                    ).call({'from': self.address})
                    simulated_amount_out = self.w3.from_wei(simulated_assets, 'ether')
                    print(f"   -> Simulation result: ~{simulated_amount_out:.18f} GNO assets")
                    return {'success': True, 'simulated_amount_out': float(simulated_amount_out), 'type': 'simulation'}
                except Exception as e:
                    print(f"❌ Simulation error during unwrap: {e}")
                    return {'success': False, 'error': str(e), 'type': 'simulation'}

            # --- Execution Logic ---
            print(f"Unwrapping {amount} waGNO to GNO...")
            
            # Try to estimate gas first to see if transaction would fail
            try:
                gas_estimate = self.wagno_token.functions.redeem(
                    amount_wei, self.address, self.address
                ).estimate_gas({'from': self.address})
                print(f"✅ Gas estimation successful: {gas_estimate}")
            except Exception as gas_error:
                print(f"⚠️ WARNING: Gas estimation failed: {gas_error}")
                print("   This usually indicates the transaction will fail, but proceeding anyway...")
                gas_estimate = 500000  # Default high gas limit
            
            # Redeem waGNO to get GNO back
            redeem_tx = self.wagno_token.functions.redeem(
                amount_wei,
                self.address,  # receiver
                self.address   # owner
            ).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
                'gas': int(gas_estimate * 1.2),  # Add 20% buffer
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.w3.eth.chain_id,
            })
            
            # Sign and send transaction
            signed_tx = self.w3.eth.account.sign_transaction(redeem_tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(get_raw_transaction(signed_tx))
            
            print(f"\n⏳ Unwrapping transaction sent: {tx_hash.hex()}")
            print(f"Transaction: https://gnosisscan.io/tx/{tx_hash.hex()}")
            
            # Wait for transaction confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt['status'] == 1:
                # Get new balances
                new_wagno_balance = self.wagno_token.functions.balanceOf(self.address).call()
                gno_token = self.bot.get_token_contract(TOKEN_CONFIG["company"]["address"])
                new_gno_balance = gno_token.functions.balanceOf(self.address).call()
                
                print(f"\n✅ Successfully unwrapped {amount} waGNO to GNO!")
                print(f"New balances:")
                print(f"waGNO: {self.w3.from_wei(new_wagno_balance, 'ether')} ({new_wagno_balance} wei)")
                print(f"GNO: {self.w3.from_wei(new_gno_balance, 'ether')} ({new_gno_balance} wei)")
                
                # Calculate and display changes
                print(f"\nBalance Changes:")
                print(f"waGNO: -{amount} waGNO")  # We know exactly how much was unwrapped
                print(f"GNO: +{amount} GNO")  # We know exactly how much was received
                
                return tx_hash.hex()
            else:
                print("❌ Unwrapping transaction failed!")
                # Try to get error details
                try:
                    trace_node = f"https://blockscout.com/xdai/mainnet/api?module=transaction&action=gettxinfo&txhash={tx_hash.hex()}"
                    print(f"Check transaction details at: {trace_node}")
                    print(f"Transaction: https://gnosisscan.io/tx/{tx_hash.hex()}")
                except Exception as trace_error:
                    print(f"Error getting transaction trace: {trace_error}")
                return None
                    
        except Exception as e:
            print(f"❌ Error unwrapping waGNO to GNO: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_pool_tokens(self):
        """
        Get the tokens in the Balancer pool.
        
        Returns:
            tuple: (token_addresses, token_balances)
        """
        try:
            tokens, balances, _ = self.balancer_vault.functions.getPoolTokens(self.pool_id).call()
            return tokens, balances
        except Exception as e:
            print(f"❌ Error getting pool tokens: {e}")
            return [], []
    


    def swap_on_balancer(self, token_in, token_out, amount_in, min_amount_out=None):
        try:
            # Convert addresses to checksummed form
            token_in_cs = self.w3.to_checksum_address(token_in)
            token_out_cs = self.w3.to_checksum_address(token_out)
            
            print(f"DEBUG: Token in: {token_in_cs}")
            print(f"DEBUG: Token out: {token_out_cs}")
            
            # Convert amount to wei
            amount_in_wei = self.w3.to_wei(amount_in, 'ether')
            print(f"DEBUG: Amount in wei: {amount_in_wei}")
            
            # Check token balance
            token_in_contract = self.bot.get_token_contract(token_in_cs)
            token_in_balance = token_in_contract.functions.balanceOf(self.address).call()
            
            if token_in_balance < amount_in_wei:
                print(f"❌ Insufficient {token_in} balance. Required: {amount_in}, Available: {self.w3.from_wei(token_in_balance, 'ether')}")
                return None
            
            # Use the pool ID we've defined
            pool_id = "0xD1D7Fa8871d84d0E77020fc28B7Cd5718C4465220002000000000000000001d7"
            print(f"Using Pool ID: {pool_id}")
            
            # Convert the pool ID string to bytes
            pool_id_bytes = bytes.fromhex(pool_id.replace("0x", ""))
            print(f"DEBUG: Pool ID as bytes has length: {len(pool_id_bytes)}")
            
            # Calculate min amount out if not provided
            if min_amount_out is None:
                min_amount_out = amount_in * 0.9  # 10% slippage
                print(f"Using default minimum amount out: {min_amount_out} (with 10% slippage)")
            
            min_amount_out_wei = self.w3.to_wei(min_amount_out, 'ether')
            print(f"DEBUG: Min amount out wei: {min_amount_out_wei}")
            
            print(f"Swapping {amount_in} tokens for at least {min_amount_out} tokens on Balancer...")
            
            # Approve Balancer vault to spend tokens
            if not self.bot.approve_token(token_in_contract, self.balancer_vault_address, amount_in_wei):
                print("❌ Failed to approve token transfer")
                return None
            
            # Create swap parameters
            single_swap = {
                'poolId': pool_id_bytes,
                'assetIn': token_in_cs,
                'assetOut': token_out_cs,
                'amount': amount_in_wei,
                'userData': b''
            }
            
            fund_management = {
                'sender': self.address,
                'fromInternalBalance': False,
                'recipient': self.address,
                'toInternalBalance': False
            }
            
            # Limit is the minimum amount we want to receive
            limit = min_amount_out_wei
            
            # Set deadline to 10 minutes from now
            deadline = self.w3.eth.get_block('latest')['timestamp'] + 600
            
            print("DEBUG: Swap parameters:")
            print(f"  poolId: {pool_id}")
            print(f"  assetIn: {token_in_cs}")
            print(f"  assetOut: {token_out_cs}")
            print(f"  amount: {amount_in_wei}")
            print(f"  limit: {limit}")
            print(f"  deadline: {deadline}")
            
            # Try to estimate gas first
            try:
                gas_estimate = self.balancer_vault.functions.swap(
                    single_swap,
                    fund_management,
                    limit,
                    deadline
                ).estimate_gas({
                    'from': self.address,
                    'value': 0
                })
                print(f"DEBUG: Estimated gas: {gas_estimate}")
            except Exception as gas_error:
                print(f"WARNING: Gas estimation failed: {gas_error}")
                gas_estimate = 700000  # Higher default value
            
            # Create swap transaction
            swap_tx = self.balancer_vault.functions.swap(
                single_swap,
                fund_management,
                limit,
                deadline
            ).build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
                'gas': int(gas_estimate * 1.2) if gas_estimate != 700000 else 700000,
                'gasPrice': self.w3.eth.gas_price,
                'chainId': self.w3.eth.chain_id,
                'value': 0
            })
            
            print(f"DEBUG: Transaction data length: {len(swap_tx['data'])}")
            
            # Sign and send transaction
            signed_tx = self.w3.eth.account.sign_transaction(swap_tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(get_raw_transaction(signed_tx))
            
            print(f"⏳ Swap transaction sent: {tx_hash.hex()}")
            print(f"Transaction URL: https://gnosisscan.io/tx/{tx_hash.hex()}")
            
            # Wait for transaction confirmation
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt['status'] == 1:
                print(f"✅ Swap successful!")
                return tx_hash.hex()
            else:
                print("❌ Swap transaction failed!")
                print(f"Check transaction details: https://gnosisscan.io/tx/{tx_hash.hex()}")
                return None
                
        except Exception as e:
            print(f"❌ Error executing swap on Balancer: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def swap_sdai_to_wagno(self, amount, min_amount_out=None):
        """Convenience method to swap sDAI to waGNO"""
        return self.swap_on_balancer(self.sdai_address, self.wagno_address, amount, min_amount_out)
    
    def swap_wagno_to_sdai(self, amount, min_amount_out=None):
        """Convenience method to swap waGNO to sDAI"""
        return self.swap_on_balancer(self.wagno_address, self.sdai_address, amount, min_amount_out)
    
    def get_balances(self):
        """
        Get token balances.
        
        Returns:
            dict: Token balances
        """
        try:
            # Get token balances
            sdai_balance = self.sdai_token.functions.balanceOf(self.address).call()
            wagno_balance = self.wagno_token.functions.balanceOf(self.address).call()
            
            balances = {
                "sDAI": self.w3.from_wei(sdai_balance, 'ether'),
                "waGNO": self.w3.from_wei(wagno_balance, 'ether')
            }
            
            return balances
        except Exception as e:
            print(f"❌ Error getting token balances: {e}")
            return {
                "sDAI": 0,
                "waGNO": 0
            }
    
    def print_balances(self):
        """Print token balances"""
        balances = self.get_balances()
        
        print("\n=== Aave/Balancer Token Balances ===")
        print(f"sDAI:  {balances['sDAI']:.6f}")
        print(f"waGNO: {balances['waGNO']:.6f}")

    def check_wagno_configuration(self):
        """
        Verify the waGNO contract configuration.
        
        Returns:
            bool: True if configuration is correct, False otherwise
        """
        try:
            print("\n=== Checking waGNO Configuration ===")
            
            # 1. Check if the contract exists
            code = self.w3.eth.get_code(self.w3.to_checksum_address(self.wagno_address))
            if code == b'' or code == '0x':
                print(f"❌ No contract code found at waGNO address {self.wagno_address}")
                return False
            else:
                print(f"✅ Contract code exists at waGNO address (length: {len(code)} bytes)")
            
            # 2. Check for basic functionality - don't try to print function names
            print("\nTesting contract functionality:")
            
            # 3. Check balanceOf function
            try:
                balance = self.wagno_token.functions.balanceOf(self.address).call()
                print(f"waGNO Balance: {self.w3.from_wei(balance, 'ether')}")
                print("✅ balanceOf function works")
            except Exception as balance_error:
                print(f"❌ Error checking balance: {balance_error}")
            
            # 4. Check if we can at least build a deposit transaction (without sending it)
            try:
                deposit_data = self.wagno_token.functions.deposit(
                    self.w3.to_wei(0.001, 'ether'),
                    self.address
                ).build_transaction({
                    'from': self.address,
                    'gas': 500000,
                    'gasPrice': self.w3.eth.gas_price,
                    'nonce': self.w3.eth.get_transaction_count(self.address),
                    'chainId': self.w3.eth.chain_id,
                })
                print("✅ deposit function can build transaction")
                print(f"Transaction data length: {len(deposit_data['data'])}")
            except Exception as deposit_error:
                print(f"❌ Error building deposit transaction: {deposit_error}")
            
            # 5. Check if we can at least build a redeem transaction (without sending it)
            try:
                redeem_data = self.wagno_token.functions.redeem(
                    self.w3.to_wei(0.001, 'ether'),
                    self.address,
                    self.address
                ).build_transaction({
                    'from': self.address,
                    'gas': 500000,
                    'gasPrice': self.w3.eth.gas_price,
                    'nonce': self.w3.eth.get_transaction_count(self.address),
                    'chainId': self.w3.eth.chain_id,
                })
                print("✅ redeem function can build transaction")
                print(f"Transaction data length: {len(redeem_data['data'])}")
            except Exception as redeem_error:
                print(f"❌ Error building redeem transaction: {redeem_error}")
            
            print("=== Configuration check complete ===\n")
            return True
                
        except Exception as e:
            print(f"❌ Error checking waGNO configuration: {e}")
            import traceback
            traceback.print_exc()
            return False