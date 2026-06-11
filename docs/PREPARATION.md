# Preparation Guide — accounts, keys, wallets

What you need before each capability goes live. The offline demo and the
full test suite need **none** of this.

## Security rules (read first)

1. **Dedicated throwaway wallets only.** The APEX agent wallet and the x402
   payer wallet must be fresh keys created for this hackathon. Never reuse a
   key that has ever held mainnet funds.
2. **Nothing secret enters git.** `.env` is gitignored; `PRIVATE_KEY` is
   needed on the SDK's first run only (it encrypts to
   `~/.bnbagent/wallets/` as Keystore V3) — delete it from `.env` afterward.
3. Everything on-chain here is **BSC testnet**; the bnbagent SDK refuses
   mainnet today anyway.

## Checklist by capability

### 1 · CMC Agent Hub (live data + Hub signals)
- [ ] Account + API key: https://pro.coinmarketcap.com (free tier is fine to
      start; Day-1 test T1 reveals any plan gating on the v4 DEX endpoints)
- [ ] `CMC_API_KEY` in `.env`
- [ ] One PancakeSwap V3 pool address for the T1 probe
      (`SMOKE_POOL_ADDRESS`) — pick the pair you'll research
- [ ] MCP (for Hub indicator wiring, task T2): connect
      `https://mcp.coinmarketcap.com/mcp` from your agent runtime with header
      `X-CMC-MCP-API-KEY`

### 2 · Trust Wallet Agent Kit (token risk screen)
- [ ] Developer access via https://portal.trustwallet.com
- [ ] `TWAK_API_BASE`, `TWAK_API_KEY` in `.env`
- [ ] Day-1 task T3: confirm the security/risk endpoint path + response
      schema; adjust `rangepilot/twak/risk_screen.py` if field names differ

### 3 · BNB AI Agent SDK / APEX (hireable agent, testnet)
- [ ] `pip install "bnbagent[server,ipfs]" uvicorn`
- [ ] Fresh agent wallet: `PRIVATE_KEY` (first run only) + `WALLET_PASSWORD`
- [ ] Gas: tBNB faucet → https://www.bnbchain.org/en/testnet-faucet
- [ ] Payment token: U faucet → https://united-coin-u.github.io/u-faucet/
      (client wallet needs U to fund escrow; agent wallet needs nothing —
      ERC-8004 registration is gas-sponsored via MegaFuel)
- [ ] IPFS pinning JWT (Pinata or compatible): `STORAGE_PROVIDER=ipfs`,
      `STORAGE_API_KEY` — required so the UMA evaluator can fetch deliverables
- [ ] `SERVICE_PRICE` (wei, 18 decimals; default 1 U)
- [ ] A second throwaway wallet as the *client* for the hiring demo
      (`scripts/apex_client_demo.py`), funded with tBNB + U

### 4 · x402 keyless data path (optional)
- [ ] `pip install x402 eth-account`
- [ ] Fresh wallet on **Base** holding a few USDC ($0.01/request)
- [ ] `X402_PRIVATE_KEY` in `.env`

### 5 · LLM narrative polish (optional)
- [ ] Any OpenAI-compatible endpoint (`LLM_API_BASE`, `LLM_API_KEY`,
      `LLM_MODEL`). Numbers are never LLM-generated either way.

## Order of operations

```bash
cp .env.example .env            # fill incrementally
python scripts/day1_smoke_tests.py    # after every addition — T0 must stay GO
```

T1/T2/T3 NO-GOs print their exact fix location; nothing else in the repo
blocks on them (loud fallbacks everywhere).
