# Constants, contract addresses, and ABIs for the Futarchy Trading Bot

# API Endpoints
COWSWAP_API_URL = "https://api.cow.fi/xdai"  # Gnosis Chain (Production)

# Contract addresses
CONTRACT_ADDRESSES = {
    "futarchyRouter": "0x7495a583ba85875d59407781b4958ED6e0E1228f",
    "sushiswap": "0x592abc3734cd0d458e6e44a2db2992a3d00283a4",
    "market": "0x6242AbA055957A63d682e9D3de3364ACB53D053A",
    "conditionalTokens": "0xCeAfDD6bc0bEF976fdCd1112955828E00543c0Ce",
    "wrapperService": "0xc14f5d2B9d6945EF1BA93f8dB20294b90FA5b5b1",
    "vaultRelayer": "0xC92E8bdf79f0507f65a392b0ab4667716BFE0110",
    "cowSettlement": "0x9008D19f58AAbD9eD0D60971565AA8510560ab41",
    "baseCurrencyToken": "0xaf204776c7245bF4147c2612BF6e5972Ee483701",  # SDAI
    "baseCompanyToken": "0x9C58BAcC331c9aa871AFD802DB6379a98e80CEdb",  # GNO
    "currencyYesToken": "0x493A0D1c776f8797297Aa8B34594fBd0A7F8968a",
    "currencyNoToken": "0xE1133Ef862f3441880adADC2096AB67c63f6E102",
    "companyYesToken": "0x177304d505eCA60E1aE0dAF1bba4A4c4181dB8Ad",
    "companyNoToken": "0xf1B3E5Ffc0219A4F8C0ac69EC98C97709EdfB6c9",
    "poolYes": "0x9a14d28909f42823ee29847f87a15fb3b6e8aed3",
    "poolNo": "0x6E33153115Ab58dab0e0F1E3a2ccda6e67FA5cD7",
    "sdaiRateProvider": "0x89C80A4540A00b5270347E02e2E144c71da2EceD",
    "wxdai": "0xe91D153E0b41518A2Ce8Dd3D7944Fa863463a97d",
}

# Pool configurations
POOL_CONFIG_YES = {
    "address": "0x9a14d28909f42823ee29847f87a15fb3b6e8aed3",
    "tokenCompanySlot": 0
}

POOL_CONFIG_NO = {
    "address": "0x6E33153115Ab58dab0e0F1E3a2ccda6e67FA5cD7",
    "tokenCompanySlot": 1
}

# Token configurations
TOKEN_CONFIG = {
    "currency": {
        "name": "SDAI",
        "address": "0xaf204776c7245bF4147c2612BF6e5972Ee483701",
        "decimals": 18,
        "yes_address": "0x493A0D1c776f8797297Aa8B34594fBd0A7F8968a",
        "no_address": "0xE1133Ef862f3441880adADC2096AB67c63f6E102"
    },
    "company": {
        "name": "GNO",
        "address": "0x9C58BAcC331c9aa871AFD802DB6379a98e80CEdb",
        "decimals": 18,
        "yes_address": "0x177304d505eCA60E1aE0dAF1bba4A4c4181dB8Ad",
        "no_address": "0xf1B3E5Ffc0219A4F8C0ac69EC98C97709EdfB6c9"
    }
}

# Constants for SushiSwap V3
MIN_SQRT_RATIO = 4295128740
MAX_SQRT_RATIO = 1461446703485210103287273052203988822378723970341

