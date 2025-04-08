# Futarchy Bots

A collection of tools for interacting with futarchy markets on Gnosis Chain.

## Tools

### Price Impact Calculator

A tool for calculating the price impact of trades in various pools:

- Balancer sDAI/waGNO pool
- SushiSwap YES conditional pool
- SushiSwap NO conditional pool

The calculator provides accurate price impact calculations for different trade sizes, helping traders make informed decisions.

### SushiSwap V3 Liquidity Provider

A tool for adding and managing concentrated liquidity positions in SushiSwap V3 pools:

- Create new concentrated liquidity positions with custom price ranges
- Increase liquidity in existing positions
- Decrease liquidity from positions
- Collect accumulated fees
- View detailed position information

This functionality allows users to provide liquidity to the YES and NO markets with greater capital efficiency.

## Development Setup

### Prerequisites

- Python 3.8+
- Git

### First-time Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/futarchy-bots.git
cd futarchy-bots
```

2. Run the development setup script:
```bash
./scripts/setup_dev.sh
```

This script will:
- Create a Python virtual environment
- Install all required dependencies
- Set up the package in development mode

3. Create a `.env` file with your configuration:
```
PRIVATE_KEY=your_private_key_here
RPC_URL=your_rpc_url_here
```

### Daily Development

1. Activate the virtual environment:
```bash
source venv/bin/activate
```

2. When dependencies change:
- Run the setup script again to update:
```bash
./scripts/setup_dev.sh
```

## Usage

### Price Impact Calculator

```bash
python price_impact_calculator.py --amount 0.1
```

Options:
- `--amount`: Amount of GNO to calculate price impact for (default: 0.01)

### SushiSwap V3 Liquidity Provider

The liquidity provider functionality is integrated into the main futarchy bot and can be accessed through the CLI menu.

## Experimental CLI (Refactored)

An experimental command-line interface using a refactored MVC-like architecture is available.

### Usage (Experimental CLI)

```bash
# Activate environment
source venv/bin/activate 

# Check balances
python refactored_main.py balances

# Buy GNO with sDAI (executes transaction)
python refactored_main.py buy_gno 0.1 

# Sell GNO for sDAI (executes transaction)
python refactored_main.py sell_gno 0.01
```

### Simulation Mode (`--simulate`)

Several commands support a simulation mode using the `--simulate` flag. This allows you to see the expected outcome of an operation (like a swap or wrap/unwrap) without sending a transaction or spending gas.

**How it works:** The simulator uses `eth_call` to query the blockchain state and predict the results of contract function calls.

**Example Usage:**

```bash
# Simulate buying 0.5 GNO with sDAI
python refactored_main.py buy_gno 0.5 --simulate

# Simulate selling 0.01 GNO for sDAI
python refactored_main.py sell_gno 0.01 --simulate
```

**Sample Simulation Output:**

*   **Buy Simulation (`buy_gno 0.5 --simulate`)**

    ```
    🔄 SIMULATING buy GNO using 0.500000 sDAI...
    🔄 SIMULATING Step 1/2: Swapping 0.5 sDAI for waGNO on Balancer...
    Initial Balances:
      0xaf2047...: 4.234152813527603567 (4234152813527603567 wei)
      0x7c16F0...: 0.018774436437561806 (18774436437561806 wei)
    
    🔄 Simulating swap of 0.5 0xaf2047... -> 0x7c16F0......
       -> Simulation Result: ~0.005023571141815315 out (5023571141815315 wei)
       -> Estimated Price: 99.530789 in/out
       - Simulation Result: Would receive ~0.005024 waGNO
       - Estimated Price: ~99.530789 sDAI per waGNO
    🔄 SIMULATING Step 2/2: Unwrapping 0.005024 waGNO to GNO...
    
    Current Balances:
    waGNO: 0.018774436437561806 (18774436437561806 wei)
    Amount to unwrap: 0.005023571141815315 waGNO (5023571141815314 wei)
    
    🔄 Simulating unwrap of 0.005023571141815315 waGNO to GNO...
       -> Simulation result: ~0.005030927946411399 GNO assets
       - Simulation Result: Would receive ~0.005031 GNO
    
    ✅ Buy GNO simulation completed.
    ```

*   **Sell Simulation (`sell_gno 0.01 --simulate`)**

    ```
    🔄 SIMULATING sell 0.010000 GNO for sDAI...
    🔄 SIMULATING Step 1/2: Wrapping 0.01 GNO to waGNO...
    🔄 Simulating wrap of 0.01 GNO to waGNO...
       -> Simulation result: Assuming ~0.010000000000000000 waGNO shares (simulation call skipped due to internal checks)
       - Simulation Result: Assumed ~0.010000 waGNO (due to simulation limitations)
    🔄 SIMULATING Step 2/2: Swapping 0.010000 waGNO for sDAI on Balancer...
    Initial Balances:
      0x7c16F0...: 0.018774436437561806 (18774436437561806 wei)
      0xaf2047...: 4.234152813527603567 (4234152813527603567 wei)
    
    🔄 Simulating swap of 0.01 0x7c16F0... -> 0xaf2047......
       -> Simulation Result: ~0.990334608804374833 out (990334608804374833 wei)
       -> Estimated Price: 0.010098 in/out
       - Simulation Result: Would receive ~0.990335 sDAI
       - Estimated Price: ~0.010098 waGNO per sDAI
    
    ✅ Sell GNO simulation completed.
    ```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This software is provided for educational and research purposes only. Use at your own risk. The authors are not responsible for any financial losses incurred through the use of these tools.
