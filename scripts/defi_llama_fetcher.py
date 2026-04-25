#!/usr/bin/env python3
"""Fetch protocol metrics from the DeFi Llama API."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


BASE_URL = "https://api.llama.fi"
DATA_UNAVAILABLE = "[DATA_UNAVAILABLE]"
TIMEOUT_SECONDS = 20


class ApiUnavailableError(RuntimeError):
    """Raised when DeFi Llama cannot be reached or returns a server error."""


class ProtocolNotFoundError(RuntimeError):
    """Raised when DeFi Llama does not recognize the supplied protocol slug."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str) -> Any:
    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ApiUnavailableError(str(exc)) from exc

    if response.status_code == 404:
        raise ProtocolNotFoundError(url)

    if response.status_code >= 500:
        raise ApiUnavailableError(f"{url} returned HTTP {response.status_code}")

    try:
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as exc:
        raise ApiUnavailableError(f"{url} returned HTTP {response.status_code}") from exc
    except ValueError as exc:
        raise ApiUnavailableError(f"{url} returned invalid JSON") from exc


def fetch_optional_json(url: str) -> Any | None:
    try:
        return fetch_json(url)
    except ProtocolNotFoundError:
        return None


def normalize_tvl_point(point: dict[str, Any]) -> dict[str, Any]:
    value = point.get("totalLiquidityUSD", point.get("tvl", point.get("value")))
    return {
        "date": point.get("date"),
        "tvl_usd": value,
    }


def get_historical_tvl_30d(protocol_data: dict[str, Any]) -> list[dict[str, Any]]:
    tvl_points = protocol_data.get("tvl")
    if not isinstance(tvl_points, list):
        return []

    normalized = [
        normalize_tvl_point(point)
        for point in tvl_points
        if isinstance(point, dict) and point.get("date") is not None
    ]
    return normalized[-30:]


def calculate_30d_change_pct(historical_tvl: list[dict[str, Any]]) -> float | str:
    if len(historical_tvl) < 2:
        return DATA_UNAVAILABLE

    start_tvl = historical_tvl[0].get("tvl_usd")
    end_tvl = historical_tvl[-1].get("tvl_usd")

    if not isinstance(start_tvl, (int, float)) or not isinstance(end_tvl, (int, float)):
        return DATA_UNAVAILABLE
    if start_tvl == 0:
        return DATA_UNAVAILABLE

    return round(((end_tvl - start_tvl) / start_tvl) * 100, 2)


def extract_fee_metrics(fees_data: dict[str, Any] | None) -> tuple[Any, Any]:
    if not isinstance(fees_data, dict):
        return DATA_UNAVAILABLE, DATA_UNAVAILABLE

    fees_24h = fees_data.get("total24h", DATA_UNAVAILABLE)
    revenue_24h = fees_data.get("totalRevenue24h", fees_data.get("revenue24h", DATA_UNAVAILABLE))
    return fees_24h, revenue_24h


def get_protocol_catalog_entry(protocols: list[Any], protocol_slug: str) -> dict[str, Any]:
    for protocol in protocols:
        if isinstance(protocol, dict) and protocol.get("slug") == protocol_slug:
            return protocol
    return {}


def get_related_catalog_entries(
    protocols: list[Any],
    protocol_data: dict[str, Any],
    protocol_slug: str,
) -> list[dict[str, Any]]:
    aliases = {protocol_slug.casefold()}
    name = protocol_data.get("name")
    if isinstance(name, str):
        aliases.add(name.casefold())

    other_protocols = protocol_data.get("otherProtocols")
    if isinstance(other_protocols, list):
        aliases.update(item.casefold() for item in other_protocols if isinstance(item, str))

    related = []
    for protocol in protocols:
        if not isinstance(protocol, dict):
            continue
        candidate_slug = protocol.get("slug")
        candidate_name = protocol.get("name")
        if isinstance(candidate_slug, str) and candidate_slug.casefold() in aliases:
            related.append(protocol)
        elif isinstance(candidate_name, str) and candidate_name.casefold() in aliases:
            related.append(protocol)

    return related


def first_available_category(*entries: dict[str, Any]) -> str | None:
    for entry in entries:
        category = entry.get("category")
        if isinstance(category, str) and category:
            return category
    return None


def merge_chains(*entries: dict[str, Any]) -> list[str]:
    chains = []
    seen = set()
    for entry in entries:
        entry_chains = entry.get("chains")
        if not isinstance(entry_chains, list):
            continue
        for chain in entry_chains:
            if isinstance(chain, str) and chain not in seen:
                chains.append(chain)
                seen.add(chain)
    return chains


