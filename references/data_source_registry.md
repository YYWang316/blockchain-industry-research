---
schema_version: 1
description: Canonical registry of external data sources for Stack Anamnesis. Each entry covers endpoint, auth model, rate limit, coverage, documented quirks, and which subject_class values it is most relevant for. Companion: references/subject_taxonomy.md (the five classes that key into this registry). Read before authoring or modifying any data-collection agent.
---

# Data Source Registry

This file is the **canonical contract** for which external data sources Stack Anamnesis is allowed to call, what each one provides, and what its limits are. Six sources are registered:

1. **DefiLlama** — protocol/chain TVL, stablecoin caps, yields. Free.
2. **Dune** — custom SQL across indexed chains. Mixed free/paid.
3. **Etherscan family** — raw EVM (and Solscan for Solana) tx data, contract source, contract reads. Free tier with API key.
4. **CoinGecko** — price, market cap, volume, coin metadata. Free tier rate-limited.
5. **RPC tier** — Alchemy / Infura / QuickNode JSON-RPC for direct contract reads. Per-provider tier.
6. **SEC EDGAR** — public-company filings (10-K, 10-Q, 8-K), XBRL company facts, insider transactions. Free; **conditional** consumer of the `P0_sec_email` gate (only fires when `subject_entity.listed` or `parent_or_issuer_entity.listed` per `references/subject_relationships.yaml`).

> **TD-009 closure.** SEC EDGAR re-entered the registry in Phase B.0 deliverable #1.5. Between Phase A and Phase B, the registry was a five-source set and the SEC-specific secret-handling pattern was held in `references/TODO.md` TD-009 as a deferred design note. The re-add restores the sixth source and the I-003-pattern secret-handling rule returns to `MEMORY.md`'s Privacy Invariants section in B.0 deliverable #16. TD-009's status in `references/TODO.md` should be flipped to closed in the same pass.

Any data-collection agent that wants to call something *not* in this registry must (a) record `event: "out_of_registry"` in `meta/run.jsonl` and (b) halt for human confirmation before the call. Adding a new source is a deliberate change to this file. Registry-drift incidents are exactly the shape that earns an `INCIDENTS.md` entry.

The registry is also keyed off `references/subject_taxonomy.md`. The **"relevant for"** column in each entry below maps to the five subject classes and is how the orchestrator selects which subset of this registry to consult for a given run.

---

## 1. DefiLlama

**Domain.** `api.llama.fi` (general), `stablecoins.llama.fi`, `yields.llama.fi`, `coins.llama.fi`, `bridges.llama.fi`. Documentation: `defillama.com/docs/api`.

**Auth.** None. Open API.

**Rate limit.** Undocumented; empirically ~300 requests / 5 minutes per IP across the `api.llama.fi` host. Per-endpoint quotas tighter on `coins.llama.fi` (historical price endpoints). **Hard rule for this harness**: cap at **1 req/sec** with a 100ms jitter, regardless of empirical headroom. The harness has no business burning DefiLlama's free hosting; respectful pacing keeps the source usable.

**What you get.**
- `/protocols`, `/protocol/{slug}` — TVL by protocol, with chain breakdown and historical daily TVL.
- `/stablecoins`, `/stablecoin/{id}` — circulating supply per stablecoin, per chain.
- `/chains` — TVL by chain, with breakdown by protocol category.
- `/yields/pools` — APY by pool with TVL and chain.
- `/bridges` — bridge volume and TVL.
- `/coins/prices/current/{coins}`, `/coins/prices/historical/{ts}/{coins}` — spot and historical prices by token (CoinGecko-style coin IDs).

**Documented quirks.**
- Chain naming inconsistent across endpoints — use the lowercase canonical form returned by `/chains` (e.g., `ethereum`, `base`, `arbitrum`, not `Ethereum` or `ETH`).
- Category overlap: a protocol can appear in multiple categories (DEX + lending). Sum across categories will double-count TVL.
- CORS-enabled for browser calls.
- Historical TVL series have occasional gaps after protocol incidents; treat null days as nulls, not zeros.