# Contract ABIs
ERC20_ABI = [
    {"constant": True, "inputs": [{"name": "owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "payable": False, "stateMutability": "view", "type": "function"},
    {"constant": False, "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "payable": False, "stateMutability": "nonpayable", "type": "function"},
    {"constant": True, "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}], "name": "allowance", "outputs": [{"name": "", "type": "uint256"}], "payable": False, "stateMutability": "view", "type": "function"}
]

UNISWAP_V3_POOL_ABI = [
    {"inputs": [], "name": "token0", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "token1", "outputs": [{"internalType": "address", "name": "", "type": "address"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "slot0", "outputs": [{"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"}, {"internalType": "int24", "name": "tick", "type": "int24"}, {"internalType": "uint16", "name": "observationIndex", "type": "uint16"}, {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"}, {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"}, {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"}, {"internalType": "bool", "name": "unlocked", "type": "bool"}], "stateMutability": "view", "type": "function"}
]

SUSHISWAP_V3_ROUTER_ABI = [
    {"inputs": [{"internalType": "address", "name": "pool", "type": "address"}, {"internalType": "address", "name": "recipient", "type": "address"}, {"internalType": "bool", "name": "zeroForOne", "type": "bool"}, {"internalType": "int256", "name": "amountSpecified", "type": "int256"}, {"internalType": "uint160", "name": "sqrtPriceLimitX96", "type": "uint160"}, {"internalType": "bytes", "name": "data", "type": "bytes"}], "name": "swap", "outputs": [{"internalType": "int256", "name": "", "type": "int256"}, {"internalType": "int256", "name": "", "type": "int256"}], "stateMutability": "nonpayable", "type": "function"}
]

FUTARCHY_ROUTER_ABI = [
    {"inputs": [{"internalType": "contract FutarchyProposal", "name": "proposal", "type": "address"}, {"internalType": "contract IERC20", "name": "collateralToken", "type": "address"}, {"internalType": "uint256", "name": "amount", "type": "uint256"}], "name": "splitPosition", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "contract FutarchyProposal", "name": "proposal", "type": "address"}, {"internalType": "contract IERC20", "name": "collateralToken", "type": "address"}, {"internalType": "uint256", "name": "amount", "type": "uint256"}], "name": "mergePositions", "outputs": [], "stateMutability": "nonpayable", "type": "function"}
]

SDAI_RATE_PROVIDER_ABI = [
    {"inputs": [], "name": "getRate", "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}], "stateMutability": "view", "type": "function"}
]

WXDAI_ABI = [
    {"constant": False, "inputs": [], "name": "deposit", "outputs": [], "payable": True, "stateMutability": "payable", "type": "function"},
    {"constant": True, "inputs": [{"name": "", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "payable": False, "stateMutability": "view", "type": "function"},
    {"constant": False, "inputs": [{"name": "guy", "type": "address"}, {"name": "wad", "type": "uint256"}], "name": "approve", "outputs": [{"name": "", "type": "bool"}], "payable": False, "stateMutability": "nonpayable", "type": "function"}
]

SDAI_DEPOSIT_ABI = [
    {"inputs":[{"internalType":"uint256","name":"assets","type":"uint256"},{"internalType":"address","name":"receiver","type":"address"}],"name":"deposit","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"nonpayable","type":"function"}
]

# Add to constants.py

# Balancer and Aave addresses
BALANCER_VAULT_ADDRESS = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
BALANCER_POOL_ADDRESS = "0xd1d7fa8871d84d0e77020fc28b7cd5718c446522"
WAGNO_ADDRESS = "0x7c16f0185a26db0ae7a9377f23bc18ea7ce5d644"

# ABIs for Balancer and Aave contracts
BALANCER_VAULT_ABI = [
    {"inputs":[{"components":[{"internalType":"bytes32","name":"poolId","type":"bytes32"},{"internalType":"address","name":"assetIn","type":"address"},{"internalType":"address","name":"assetOut","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"},{"internalType":"bytes","name":"userData","type":"bytes"}],"internalType":"struct IVault.SingleSwap","name":"singleSwap","type":"tuple"},{"components":[{"internalType":"address","name":"sender","type":"address"},{"internalType":"bool","name":"fromInternalBalance","type":"bool"},{"internalType":"address payable","name":"recipient","type":"address"},{"internalType":"bool","name":"toInternalBalance","type":"bool"}],"internalType":"struct IVault.FundManagement","name":"funds","type":"tuple"},{"internalType":"uint256","name":"limit","type":"uint256"},{"internalType":"uint256","name":"deadline","type":"uint256"}],"name":"swap","outputs":[{"internalType":"uint256","name":"amountCalculated","type":"uint256"}],"stateMutability":"payable","type":"function"},
    {"inputs":[{"internalType":"bytes32","name":"poolId","type":"bytes32"}],"name":"getPoolTokens","outputs":[{"internalType":"address[]","name":"tokens","type":"address[]"},{"internalType":"uint256[]","name":"balances","type":"uint256[]"},{"internalType":"uint256","name":"lastChangeBlock","type":"uint256"}],"stateMutability":"view","type":"function"}
]

BALANCER_POOL_ABI = [
    {"inputs":[],"name":"getPoolId","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"}
]

WAGNO_ABI = [
    {"inputs":[{"name":"assets","type":"uint256"},{"name":"receiver","type":"address"}],"name":"deposit","outputs":[{"name":"","type":"uint256"}],"stateMutability":"nonpayable","type":"function"},
    {"inputs":[{"name":"owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"name":"shares","type":"uint256"},{"name":"receiver","type":"address"},{"name":"owner","type":"address"}],"name":"redeem","outputs":[{"name":"","type":"uint256"}],"stateMutability":"nonpayable","type":"function"}
]