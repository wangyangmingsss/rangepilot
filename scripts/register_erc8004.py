#!/usr/bin/env python3
"""Register the RangePilot agent identity on-chain (ERC-8004, BSC testnet).

Gas-free via MegaFuel paymaster. One-time setup. Follows the bnbagent SDK
quickstart exactly. Requires .env with WALLET_PASSWORD (+ PRIVATE_KEY on the
first run only — it is encrypted to ~/.bnbagent/wallets/ and can be removed).

Usage:  python scripts/register_erc8004.py --endpoint https://your-host/.well-known/agent-card.json
"""
import argparse
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="rangepilot-strategy-agent")
    ap.add_argument("--description",
                    default="Generates executability-validated, backtested "
                            "PancakeSwap V3 market-making StrategySpecs from "
                            "CMC market data. Hireable via APEX (ERC-8183).")
    ap.add_argument("--endpoint", required=True,
                    help="public A2A agent-card URL of your APEX server")
    ap.add_argument("--network", default=os.getenv("NETWORK", "bsc-testnet"))
    args = ap.parse_args()

    try:
        from bnbagent import ERC8004Agent, AgentEndpoint, EVMWalletProvider
    except Exception as e:
        print(f"bnbagent SDK missing: pip install bnbagent  ({e})")
        return 1

    wallet = EVMWalletProvider(
        password=os.getenv("WALLET_PASSWORD"),
        private_key=os.getenv("PRIVATE_KEY") or None,
    )
    sdk = ERC8004Agent(network=args.network, wallet_provider=wallet)
    uri = sdk.generate_agent_uri(
        name=args.name,
        description=args.description,
        endpoints=[AgentEndpoint(name="A2A", endpoint=args.endpoint, version="0.3.0")],
    )
    result = sdk.register_agent(agent_uri=uri)
    print(f"registered agentId={result['agentId']} tx={result['transactionHash']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