def get_comparable_protocols(
    protocols: list[Any],
    category: str | None,
    protocol_slug: str,
) -> list[dict[str, Any]]:
    if not category:
        return []

    comparable = []
    for protocol in protocols:
        if not isinstance(protocol, dict):
            continue
        if protocol.get("category") != category:
            continue
        if protocol.get("slug") == protocol_slug:
            continue

        comparable.append(
            {
                "name": protocol.get("name", DATA_UNAVAILABLE),
                "slug": protocol.get("slug", DATA_UNAVAILABLE),
                "tvl_usd": protocol.get("tvl", DATA_UNAVAILABLE),
                "chains": protocol.get("chains", []),
            }
        )

    comparable.sort(
        key=lambda item: item["tvl_usd"] if isinstance(item.get("tvl_usd"), (int, float)) else -1,
        reverse=True,
    )
    return comparable[:10]


def build_protocol_result(protocol_slug: str) -> dict[str, Any]:
    fetched_at = utc_now_iso()

    current_tvl = fetch_json(f"{BASE_URL}/tvl/{protocol_slug}")
    protocol_data = fetch_json(f"{BASE_URL}/protocol/{protocol_slug}")
    if not isinstance(protocol_data, dict):
        raise ProtocolNotFoundError(protocol_slug)

    protocols = fetch_json(f"{BASE_URL}/protocols")
    if not isinstance(protocols, list):
        protocols = []

    catalog_entry = get_protocol_catalog_entry(protocols, protocol_slug)
    related_entries = get_related_catalog_entries(protocols, protocol_data, protocol_slug)
    fees_data = fetch_optional_json(f"{BASE_URL}/summary/fees/{protocol_slug}")
    historical_tvl_30d = get_historical_tvl_30d(protocol_data)
    category = first_available_category(protocol_data, catalog_entry, *related_entries)
    chains = merge_chains(protocol_data, catalog_entry, *related_entries)

    fees_24h, revenue_24h = extract_fee_metrics(fees_data)

    return {
        "protocol": protocol_data.get("name", protocol_slug),
        "slug": protocol_slug,
        "fetched_at": fetched_at,
        "tvl_usd": current_tvl if isinstance(current_tvl, (int, float)) else DATA_UNAVAILABLE,
        "tvl_30d_change_pct": calculate_30d_change_pct(historical_tvl_30d),
        "category": category or DATA_UNAVAILABLE,
        "chains": chains,
        "fees_24h_usd": fees_24h,
        "revenue_24h_usd": revenue_24h,
        "description": protocol_data.get("description", DATA_UNAVAILABLE),
        "historical_tvl_30d": historical_tvl_30d,
        "comparable_protocols": get_comparable_protocols(protocols, category, protocol_slug),
    }


def save_result(protocol_slug: str, result: dict[str, Any]) -> Path:
    output_dir = Path("workspace") / protocol_slug
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "data.json"
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def print_summary(result: dict[str, Any], output_path: Path) -> None:
    if "error" in result:
        print(f"Error: {result['error']}")
        if "slug_tried" in result:
            print(f"Slug tried: {result['slug_tried']}")
        if "timestamp" in result:
            print(f"Timestamp: {result['timestamp']}")
        print(f"Saved JSON: {output_path}")
        return

    print(f"Protocol: {result['protocol']} ({result['slug']})")
    print(f"Fetched at: {result['fetched_at']}")
    print(f"Current TVL: ${result['tvl_usd']:,.2f}" if isinstance(result["tvl_usd"], (int, float)) else "Current TVL: [DATA_UNAVAILABLE]")
    print(f"30d TVL change: {result['tvl_30d_change_pct']}%")
    print(f"Category: {result['category']}")
    print(f"Chains: {', '.join(result['chains']) if result['chains'] else DATA_UNAVAILABLE}")
    print(f"Fees 24h: ${result['fees_24h_usd']:,.2f}" if isinstance(result["fees_24h_usd"], (int, float)) else "Fees 24h: [DATA_UNAVAILABLE]")
    print(f"Revenue 24h: ${result['revenue_24h_usd']:,.2f}" if isinstance(result["revenue_24h_usd"], (int, float)) else "Revenue 24h: [DATA_UNAVAILABLE]")
    print(f"Comparable protocols: {len(result['comparable_protocols'])}")
    print(f"Saved JSON: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch DeFi Llama protocol data.")
    parser.add_argument("protocol", help='Protocol slug, e.g. "arbitrum", "aave", or "uniswap".')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    protocol_slug = args.protocol.strip().lower()

    if not protocol_slug:
        print("Error: protocol slug is required", file=sys.stderr)
        return 2

    try:
        result = build_protocol_result(protocol_slug)
    except ProtocolNotFoundError:
        result = {"error": "Protocol not found", "slug_tried": protocol_slug}
    except ApiUnavailableError:
        result = {"error": "API unavailable", "timestamp": utc_now_iso()}
    except Exception as exc:
        result = {"error": "Unexpected error", "message": str(exc), "timestamp": utc_now_iso()}

    output_path = save_result(protocol_slug, result)
    print_summary(result, output_path)
    return 1 if "error" in result else 0


if __name__ == "__main__":
    raise SystemExit(main())
