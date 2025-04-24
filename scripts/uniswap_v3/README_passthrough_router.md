# Uniswap V3 Passthrough Router Swap Script

This script allows you to execute swaps through a Uniswap V3 pool using a `UniswapV3PassthroughRouter` contract.

## Prerequisites

- You must be the **owner** of the UniswapV3PassthroughRouter contract to use this script
- The target Uniswap V3 pool must be authorized (the script will attempt to authorize it)
- Sufficient token balance to perform the swap

## Updated Contract Structure

The script has been updated to work with the latest version of the UniswapV3PassthroughRouter contract which uses a struct-based parameter system:

```solidity
// New swap function signature
function swap(
    PoolInteraction calldata poolInfo,
    TokenInteraction calldata tokenInfo
) external returns (int256 amount0, int256 amount1);

// Struct definitions
struct TokenInteraction {
    bool zeroForOne;
    int256 amountSpecified;
    uint160 sqrtPriceLimitX96;
    uint256 minAmountReceived;
}

struct PoolInteraction {
    address pool;
    address recipient;
    bytes callbackData;
}
```

## Configuration

Set the following environment variables in your `.env` file:

```
# Required
PRIVATE_KEY=your_private_key
V3_PASSTHROUGH_ROUTER_ADDRESS=0xYourPassthroughRouterAddress

# Pool and Token settings (pre-configured with NO pool and tokens)
UNISWAP_V3_POOL_ADDRESS=0x6E33153115Ab58dab0e0F1E3a2ccda6e67FA5cD7
RECIPIENT_ADDRESS=0x33A0b5d7DA5314594D2C163D448030b9F1cADcb2
TOKEN_IN_ADDRESS=0xE1133Ef862f3441880adADC2096AB67c63f6E102  # NO_SDAI
TOKEN_OUT_ADDRESS=0xf1B3E5Ffc0219A4F8C0ac69EC98C97709EdfB6c9  # NO_GNO

# Swap parameters
AMOUNT_TO_SWAP=1.0  # or use AMOUNT_TO_SWAP_WEI=1000000000000000000
GNOSIS_RPC_URL=https://rpc.gnosis.gateway.fm
```

## Usage

```bash
# Run with default settings from .env file
python scripts/uniswap_v3/passthrough_router_swap.py
```

## Token Configuration

By default, the script is configured to swap between the following tokens:

- **NO_SDAI** (TOKEN_IN): `0xE1133Ef862f3441880adADC2096AB67c63f6E102`
- **NO_GNO** (TOKEN_OUT): `0xf1B3E5Ffc0219A4F8C0ac69EC98C97709EdfB6c9`

The script uses the Uniswap V3 NO Pool: `0x6E33153115Ab58dab0e0F1E3a2ccda6e67FA5cD7`

## Swap Parameters

The script is configured with these default swap parameters:

- `zeroForOne`: `true` (swapping token0 for token1)
- `sqrtPriceLimitX96`: `4295128740` (minimum price limit)
- `amountSpecified`: `1000000000000000000` (1 token with 18 decimals)
- `minAmountReceived`: 1% of the input amount (slippage protection)

## Key Features

- Verifies you are the owner of the passthrough router
- Authorizes the pool if not already authorized
- Approves token spending if needed
- Executes the swap with detailed logging
- Reports token balances before and after the swap
- Includes minimum amount protection (slippage control)

## Important Notes

1. The `zeroForOne` parameter is set to `True` by default, which is correct for the NO pool token ordering.

2. The script does not include price quotation since the passthrough router itself does not provide a quotation mechanism. For price estimates, you would need to use a separate Quoter contract.

3. The `sqrtPriceLimitX96` parameter is set to `4295128740`, which sets a minimum price limit for the swap.

4. Make sure your private key has owner access to the specified router. The swap will fail if you're not the owner.

## Example Output

```
✅ Connected to chain (chainId: 100)
🔑 Using owner account: 0xYourAddress
💰 10.0 NO_SDAI balance
💰 5.0 NO_GNO balance before swap
🔄 Swap amount: 1.0 NO_SDAI

Current allowance for router: 0.0
🔑 Approving pass-through router to spend our NO_SDAI...
⏳ Approval tx sent: 0x...
✅ Approval successful.

🔑 Authorizing pool for the router...
⏳ Pool authorization tx sent: 0x...
✅ Pool authorization successful.

🔄 Executing Uniswap V3 swap...
Pool: 0x6E33153115Ab58dab0e0F1E3a2ccda6e67FA5cD7
Recipient: 0x33A0b5d7DA5314594D2C163D448030b9F1cADcb2
Zero for One: True
Amount: 1000000000000000000 (1.0 tokens)
Sqrt Price Limit X96: 4295128740
Min Amount Received: 10000000000000000 (0.01 tokens)
Token In: 0xE1133Ef862f3441880adADC2096AB67c63f6E102 (NO_SDAI)
Token Out: 0xf1B3E5Ffc0219A4F8C0ac69EC98C97709EdfB6c9 (NO_GNO)
⏳ Swap transaction sent: 0x...
✅ Swap successful!
🔹 NO_GNO after swap (owner): 5.123
🔹 Gained (owner): 0.123 NO_GNO
🔹 NO_GNO balance (recipient): 1.5

🔗 Explorer: https://gnosisscan.io/tx/0x...
``` 