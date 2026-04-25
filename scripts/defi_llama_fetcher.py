#!/usr/bin/env python3
"""Fetch chain or protocol metrics from the DeFi Llama free API.

DefiLlama exposes three endpoint families that must not be confused:

- Chains:    https://api.llama.fi/v2/chains
             https://api.llama.fi/v2/historicalChainTvl/{ChainName}
- Protocols: https://api.llama.fi/protocols
             https://api.llama.fi/protocol/{slug}
             https://api.llama.fi/tvl/{slug}
- Fees:      https://api.llama.fi/overview/fees/{ChainName}?excludeTotalDataChartBreakdown=true
             https://api.llama.fi/summary/fees/{slug}?excludeTotalDataChartBreakdown=true

This script auto-detects whether the input is a chain or a protocol, fetches
only the correct endpoints for each, and writes a normalized JSON file.

Missing or genuinely unavailable fields are serialized as JSON null. The
report generator renders null values as "—".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://api.llama.fi"
TIMEOUT_SECONDS = 30
SLOW_TIMEOUT_SECONDS = 60
SECONDS_PER_DAY = 86_400
NON_CHAIN_TOKENS = {"staking", "pool2", "borrowed", "doublecounted"}


# ----------------------------------------------------------------------------
# HTTP plumbing


class FetchLog:
    """Records every endpoint touch so the user can see what worked."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record(self, url: str, status: str, detail: str = "") -> None:
        self.entries.append({"url": url, "status": status, "detail": detail})
        print(f"[FETCH] {status:<7} {url}{(' — ' + detail) if detail else ''}")

    def note(self, message: str) -> None:
        self.entries.append({"note": message})
        print(f"[NOTE] {message}")


def http_get_json(url: str, log: FetchLog, timeout: int = TIMEOUT_SECONDS) -> Any | None:
    """GET a URL and return parsed JSON, or None for any failure."""
    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        log.record(url, "ERR", f"transport error: {exc}")
        return None

    if response.status_code == 404:
        log.record(url, "404")
        return None
    if response.status_code >= 500:
        log.record(url, f"{response.status_code}", "server error")
        return None
    if not response.ok:
        log.record(url, f"{response.status_code}", "http error")
        return None

    try:
        payload = response.json()
    except ValueError as exc:
        log.record(url, "ERR", f"invalid JSON: {exc}")
        return None

    detail = ""
    if isinstance(payload, list):
        detail = f"{len(payload)} items"
    elif isinstance(payload, dict):
        detail = f"{len(payload)} keys"
    log.record(url, "OK", detail)
    return payload


# ----------------------------------------------------------------------------
# Slug helpers


def normalize_input(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.strip().lower()).strip("-")


def match_token(value: str) -> str:
    """Collapse a string for case/punctuation-insensitive matching."""
    return re.sub(r"[\s_\-]+", "", value).casefold()


def candidate_protocol_slugs(slug: str) -> list[str]:
    """Build a list of slug variants to try against DefiLlama."""
    candidates = [slug]
    if "-" in slug:
        head = slug.split("-", 1)[0]
        if head and head not in candidates:
            candidates.append(head)
    if not slug.endswith("-one"):
        candidates.append(f"{slug}-one")
    return list(dict.fromkeys(candidates))


# ----------------------------------------------------------------------------
# Detection


def detect_kind(
    slug: str,
    chains: list[dict[str, Any]] | None,
    log: FetchLog,
) -> tuple[str, dict[str, Any] | None]:
    """Decide whether ``slug`` refers to a chain or a protocol."""
    if isinstance(chains, list):
        target = match_token(slug)
        for entry in chains:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name", "")
            if isinstance(name, str) and match_token(name) == target:
                log.note(f'detected as chain: "{name}" (matched input "{slug}")')
                return "chain", entry
    log.note(f'no chain match for "{slug}" — treating as protocol')
    return "protocol", None


