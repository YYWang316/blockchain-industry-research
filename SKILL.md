---
name: atoms-to-bits-protocol-research
description: Research crypto and blockchain protocols through the Atoms to Bits industrial supply chain framework. Use when analyzing protocols, sectors, DeFi systems, L1s, L2s, restaking, infrastructure, or blockchain applications from physical infrastructure through access layers.
---

# Atoms to Bits Protocol Research

## Core Identity

Analyze blockchain protocols through an industrial supply chain lens. Trace the system from physical infrastructure up through software, market structure, applications, DeFi, and access layers.

The core framework is **Atoms to Bits**: a 7-layer stack that connects Layer 0 physical inputs such as hardware, energy, and semiconductors to higher-level blockchain protocols, consensus systems, applications, DeFi markets, and Layer 6 access interfaces.

## Hard Rules: P0 Gates

- Never fabricate on-chain numbers, TVL, fees, usage metrics, protocol revenue, user counts, or market figures.
- If required data is unavailable or the data fetch fails, mark the field as `[DATA_UNAVAILABLE]`.
- Every upstream dependency claim must include a reasoning chain that explains why the dependency matters.
- Every report must include the supply chain angle. This is the core differentiator of the research.
- Keep the report language in English.

## Phase 0: Input Parsing

- Accept a topic input such as `Ethereum L2`, `EigenLayer`, `Solana`, `DePIN`, or a specific protocol name.
- Normalize the topic into:
  - Protocol or sector name.
  - Ecosystem category.
  - Primary use case.
  - Relevant chain or chains, if applicable.
- Identify which layers of the 7-layer Atoms to Bits stack are relevant:
  - Layer 0: Physical infrastructure, energy, hardware, semiconductors, data centers.
  - Layer 1: Base blockchain networks and validator or miner infrastructure.
  - Layer 2: Scaling systems, execution layers, rollups, appchains, shared security layers.
  - Layer 3: Middleware, oracle networks, indexing, bridges, interoperability, data availability.
  - Layer 4: Protocols and applications, including DeFi, restaking, payments, gaming, identity, and DePIN.
  - Layer 5: Aggregation, routing, liquidity, market structure, wallets-as-platforms, developer platforms.
  - Layer 6: User access, exchanges, wallets, custody, APIs, front ends, fiat ramps, and distribution channels.
- Set the report language to English.
- Define the research scope before collecting data:
  - What is the object of analysis?
  - Which layers are in scope?
  - Which layers are out of scope or only lightly touched?

## Phase 1: Data Collection

- Trigger `scripts/defi_llama_fetcher.py` to collect real metrics where applicable.
- Read generated data from `workspace/{protocol_name}/data.json`.
- Collect only verifiable data, including:
  - TVL.
  - Fees.
  - Revenue, if available.
  - Volume, if available.
  - Chain-level or protocol-level activity metrics, if available.
  - Comparable protocol metrics for market context, if available.
- If `scripts/defi_llama_fetcher.py` fails, returns partial data, or does not support the topic:
  - Mark missing fields as `[DATA_UNAVAILABLE]`.
  - Do not estimate, infer, interpolate, or fabricate numbers.
  - State the data limitation clearly in the report.
- Preserve source labels and timestamps when available.

## Phase 2: Supply Chain Mapping

- Trigger the `agents/upstream_downstream.md` sub-agent.
- Map upstream dependencies by asking what physical, infrastructure, and protocol layers the topic depends on.
- For each upstream dependency, include:
  - The dependency.
  - The relevant Atoms to Bits layer.
  - The reasoning chain explaining why the dependency exists.
  - The risk or bottleneck created by that dependency.
- Map downstream applications by asking what is built on top of the protocol or sector.
- For each downstream application, include:
  - The application or market.
  - The relevant Atoms to Bits layer.
  - Why this protocol enables or improves that downstream use case.
  - Any adoption, distribution, liquidity, or integration constraints.
- Explicitly connect physical infrastructure to software outcomes where relevant.

## Phase 3: Narrative And Competitive Context

- Summarize the current market narrative around the protocol or sector in plain English.
- Identify the main thesis investors, builders, or users have for why this topic matters.
- Identify the main counter-thesis, bottleneck, or risk.
- Select 2-3 comparable protocols, sectors, or ecosystems for contrast.
- Compare the topic against those peers using:
  - Supply chain position.
  - Technical architecture.
  - Demand drivers.
  - Economic model.
  - Dependency risks.
  - Downstream adoption.
- Avoid unsupported market claims. If a claim requires data that is unavailable, mark the relevant field as `[DATA_UNAVAILABLE]`.

## Phase 4: Report Generation

- Fill in `templates/report_template.html` with all gathered data and analysis.
- Save final protocol outputs under `workspace/{protocol_name}/`.
- Ensure the final report includes:
  - Topic and scope.
  - Relevant Atoms to Bits layers.
  - Verified protocol metrics or `[DATA_UNAVAILABLE]`.
  - Upstream dependency map with reasoning chains.
  - Downstream application map.
  - Narrative and competitive context.
  - Key risks and bottlenecks.
  - Supply chain-specific conclusion.
- Output the final report as HTML.
- Before finalizing, verify:
  - No fabricated numbers appear in the report.
  - Every upstream dependency has a reasoning chain.
  - The supply chain angle appears throughout the report, not only in the conclusion.
  - All unavailable data is marked as `[DATA_UNAVAILABLE]`.
