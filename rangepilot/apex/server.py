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
            return {"status": "queued", "jobId": body.get("jobId", "mock-job-123")}

        @app.get("/job/{job_id}/response")
        def get_response(job_id: str):
            return {
                "jobId": job_id,
                "status": "completed",
                "deliverable": {
                    "spec_sha256": "f36e09205ea12ca53bf05a2014d8c2a3b1efcb39432403a64239e96d37972e30"
                },
            }

        return app
    return create_apex_app(on_job=handle_job)


# uvicorn target — created lazily so the package imports clean without the SDK
try:
    app = build_app()
except Exception:  # SDK absent in offline/dev environments
    app = None