# ----------------------------------------------------------------------------
# TVL helpers


def normalize_history(points: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(points, list):
        return out
    for point in points:
        if not isinstance(point, dict):
            continue
        date = point.get("date")
        tvl = point.get("tvl", point.get("totalLiquidityUSD"))
        if date is None or not isinstance(tvl, (int, float)):
            continue
        out.append({"date": int(date), "tvl": float(tvl)})
    return out


def slice_last_30d(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return history[-30:]


def pct_change(history: list[dict[str, Any]], days: int) -> float | None:
    if len(history) < 2:
        return None
    end = history[-1]
    target_ts = end["date"] - days * SECONDS_PER_DAY
    start = history[0]
    for point in history:
        if point["date"] <= target_ts:
            start = point
        else:
            break
    if start["tvl"] == 0:
        return None
    return round(((end["tvl"] - start["tvl"]) / start["tvl"]) * 100, 2)


# ----------------------------------------------------------------------------
# Fees helpers


def fetch_fees(
    candidates: list[str],
    *,
    is_chain: bool,
    log: FetchLog,
) -> dict[str, Any] | None:
    """Try each slug variant against the chain or protocol fees endpoint."""
    path = "overview/fees" if is_chain else "summary/fees"
    for slug in candidates:
        url = f"{BASE_URL}/{path}/{slug}?excludeTotalDataChartBreakdown=true"
        payload = http_get_json(url, log, timeout=SLOW_TIMEOUT_SECONDS)
        if isinstance(payload, dict):
            return payload
    return None


def numeric(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


# ----------------------------------------------------------------------------
# Comparables


def compare_chains(chains: list[dict[str, Any]] | None, exclude: str) -> list[dict[str, Any]]:
    if not isinstance(chains, list):
        return []
    target = match_token(exclude)
    rows: list[dict[str, Any]] = []
    for entry in chains:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        tvl = numeric(entry.get("tvl"))
        if not isinstance(name, str) or tvl is None:
            continue
        if match_token(name) == target:
            continue
        rows.append({"name": name, "tvl": tvl, "category": None})
    rows.sort(key=lambda item: item["tvl"], reverse=True)
    return rows[:5]


def chains_from_tvl_breakdown(breakdown: Any) -> list[str]:
    """Derive a clean chain list from DefiLlama's currentChainTvls keys."""
    if not isinstance(breakdown, dict):
        return []
    seen: list[str] = []
    for key in breakdown.keys():
        if not isinstance(key, str):
            continue
        head = key.split("-", 1)[0]
        if not head or head.lower() in NON_CHAIN_TOKENS:
            continue
        if head not in seen:
            seen.append(head)
    return seen


def category_from_children(
    protocols: list[dict[str, Any]] | None,
    parent_id: str | None,
) -> str | None:
    """Pick the most common category among child protocols of a parent slug."""
    if not isinstance(protocols, list) or not parent_id:
        return None
    counts: dict[str, int] = {}
    for entry in protocols:
        if not isinstance(entry, dict):
            continue
        if entry.get("parentProtocol") != parent_id:
            continue
        category = entry.get("category")
        if isinstance(category, str) and category:
            counts[category] = counts.get(category, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: item[1])[0]


def compare_protocols(
    protocols: list[dict[str, Any]] | None,
    *,
    category: str | None,
    exclude_slug: str,
) -> list[dict[str, Any]]:
    if not isinstance(protocols, list) or not category:
        return []
    rows: list[dict[str, Any]] = []
    for entry in protocols:
        if not isinstance(entry, dict):
            continue
        if entry.get("category") != category:
            continue
        if entry.get("slug") == exclude_slug:
            continue
        name = entry.get("name")
        tvl = numeric(entry.get("tvl"))
        if not isinstance(name, str) or tvl is None:
            continue
        rows.append({"name": name, "tvl": tvl, "category": category})
    rows.sort(key=lambda item: item["tvl"], reverse=True)
    return rows[:5]


# ----------------------------------------------------------------------------
# Builders


def build_chain_record(
    slug: str,
    chain_entry: dict[str, Any],
    chains: list[dict[str, Any]],
    log: FetchLog,
) -> dict[str, Any]:
    chain_name = chain_entry.get("name") or slug

    history_payload = http_get_json(
        f"{BASE_URL}/v2/historicalChainTvl/{chain_name}",
        log,
        timeout=SLOW_TIMEOUT_SECONDS,
    )
    history = normalize_history(history_payload)

    fees = fetch_fees(
        list(dict.fromkeys([chain_name, slug, f"{slug}-one"])),
        is_chain=True,
        log=log,
    )

    current_tvl = numeric(chain_entry.get("tvl"))
    if current_tvl is None and history:
        current_tvl = history[-1]["tvl"]

    return {
        "protocol": slug,
        "display_name": chain_name,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "type": "chain",
        "tvl_usd": current_tvl,
        "tvl_7d_change_pct": pct_change(history, 7),
        "tvl_30d_change_pct": pct_change(history, 30),
        "tvl_history_30d": slice_last_30d(history),
        "category": None,
        "chains": [chain_name],
        "fees_24h_usd": numeric((fees or {}).get("total24h")),
        "fees_7d_usd": numeric((fees or {}).get("total7d")),
        "revenue_24h_usd": numeric(
            (fees or {}).get("totalRevenue24h")
            or (fees or {}).get("dailyRevenue")
        ),
        "description": None,
        "token_symbol": chain_entry.get("tokenSymbol") or None,
        "comparable_protocols": compare_chains(chains, exclude=chain_name),
    }


def build_protocol_record(
    slug: str,
    protocols: list[dict[str, Any]] | None,
    log: FetchLog,
) -> dict[str, Any] | None:
    detail_payload: dict[str, Any] | None = None
    matched_slug = slug
    for candidate in candidate_protocol_slugs(slug):
        payload = http_get_json(f"{BASE_URL}/protocol/{candidate}", log)
        if isinstance(payload, dict):
            detail_payload = payload
            matched_slug = candidate
            break

    if detail_payload is None:
        return None

    catalog_entry: dict[str, Any] = {}
    if isinstance(protocols, list):
        for entry in protocols:
            if isinstance(entry, dict) and entry.get("slug") == matched_slug:
                catalog_entry = entry
                break

    current_tvl_payload = http_get_json(f"{BASE_URL}/tvl/{matched_slug}", log)
    current_tvl: float | None = None
    if isinstance(current_tvl_payload, (int, float)):
        current_tvl = float(current_tvl_payload)
    elif isinstance(catalog_entry.get("tvl"), (int, float)):
        current_tvl = float(catalog_entry["tvl"])

    history = normalize_history(detail_payload.get("tvl"))

    fees = fetch_fees(
        candidate_protocol_slugs(matched_slug),
        is_chain=False,
        log=log,
    )

    chains = detail_payload.get("chains") or catalog_entry.get("chains") or []
    if not isinstance(chains, list) or not chains:
        chains = chains_from_tvl_breakdown(detail_payload.get("currentChainTvls"))

    category = (
        detail_payload.get("category")
        or catalog_entry.get("category")
        or category_from_children(protocols, detail_payload.get("id"))
    )

    return {
        "protocol": matched_slug,
        "display_name": detail_payload.get("name") or catalog_entry.get("name") or matched_slug,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "type": "protocol",
        "tvl_usd": current_tvl,
        "tvl_7d_change_pct": pct_change(history, 7),
        "tvl_30d_change_pct": pct_change(history, 30),
        "tvl_history_30d": slice_last_30d(history),
        "category": category,
        "chains": list(chains),
        "fees_24h_usd": numeric((fees or {}).get("total24h")),
        "fees_7d_usd": numeric((fees or {}).get("total7d")),
        "revenue_24h_usd": numeric(
            (fees or {}).get("totalRevenue24h")
            or (fees or {}).get("dailyRevenue")
        ),
        "description": detail_payload.get("description")
        or catalog_entry.get("description")
        or None,
        "token_symbol": detail_payload.get("symbol") or catalog_entry.get("symbol") or None,
        "comparable_protocols": compare_protocols(
            protocols, category=category, exclude_slug=matched_slug
        ),
    }


# ----------------------------------------------------------------------------
# Output


def save_record(slug: str, record: dict[str, Any]) -> Path:
    output_dir = Path("workspace") / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slug}_data.json"
    output_path.write_text(
        json.dumps(record, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return output_path


def print_summary(record: dict[str, Any], output_path: Path) -> None:
    print()
    print(f"{record['type'].upper()}: {record['display_name']} (slug: {record['protocol']})")
    print(f"Fetched at: {record['fetched_at']}")
    tvl = record.get("tvl_usd")
    print(f"Current TVL: ${tvl:,.0f}" if isinstance(tvl, (int, float)) else "Current TVL: —")
    print(f"7d TVL change:  {record.get('tvl_7d_change_pct')}%" if record.get("tvl_7d_change_pct") is not None else "7d TVL change: —")
    print(f"30d TVL change: {record.get('tvl_30d_change_pct')}%" if record.get("tvl_30d_change_pct") is not None else "30d TVL change: —")
    print(f"Category: {record.get('category') or '—'}")
    chains = record.get("chains") or []
    print(f"Chains: {', '.join(chains) if chains else '—'}")
    fees = record.get("fees_24h_usd")
    print(f"Fees 24h: ${fees:,.0f}" if isinstance(fees, (int, float)) else "Fees 24h: —")
    revenue = record.get("revenue_24h_usd")
    print(f"Revenue 24h: ${revenue:,.0f}" if isinstance(revenue, (int, float)) else "Revenue 24h: —")
    print(f"Comparables: {len(record.get('comparable_protocols') or [])}")
    print(f"Saved JSON: {output_path}")


# ----------------------------------------------------------------------------
# Entry point


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch DeFi Llama chain or protocol data.")
    parser.add_argument(
        "protocol",
        help='Chain or protocol slug, e.g. "arbitrum", "base", "aave", "uniswap".',
    )
    return parser.parse_args()


def fetch(slug: str) -> tuple[dict[str, Any], Path]:
    log = FetchLog()

    chains = http_get_json(f"{BASE_URL}/v2/chains", log)
    chains = chains if isinstance(chains, list) else []

    protocols = http_get_json(f"{BASE_URL}/protocols", log)
    protocols = protocols if isinstance(protocols, list) else []

    kind, chain_entry = detect_kind(slug, chains, log)

    if kind == "chain" and isinstance(chain_entry, dict):
        record: dict[str, Any] | None = build_chain_record(slug, chain_entry, chains, log)
    else:
        record = build_protocol_record(slug, protocols, log)
        if record is None and chains:
            log.note(f'protocol fetch failed for "{slug}" — retrying as chain')
            for entry in chains:
                if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                    if match_token(entry["name"]) == match_token(slug):
                        record = build_chain_record(slug, entry, chains, log)
                        break

    if record is None:
        record = {
            "error": "Protocol or chain not found",
            "slug_tried": slug,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    output_path = save_record(slug, record)
    record["_fetch_log"] = log.entries
    return record, output_path


def main() -> int:
    args = parse_args()
    slug = normalize_input(args.protocol)
    if not slug:
        print("Error: protocol or chain name is required", file=sys.stderr)
        return 2

    record, output_path = fetch(slug)
    if "error" in record:
        print(f"\nError: {record['error']} — slug tried: {record.get('slug_tried')}", file=sys.stderr)
        print(f"Saved JSON: {output_path}", file=sys.stderr)
        return 1

    print_summary(record, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
