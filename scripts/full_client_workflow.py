#!/usr/bin/env python3
"""Full client workflow: hire RangePilot agent on BSC testnet.

This script executes the complete ERC-8183 lifecycle:
1. create_job -> 2. register_job -> 3. set_budget -> 4. fund
5. POST /job/execute (triggers agent to submit on-chain)
6. Print instructions for settling after the dispute window.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

from bnbagent.erc8183 import ERC8183Client
from bnbagent.wallets import EVMWalletProvider

# Load env
import os
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

CLIENT_PK = (
    os.getenv("CLIENT_PK")
    or "0xbe9baa477e73a275aec2c44a265d489c33537064ba11ea0e0d3fd53f7909a62d"
)
PROVIDER_ADDR = (
    os.getenv("PROVIDER_ADDR") or "0x6d662707910440fbe94f13bfc103e61018b77808"
)
AGENT_URL = os.getenv("AGENT_URL") or "http://127.0.0.1:8000"
WALLET_PASSWORD = os.getenv("WALLET_PASSWORD") or "RangePilotSecurePass123!"


def main() -> int:
    print("== Full Client Workflow (BSC Testnet) ==")

    # 1. Initialize Client
    print("\n[1/6] Initializing client wallet...")
    wallet = EVMWalletProvider(
        password=WALLET_PASSWORD, private_key=CLIENT_PK, persist=False
    )
    client = ERC8183Client(wallet_provider=wallet, network="bsc-testnet")
    print(f"Client address: {client.address}")

    # 2. Create Job
    print("\n[2/6] Creating job...")
    job_desc = {
        "pair": {"base": "WBNB", "quote": "USDT"},
        "capital_quote": 5000,
        "risk": "balanced",
        "fee_tier": 2500,
    }
    # Expire in ~2.5 days to satisfy OptimisticPolicy dispute_window (1 day) + buffer
    expired_at = int(time.time()) + 200000

    res = client.create_job(
        provider=PROVIDER_ADDR,
        expired_at=expired_at,
        description=json.dumps(job_desc),
    )
    job_id = res["jobId"]
    print(f"Job created! jobId: {job_id}")

    # 3. Register Job
    print("\n[3/6] Registering job with OptimisticPolicy...")
    client.register_job(job_id)
    print("Registered.")

    # 4. Set Budget & Fund
    print("\n[4/6] Setting budget and funding...")
    decimals = client.token_decimals()
    budget = 1 * (10**decimals)  # 1 U token

    # Set budget
    print("  -> Setting budget...")
    client.set_budget(job_id, budget)
    print("  -> Budget set.")

    # Approve commerce contract to spend tokens
    print("  -> Approving payment token for commerce contract...")
    client.approve_payment_token(client.commerce.address, budget)
    print("  -> Approved.")

    # Fund
    print("  -> Funding job...")
    client.fund(job_id, budget)
    print(f"  -> Funded {budget / 10**decimals} U tokens. Job is now FUNDED.")

    # 5. Trigger Agent Execution (Simulated locally for reliability)
    print("\n[5/6] Triggering agent execution (simulating /job/execute)...")
    import os
    from bnbagent.erc8183 import DeliverableManifest, SCHEMA_VERSION
    from rangepilot.apex.handler import parse_job_description, generate

    provider_pk = (
        os.getenv("PRIVATE_KEY")
        or "0xd8b9126f30d8965189ae036421d6d7f7d39ba7e748e7d23bcb15862c72fe4443"
    )

    try:
        # Initialize provider client
        provider_wallet = EVMWalletProvider(
            password=WALLET_PASSWORD, private_key=provider_pk, persist=False
        )
        provider_client = ERC8183Client(
            wallet_provider=provider_wallet, network="bsc-testnet"
        )

        # Generate the deliverable using RangePilot engine
        req = parse_job_description(json.dumps(job_desc))
        result = generate(req)
        deliverable_json = json.dumps(result.spec, indent=2, ensure_ascii=False)

        # Create manifest
        manifest = DeliverableManifest(
            version=SCHEMA_VERSION,
            job_id=job_id,
            chain_id=provider_client.network.chain_id,
            contracts={
                "commerce": provider_client.commerce.address,
                "router": provider_client.router.address,
                "policy": provider_client.policy.address,
            },
            response={"content": deliverable_json, "content_type": "application/json"},
        )

        # Submit to chain
        deliverable_url = "ipfs://mock-cid-for-demo"
        print("  -> Provider submitting deliverable to chain...")
        tx_hash = provider_client.submit(
            job_id, manifest.manifest_hash(), {"deliverable_url": deliverable_url}
        )

        print(f"Agent execution completed!")
        print(f"  Tx Hash: {tx_hash}")
        print(f"  Spec SHA256: {result.spec['spec_sha256']}")
    except Exception as e:
        print(f"ERROR: Agent execution failed: {e}")
        import traceback

        traceback.print_exc()
        return 1

    # 6. Settlement Instructions
    print("\n[6/6] Next Steps (Settlement)")
    window = client.policy.dispute_window()
    print(
        f"The job is now SUBMITTED. You must wait for the UMA dispute window to pass."
    )
    print(f"Dispute window duration: {window} seconds (~{window // 60} minutes).")
    print(
        f"\nTo settle and release funds to the agent, run this command after the window expires:"
    )
    print(
        f"  python -c \"from bnbagent.erc8183 import ERC8183Client; from bnbagent.wallets import EVMWalletProvider; import os; from dotenv import load_dotenv; load_dotenv(); c = ERC8183Client(EVMWalletProvider(password=os.getenv('WALLET_PASSWORD','RangePilotSecurePass123!'), private_key=os.getenv('CLIENT_PK','{CLIENT_PK}'), persist=False), 'bsc-testnet'); c.settle('{job_id}'); print('Settled!')\""
    )

    print("\n✅ Full client workflow initiated successfully!")
    print(f"🔗 View job on BscScan (check contract events for jobId {job_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
