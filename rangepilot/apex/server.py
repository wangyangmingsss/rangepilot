"""APEX agent server entrypoint.

Run (after `pip install "bnbagent[server,ipfs]"` and configuring .env):

    uvicorn rangepilot.apex.server:app --port 8000

Env contract is the bnbagent SDK's own (PRIVATE_KEY first run only,
WALLET_PASSWORD, STORAGE_PROVIDER=ipfs, STORAGE_API_KEY, SERVICE_PRICE,
NETWORK=bsc-testnet). Testnet contracts are pre-deployed; tBNB + U token
faucets are linked in docs/PREPARATION (gas-free ERC-8004 registration via
MegaFuel paymaster).
"""

from __future__ import annotations

from .handler import handle_job

try:
    from bnbagent.apex.server import create_apex_app  # type: ignore
except Exception as e:  # pragma: no cover
    create_apex_app = None
    _import_error = e


def build_app():
    if create_apex_app is None:
        # Fallback mock server for demonstration when bnbagent.apex is unavailable
        from fastapi import FastAPI
        from pydantic import BaseModel
        import hashlib
        import json

        app = FastAPI(title="RangePilot APEX Agent (Mock)")

        class NegotiateRequest(BaseModel):
            service_type: str
            description: str
            quality_standards: str
            deliverables: str

        @app.get("/health")
        def health():
            return {"status": "ok", "service": "rangepilot-apex-mock"}

        @app.get("/status")
        def status():
            return {
                "agent": "0x6d662707910440fbe94f13bfc103e61018b77808",
                "service_price": "1000000000000000000",
                "payment_token": "U",
                "network": "bsc-testnet",
                "note": "Mock server - bnbagent.apex not available in current SDK version",
            }

        @app.post("/negotiate")
        def negotiate(req: NegotiateRequest):
            payload_hash = hashlib.sha256(req.description.encode()).hexdigest()
            return {
                "status": "accepted",
                "quoted_price": "1000000000000000000",
                "payload_hash": payload_hash,
                "message": "Terms accepted. Proceed to on-chain job creation.",
            }

        @app.post("/job/execute")
        def execute_job(body: dict):
            import os
            from bnbagent.erc8183 import (
                ERC8183Client,
                DeliverableManifest,
                SCHEMA_VERSION,
            )
            from web3 import Web3
            from ..handler import parse_job_description, generate
            import json

            job_id = body.get("jobId")
            if not job_id:
                return {"error": "jobId required"}, 400

            # Get provider private key from env
            provider_pk = os.getenv("PRIVATE_KEY")
            if not provider_pk:
                return {"error": "PRIVATE_KEY not set in .env"}, 500

            try:
                # Initialize provider client
                provider_client = ERC8183Client(provider_pk, "bsc-testnet")

                # Generate the deliverable using RangePilot engine
                job_desc = body.get("description", "{}")
                req = parse_job_description(job_desc)
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
                    response={
                        "content": deliverable_json,
                        "content_type": "application/json",
                    },
                )

                # Submit to chain
                # Note: In a real scenario, this would be uploaded to IPFS first.
                # Here we use a placeholder URL, but the hash is anchored on-chain.
                deliverable_url = "ipfs://mock-cid-for-demo"
                tx_hash = provider_client.submit(
                    job_id,
                    manifest.manifest_hash(),
                    {"deliverable_url": deliverable_url},
                )

                return {
                    "status": "submitted",
                    "jobId": job_id,
                    "tx_hash": tx_hash,
                    "spec_sha256": result.spec["spec_sha256"],
                    "message": "Deliverable submitted to chain successfully.",
                }
            except Exception as e:
                return {"error": str(e)}, 500

        @app.get("/job/{job_id}/response")
        def get_response(job_id: str):
            import os
            from bnbagent.erc8183 import ERC8183Client

            provider_pk = os.getenv("PRIVATE_KEY")
            if not provider_pk:
                return {"error": "PRIVATE_KEY not set"}, 500

            try:
                client = ERC8183Client(provider_pk, "bsc-testnet")
                job = client.get_job(job_id)
                return {
                    "jobId": job_id,
                    "status": job.status.name,
                    "deliverable_url": job.deliverable_url
                    if hasattr(job, "deliverable_url")
                    else None,
                    "message": "Check BscScan for tx details.",
                }
            except Exception as e:
                return {"error": str(e)}, 500

        return app
    return create_apex_app(on_job=handle_job)


# uvicorn target — created lazily so the package imports clean without the SDK
try:
    app = build_app()
except Exception:  # SDK absent in offline/dev environments
    app = None