**Relevant for.** `stablecoin_issuer` (caps, chain split), `chain` (TVL, fees, category mix), `orchestrator` (bridge volume).

---

## 2. Dune

**Domain.** `dune.com` (web UI for queries and dashboards), `api.dune.com` (API). Documentation: `docs.dune.com`.

**Auth.** API key required for `api.dune.com`. Free tier requires sign-up; paid tiers via subscription.

**Rate limit / billing model.**
- **Free tier** ("Community Plan"): 10K rows/month included; 4 concurrent executions; "medium" engine only. Cached results are free.
- **Paid tiers** (Plus / Premium / Enterprise): higher row caps, more concurrency, "large" engine, longer cache TTLs.
- Costs accrue by **credits per query** (function of rows scanned + engine size), not requests. A cached read is 0 credits.

**Hard rule for this harness.** Free tier is the default. The orchestrator must prefer **cached** community queries (read by query ID) over fresh executions. Fresh executions are gated: the calling agent records the credit cost estimate before submission and the orchestrator caps total fresh-exec spend at **2000 credits / run** unless the user explicitly overrides per-run.

**What you get.**
- Custom SQL over indexed chain data: Ethereum + all major L2s (Arbitrum, Base, Optimism, Polygon, etc.) + Solana + a long tail of others.
- Tens of thousands of community-shared queries and dashboards.
- Real-time-ish data (latency varies by chain — typically minutes for Ethereum, longer for L2s after batches post).
- Webhook support for query-completion notifications (paid tiers).

**Documented quirks.**
- Query quality varies wildly across the community library. Pin to known-good queries by ID; treat all others as inputs to a sanity check, not as ground truth.
- The underlying chain decoders evolve. A query that worked yesterday can return nulls today if a decoded table got renamed. Validators must check for unexpected null rates.
- Solana data is later-arriving and noisier than EVM. Treat Solana-specific freshness with a longer tolerance.
- Public sharing of a query exposes the SQL but not the credit cost.

**Relevant for.** All five classes — Dune is the most cross-cutting source. Especially `chain` (fees, MEV, activity), `orchestrator` (bridge volume by route), `wallet` (active addresses), `agentic_payment_layer` (settlement footprint where on-chain).

---

## 3. Etherscan family (and Solscan)

**Domain.** Per chain:
- `etherscan.io` — Ethereum L1
- `basescan.org` — Base
- `arbiscan.io` — Arbitrum One + Nova
- `optimistic.etherscan.io` — Optimism
- `polygonscan.com` — Polygon PoS
- `bscscan.com` — BNB Chain
- `snowtrace.io` — Avalanche C-Chain
- `solscan.io` — Solana (not part of Etherscan, but the closest substitute and treated as a peer source here)
- (other Etherscan-family explorers exist for Linea, Scroll, etc. — same API shape, separate keys)

Documentation: `docs.etherscan.io` (with chain-specific addenda).

**Auth.** API key required, **one per chain** in the Etherscan family. Etherscan recently introduced a unified "Etherscan V2" key that covers most family chains with a single key — prefer that when available. Solscan has its own key.

**Rate limit.**
- Free tier: **5 req/sec**, 100,000 calls/day. Standard across the family.
- Paid tiers (Standard / Advanced / Pro): up to 30 req/sec, higher daily caps, priority endpoints. Per-chain billing.

**Hard rule for this harness.** Use 4 req/sec as the working ceiling (one below the documented limit, since burst behaviour is unforgiving). On 429, exponential backoff starting at 2s, max 5 retries per request. Key is read from `~/.config/anamnesis/etherscan.key` and never logged.

**What you get.**
- Raw transaction listings by address (normal, internal, token, NFT).
- Contract source code + ABI (when verified).
- Contract read functions via the proxy interface.
- Account balances at any block (free for recent blocks; archive-block reads gated to paid tiers on some chains).
- Gas oracle, block stats.
- Token transfer histories (ERC-20, ERC-721, ERC-1155).
- Verified-contract registry (useful for identifying issuer treasury contracts, bridge contracts, MEV bots).

**Documented quirks.**
- Each chain has its own daily quota — burning Ethereum's quota does not deplete Base's.
- Rate-limit windows can shift after suspected abuse (the "5 req/sec" becomes effectively lower for an hour or two).
- Address checksums are case-sensitive in some endpoints and case-insensitive in others — always lowercase before hashing/comparing.
- Solscan's API surface differs significantly from Etherscan's; treat as a separate adapter, not a drop-in.
- "Internal transactions" endpoints lag behind external by up to a few blocks.

**Relevant for.** `chain` (block stats, fee data), `stablecoin_issuer` (treasury-wallet reads, total-supply reads), `wallet` (address activity, token holdings — when address is known), `agentic_payment_layer` (settlement-contract reads).

---

## 4. CoinGecko

**Domain.** `api.coingecko.com` (free), `pro-api.coingecko.com` (paid / "Pro" tier). Documentation: `docs.coingecko.com`.

**Auth.**
- Free / "Demo" tier: optional `x-cg-demo-api-key` header. Without a key, slightly stricter limits; with a demo key, slightly looser.
- Pro tier: required `x-cg-pro-api-key` header. Different host (`pro-api.coingecko.com`).

**Rate limit.**
- Free / demo: **10–30 calls/minute** (undocumented exactly; observed). Burst-sensitive — slamming 10 in one second can trigger a temporary block even if the per-minute average is under cap.
- Pro tier: 500 calls/min and up depending on plan.

**Hard rule for this harness.** Free tier default. Cap at **1 req/2.5 sec** with 200ms jitter. Use the demo key when present. On 429, back off 60 seconds before any further CoinGecko request from any agent in the run.

**What you get.**
- Spot price, market cap, 24h/7d/30d/1y volume by coin.
- Coin metadata: description, GitHub repo, official links, exchange listings.
- Historical price/volume (limited window on free tier).
- DEX trade data (`/onchain` endpoints, GeckoTerminal-style; some are free, some Pro-only).
- Exchange data (volumes by pair).
- Stablecoin-specific endpoints: peg deviation, market dominance.

**Documented quirks.**
- Coin IDs are slug-based, not symbol-based. Symbols collide (e.g., multiple coins use `LINK`). Always resolve to the slug ID (e.g., `chainlink`) via `/coins/list` before any other query.
- Free tier rate-limit window is undocumented and varies in practice — assume it can shift down without warning, and treat 429s as a signal to slow down for the rest of the run.
- Some pages have a long cache TTL (e.g., metadata changes can take hours to propagate).
- The free tier's historical-range endpoints cap lookback at 365 days. Earlier data requires Pro.

**Relevant for.** `stablecoin_issuer` (peg deviation, dominance), `chain` (native token market data), `agentic_payment_layer` (token if any, market response to announcements), `wallet` (wallet's native token if any).

---

## 5. RPC tier — Alchemy / Infura / QuickNode

**Domain.** Per-provider URLs, **per-chain endpoints**:
- Alchemy: `<chain>-mainnet.g.alchemy.com/v2/<API_KEY>` (e.g., `eth-mainnet`, `base-mainnet`, `arb-mainnet`, `opt-mainnet`, `polygon-mainnet`, `solana-mainnet`).
- Infura: `<chain>-mainnet.infura.io/v3/<API_KEY>` (Ethereum + select chains).
- QuickNode: `<random-subdomain>.<chain>.quiknode.pro/<API_KEY>/` (per-endpoint provisioned).

Documentation: `docs.alchemy.com`, `docs.infura.io`, `www.quicknode.com/docs`.

**Auth.** API key per chain per provider, read from `~/.config/anamnesis/<provider>.key`. Never logged.

**Rate limit / billing model.**
- **Alchemy** free: 300 CU/sec (compute units, not requests; method-dependent), ~30M CU/month. Paid tiers higher CU/sec + archive methods.
- **Infura** free: 100K req/day, 25 req/sec across all chains combined. Paid tiers higher.
- **QuickNode** free trial: 25 req/sec, then per-endpoint paid plans.

**Hard rule for this harness.** Prefer Alchemy as default (most expressive free tier for archive-adjacent methods on Ethereum + L2s). Fall back to Infura on Alchemy 429. QuickNode only when a specific endpoint is provisioned for it. Per-run budget: **5M CU on Alchemy free** as a soft ceiling — if approached, escalate to user before continuing.

**What you get** (JSON-RPC standard methods, plus provider extensions):
- `eth_call` — direct contract reads (`balanceOf` on a treasury wallet, `totalSupply` on a token, custom view functions).
- `eth_getLogs` — event-log queries (token transfers, contract events).
- `eth_getBlockByNumber`, `eth_getTransactionByHash` — block and tx data.
- `eth_getBalance` — native-token balance at any block.
- Provider extensions: Alchemy's `alchemy_getAssetTransfers` (consolidated transfer history), `alchemy_getTokenBalances` (multi-token balance read), trace methods, etc.

**Documented quirks.**
- `eth_getLogs` has **block-range limits** per provider (typically 2,000 blocks on free tiers, more on paid). Splitting a long historical query across calls is mandatory.
- **Archive methods** (state at historical blocks older than ~128 blocks) require paid tier on most providers — Alchemy is the most permissive on free.
- Alchemy charges in **compute units**, not requests. An `eth_call` may be 26 CU; an `eth_getLogs` over a wide range can be 250+ CU. Always estimate before bulk runs.
- Per-chain endpoints are separate — burning Ethereum CU does not affect Base CU on Alchemy.
- Solana RPC methods differ entirely from EVM; treat as a separate adapter.

**Relevant for.** `stablecoin_issuer` (live reserve reads via `eth_call balanceOf` on issuer treasuries, `totalSupply` on the token contract — this is the only way to ground-truth the attestation page), `chain` (block timing, fee distribution), `wallet` (real-time balance on known addresses), `agentic_payment_layer` (settlement-contract reads if the protocol has deployed contracts).

---

## 6. SEC EDGAR

**Domain.** `data.sec.gov` (structured submissions + XBRL company facts), `www.sec.gov/cgi-bin/browse-edgar` (legacy filing index), `www.sec.gov/Archives/edgar/data/<CIK>/...` (raw filing documents). Documentation: `www.sec.gov/edgar/sec-api-documentation`.

**Auth.** No API key. **However**, every request **must** carry a `User-Agent` header containing a contactable email address — this is a documented SEC requirement, not a soft convention. Requests without a compliant User-Agent are throttled aggressively or denied outright. The **canonical format** (inherited from I-003 in `references/equity_incidents_archive.md`) is:

```
User-Agent: <ProjectSlug>/<Version> (<contact-email>)
```

e.g. `StackAnamnesis/1.0 (operator@example.com)`. The equity-era instance used `EquityResearchSkill/1.0 (<email>)`; the Stack Anamnesis fork uses the `StackAnamnesis/<version>` slug once `tools/audit/user_agent_pii.py`'s hardcoded `PUBLIC_USER_AGENT = "EquityResearchSkill/1.0"` is repointed (Phase B housekeeping — surfaced below, not done in B.0).

**Two User-Agent strings live in `meta/run.json`** (per the I-003 contract — never collapse them into one):

- `sec_user_agent` — contains the email; used **only** for hosts matching `sec.gov` or `*.sec.gov` (the live set includes `data.sec.gov`, `www.sec.gov`, `efts.sec.gov`).
- `public_user_agent` — **PII-free** (no email, no other PII); used for **all other** outbound HTTP — DefiLlama, Dune, Etherscan, CoinGecko, RPC, news, logos, peer pages, anything not on a `*.sec.gov` host.

Fetchers pick the right UA **by host**, not by whichever UA happens to be set in run state. A fetcher that defaults to "the only UA it finds" is the exact I-003 bug shape. `tools/audit/user_agent_pii.py` is the post-run guard: it fails when the email substring appears alongside a non-SEC URL, or when `public_user_agent` is missing or contains an email.

**Declined-email semantics.** If the user answers the `P0_sec_email` gate with the canonical token `declined` (also accepted: `skipped`, `none`, `n/a`, `no_email` — per the normaliser in `tools/audit/user_agent_pii.py`), `sec_user_agent` is `null`, SEC fetches are gated off for the run, and `public_user_agent` is still set and used for everything else.

This is the **only data source in the registry** that carries the operator's email in the request header; all five other sources use `public_user_agent`. The SEC-specific User-Agent is constructed at runtime from the `P0_sec_email` answer and **never** persisted to disk, logs, or the DB. See Privacy invariants in `MEMORY.md` and the I-003 cross-cutting guard (restated in §Cross-cutting rules below).

**Conditional gate consumer.** SEC EDGAR is the **only** source in the registry gated by `P0_sec_email`. The gate fires only when `subject_entity.listed == true OR parent_or_issuer_entity.listed == true` (per `references/subject_relationships.yaml`). If neither evaluates true, the gate auto-skips with `applies_when_false` and SEC EDGAR is **not called** for the run. When the user answers the gate with `declined`, SEC EDGAR is also not called, and the report writer notes the affected sections in the template Part 1.5 Data Availability annotation.

**Rate limit.** Documented: **10 requests/second per IP**. See `www.sec.gov/os/accessing-edgar-data`. **Hard rule for this harness**: 5 req/sec working ceiling with 100ms jitter — document fetches (10-K HTML can be several MB) are heavier than the rate-limit counter assumes, and slamming the documented cap has produced temporary blocks in practice. On 429 or 403, exponential backoff starting at 5s, max 4 retries, then surface to user.

**What you get.**
- `/submissions/CIK{padded10}.json` — recent filings + company metadata for a CIK (Central Index Key). Returns paginated `recent` plus a `files` array of older quarters; full history requires concatenating both.
- `/api/xbrl/companyfacts/CIK{padded10}.json` — structured XBRL facts (revenue, assets, share counts, etc.) across all filings for the entity.
- `/api/xbrl/companyconcept/CIK{padded10}/us-gaap/{concept}.json` — single-concept timeseries (e.g., `Revenues`, `OperatingIncomeLoss`).
- `/cgi-bin/browse-edgar?action=getcompany&CIK=...&type=10-K&dateb=&owner=include` — legacy filing index, useful when the `submissions` JSON lacks a specific older filing.
- Raw filings: 10-K (annual), 10-Q (quarterly), 8-K (material events), DEF 14A (proxy), 4 (insider transactions), S-1/S-3 (registration), 13F (institutional holdings). HTML + plaintext versions.

**Documented quirks.**
- **CIK must be zero-padded to 10 digits** in URL paths (e.g., Circle's CIK is `1876042` → URL uses `0001876042`). Unpadded CIKs return 404. Always normalise before constructing URLs.
- **XBRL companyfacts is delayed by 1–2 days** after a filing's `filedAt` date — the structured-data extraction is a separate pipeline. Treat same-day XBRL-misses as expected, not as a fetch failure.
- **The `submissions` endpoint paginates implicitly**: the `recent` block holds the most-recent ~1000 filings; older filings are in the `files` array as references to per-year JSON pages. Fetching only `recent` will silently miss anything older. Always check `files` when the lookback exceeds ~2 years for an active filer.
- **Filing URL subdirectories are unstable** — the per-filing folder under `/Archives/edgar/data/<CIK>/<accession-no-stripped>/` contains documents whose filenames are filer-controlled. Never guess document URLs; resolve them via the filing's `index.json` (e.g., `/Archives/edgar/data/<CIK>/<accession>/index.json`).
- **No CORS** on browser calls. Server-side fetch only; the harness already operates server-side, but this matters for any future thin-client surface.
- **Aggressive CDN caching**: the same URL within a short window can return cached bytes even after a re-filing. Respect 304s; do not assume freshness for filings within the last hour without re-querying the `submissions` index.
- **Form 4 (insider transactions) is high-volume noise** for large public companies — filter by reporting-person role and recent-date window before downstream processing.

**Relevant for.** All five `subject_class` values when the `P0_sec_email` `applies_when` triggers. Conditional in shape, not in coverage:
- `stablecoin_issuer` — primary use case. Circle (CRCL/NYSE) 10-Q for quarterly reserve composition, 10-K risk factors for redemption mechanics, 8-K for material attestation changes. Tether is private and is **not** in scope for SEC EDGAR.
- `wallet` — Coinbase (COIN/NASDAQ) segment revenue, custody risk disclosures in the 10-K, 8-K for outage post-mortems and SEC settlements. Robinhood (HOOD/NASDAQ) for the wallet-app retail side.
- `chain` — usually accessed via the parent company's filings when relevant: Marathon Digital (MARA/NASDAQ) for Bitcoin mining operating data, Galaxy Digital (GLXY/NASDAQ–TSX) for trading-desk volume disclosures. The chain itself is rarely listed; the parent is.
- `orchestrator` — most are private today (Stripe, Bridge, Conduit). The gate auto-skips for private-parent orchestrators. Future listings would activate the path without code change.
- `agentic_payment_layer` — most are private or pre-product. Same auto-skip behaviour as `orchestrator` until a parent goes public.

---

## Cross-cutting rules

- **Keys live on disk, never in code, never in logs.** Each provider's key path is fixed (`~/.config/anamnesis/<provider>.key`). The harness reads the key into memory at the start of the relevant agent's run and passes it via header or query string only.
- **All requests carry `public_user_agent`** (the PII-free string from `meta/run.json`). Never the operator's email. (This is the inherited I-003-style invariant — see `references/equity_incidents_archive.md` for the equity-era leak that established the rule.) **One exception:** SEC EDGAR requests carry the operator-supplied contact email in the `User-Agent` header (SEC's documented requirement; see §6 SEC EDGAR above). The email-bearing User-Agent is constructed at runtime for SEC requests only and never propagates to other sources; `tools/audit/user_agent_pii.py` is the post-run I-003 guard that detects leaks of the SEC email into non-SEC URLs.
- **Cache eagerly, refetch deliberately.** Every fetch lands as a file under `output/{run}/research/_raw/<source>/<request_hash>.json` before any processing. Re-runs and resumes consult the cache first. Cache invalidation is by hash of `(endpoint, params, freshness window)`.
- **Respect rate limits as a hard contract, not a guideline.** The per-source caps above are the harness ceiling; the provider's documented cap is *not* the ceiling. If a fetcher would exceed the harness ceiling, queue and wait, do not burst.
- **On any source returning anomalous data** (sudden null spike, malformed JSON, schema drift), the calling agent records the anomaly in `meta/run.jsonl` and the downstream validator decides whether to halt or warn. Do not paper over with retries.

## Adding a new source

If a real run surfaces a need for a source not in this registry (e.g., Token Terminal for protocol revenue, Artemis for cross-chain analytics, Nansen for wallet labelling), do **not** add the call inline. Instead:

1. Record `event: "out_of_registry"` in `meta/run.jsonl` and halt.
2. Open a PR to this file with a new entry following the same six-field shape: Domain / Auth / Rate limit / What you get / Documented quirks / Relevant for.
3. Update any agent that needs the new source to reference it by registry name.
4. Re-run.

The registry is small on purpose — six sources cover the surface that Stack Anamnesis actually needs for the five subject classes (five always-available + one conditional via `P0_sec_email`). Expansion is a deliberate, reviewed step, not an in-run patch.
