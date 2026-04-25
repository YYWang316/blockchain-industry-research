#!/usr/bin/env python3
"""Generate a YYFoundry HTML report.

Pipeline:
  1. Run scripts/defi_llama_fetcher.py to populate workspace/{slug}/{slug}_data.json
  2. Call Claude with agents/upstream_downstream.md as system prompt to produce
     the supply-chain analysis plus the YYFoundry-specific narrative pieces.
  3. Combine fetched data + analysis into the REPORT_DATA contract and write it
     to workspace/{slug}/report_data.js.
  4. Copy templates/report_template.html to workspace/{slug}/{slug}_report.html
     and inject <script src="report_data.js"></script> just before </body>.
  5. Print: Report ready -> workspace/{slug}/{slug}_report.html
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
FETCHER_PATH = ROOT_DIR / "scripts" / "defi_llama_fetcher.py"
AGENT_PROMPT_PATH = ROOT_DIR / "agents" / "upstream_downstream.md"
TEMPLATE_PATH = ROOT_DIR / "templates" / "report_template.html"

SCRIPT_TAG = '<script src="report_data.js"></script>'

LAYER_NAMES = {
    0: "Physical Infrastructure",
    1: "Network / Consensus",
    2: "Protocol / Execution",
    3: "Middleware / Infrastructure",
    4: "Application Layer",
    5: "DeFi / Financial",
    6: "Access / Compliance",
}

LAYER_DESCRIPTIONS = {
    0: "Physical infrastructure layer: semiconductors, energy, data centres, and network hardware that everything else runs on.",
    1: "Network and consensus layer: validator nodes, staking infrastructure, and client software securing the chain.",
    2: "Protocol and execution layer: virtual machines, rollup sequencers, and bridges executing user transactions.",
    3: "Middleware and infrastructure layer: oracles, indexers, RPC providers, and storage networks supporting applications.",
    4: "Application layer: user-facing smart-contract markets — DEXes, lending, staking, and yield primitives.",
    5: "DeFi and financial layer: structured products, derivatives, and yield strategies that compose application primitives.",
    6: "Access and compliance layer: wallets, on-ramps, KYC infrastructure, and institutional custody.",
}


# ----------------------------------------------------------------------------
# CLI helpers


def slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    return slug.strip("-")


def run_fetcher(protocol_slug: str) -> Path:
    subprocess.run(
        [sys.executable, str(FETCHER_PATH), protocol_slug],
        cwd=ROOT_DIR,
        check=True,
    )
    data_path = ROOT_DIR / "workspace" / protocol_slug / f"{protocol_slug}_data.json"
    if not data_path.exists():
        raise FileNotFoundError(f"Fetcher did not create {data_path}")
    return data_path


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------
# Formatting helpers


def format_money_compact(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    abs_value = abs(float(value))
    sign = "-" if value < 0 else ""
    if abs_value >= 1e12:
        return f"{sign}${abs_value / 1e12:.2f}T"
    if abs_value >= 1e9:
        return f"{sign}${abs_value / 1e9:.2f}B"
    if abs_value >= 1e6:
        return f"{sign}${abs_value / 1e6:.2f}M"
    if abs_value >= 1e3:
        return f"{sign}${abs_value / 1e3:.1f}K"
    return f"{sign}${abs_value:,.0f}"


def format_pct(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    return f"{value:+.2f}%"


def trend_from(value: Any) -> str | None:
    if not isinstance(value, (int, float)):
        return None
    if value > 0.01:
        return "up"
    if value < -0.01:
        return "down"
    return "flat"


def truncate_sentence(value: Any, max_chars: int = 240) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if sentences:
        first = sentences[0]
        if len(first) <= max_chars and first:
            return first
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"


# ----------------------------------------------------------------------------
# Layer inference


def infer_layer(data: dict[str, Any]) -> int:
    text = f"{data.get('category', '') or ''} {data.get('description', '') or ''}".lower()
    kind = (data.get("type") or "").lower()
    if kind == "chain":
        if any(term in text for term in ("rollup", "l2", "scaling", "optimistic", "validity")):
            return 2
        return 1
    if any(term in text for term in ("bridge", "rollup", "l2", "scaling")):
        return 2
    if any(term in text for term in ("oracle", "rpc", "indexer", "storage")):
        return 3
    if any(term in text for term in ("lending", "dex", "stablecoin", "perp", "options", "yield", "stake")):
        return 4
    return 4


# ----------------------------------------------------------------------------
# Claude call


def missing_api_key_analysis() -> dict[str, Any]:
    """Empty analysis when ANTHROPIC_API_KEY is not set; renders as null in the UI."""
    return {
        "tldr": None,
        "stack_description": None,
        "upstream": [],
        "downstream": [],
        "hidden_dependency": None,
        "key_insight": None,
        "findings": [],
        "risk": {"score": None, "primary_risk": None, "reasoning": None},
        "content_hooks": {"video": None, "substack": None, "x_thread": None},
        "tokenomics_notes": None,
    }


def call_claude(protocol_slug: str, data: dict[str, Any]) -> dict[str, Any]:
    load_dotenv(ROOT_DIR / ".env")
    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        return missing_api_key_analysis()

    client = Anthropic()
    system_prompt = AGENT_PROMPT_PATH.read_text(encoding="utf-8")

    user_message = {
        "protocol": protocol_slug,
        "fetched_data": data,
        "required_output_schema": {
            "tldr": "Two precise sentences. Must include an industrial supply chain analogy.",
            "stack_description": "One paragraph describing position in the 7-layer Atoms to Bits stack.",
            "upstream": [
                {
                    "layer_num": "Integer 0-6 indicating the dependency's layer.",
                    "name": "Concrete supplier or component (e.g. 'AWS us-east-1 / Sequencer Hosting').",
                    "concentration_risk": "Exactly HIGH, MED, or LOW.",
                    "analogy": "One sentence industrial / manufacturing analogy.",
                    "notes": "Optional one-line operational note. Use empty string if none.",
                }
            ],
            "downstream": [
                {
                    "name": "Protocol or application built on top.",
                    "dependency_type": "Short phrase, e.g. 'State availability + ordering'.",
                    "impact": "One sentence describing what breaks if the subject protocol fails.",
                    "lock_in": "Exactly HIGH, MED, or LOW.",
                }
            ],
            "hidden_dependency": "Two to three sentences naming the most non-obvious upstream constraint.",
            "key_insight": "One paragraph with the YYFoundry supply-chain angle that general crypto research misses.",
            "findings": [
                {
                    "heading": "Sentence-form finding statement.",
                    "body": "Two to three sentences supporting the finding.",
                }
            ],
            "risk": {
                "score": "Integer 1-10.",
                "primary_risk": "One sentence.",
                "reasoning": "One paragraph.",
            },
            "content_hooks": {
                "video": "One punchy sentence for video opening.",
                "substack": "One sentence for Substack pitch.",
                "x_thread": "One sentence as X thread opener.",
            },
            "tokenomics_notes": "Two to three sentences on token utility, supply mechanics, and emissions risks.",
        },
        "instructions": [
            "Return ONLY a single JSON object matching the schema above.",
            "Do not wrap output in Markdown. Do not include comments.",
            "Provide exactly 4 entries in 'findings'.",
            "Provide between 3 and 6 entries in 'upstream' and in 'downstream'.",
            "If a metric is genuinely unknown, use null — never invent numbers.",
        ],
    }

    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=4000,
        temperature=0.2,
        system=(
            f"{system_prompt}\n\n"
            "Return only valid JSON matching the user-supplied schema. "
            "Never fabricate metrics; use null for unknowns. "
            "The supply-chain angle is mandatory in every field."
        ),
        messages=[
            {
                "role": "user",
                "content": json.dumps(user_message, indent=2, sort_keys=True),
            }
        ],
    )

    text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
    return extract_json_object(text)


def extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Claude response did not contain a JSON object")
    return json.loads(text[start : end + 1])


# ----------------------------------------------------------------------------
# REPORT_DATA assembly


def build_meta(data: dict[str, Any], protocol_slug: str) -> dict[str, Any]:
    chains = data.get("chains") if isinstance(data.get("chains"), list) else []
    description = truncate_sentence(data.get("description"))
    return {
        "protocol_name": data.get("display_name") or data.get("protocol") or protocol_slug,
        "token_symbol": data.get("token_symbol"),
        "date": datetime.now(timezone.utc).date().isoformat(),
        "category": data.get("category"),
        "chains": [str(c) for c in chains if str(c).strip()],
        "description": description,
    }


def build_kpis(data: dict[str, Any], layer_num: int) -> list[dict[str, Any]]:
    tvl_value = format_money_compact(data.get("tvl_usd"))
    tvl_delta = format_pct(data.get("tvl_30d_change_pct"))
    fees_value = format_money_compact(data.get("fees_24h_usd"))
    revenue_value = format_money_compact(data.get("revenue_24h_usd"))

    return [
        {
            "label": "TVL",
            "value": tvl_value,
            "delta": tvl_delta,
            "trend": trend_from(data.get("tvl_30d_change_pct")),
        },
        {
            "label": "Daily Fees",
            "value": fees_value,
            "delta": None,
            "trend": None,
        },
        {
            "label": "Daily Revenue",
            "value": revenue_value,
            "delta": None,
            "trend": None,
        },
        {
            "label": "Layer",
            "value": f"L{layer_num}",
            "delta": None,
            "trend": None,
        },
    ]


def build_metrics(data: dict[str, Any]) -> list[dict[str, Any]]:
    chains = data.get("chains") if isinstance(data.get("chains"), list) else []
    chains_text = ", ".join(str(c) for c in chains if str(c).strip()) or None
    return [
        {"label": "TVL", "value": format_money_compact(data.get("tvl_usd"))},
        {"label": "7d Change", "value": format_pct(data.get("tvl_7d_change_pct"))},
        {"label": "30d Change", "value": format_pct(data.get("tvl_30d_change_pct"))},
        {"label": "Daily Fees", "value": format_money_compact(data.get("fees_24h_usd"))},
        {"label": "Daily Revenue", "value": format_money_compact(data.get("revenue_24h_usd"))},
        {"label": "Chains", "value": chains_text},
    ]


def build_layer(layer_num: int, analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "number": layer_num,
        "name": LAYER_NAMES.get(layer_num, "Application Layer"),
        "stack_description": (
            analysis.get("stack_description")
            or LAYER_DESCRIPTIONS.get(layer_num)
        ),
    }


def build_tvl_history(history: Any) -> list[dict[str, Any]]:
    if not isinstance(history, list):
        return []
    out: list[dict[str, Any]] = []
    for point in history:
        if not isinstance(point, dict):
            continue
        date = point.get("date")
        tvl = point.get("tvl")
        if date is None or not isinstance(tvl, (int, float)):
            continue
        out.append({"date": int(date) if isinstance(date, (int, float)) else date, "tvl": float(tvl)})
    return out


def normalize_level(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    upper = value.strip().upper()
    if upper.startswith("HIGH"):
        return "HIGH"
    if upper.startswith("MED"):
        return "MED"
    if upper.startswith("LOW"):
        return "LOW"
    return None


def build_upstream(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        layer_num = item.get("layer_num")
        if layer_num is None:
            layer_text = str(item.get("layer", ""))
            match = re.search(r"layer\s*([0-9])", layer_text, re.IGNORECASE)
            if match:
                layer_num = int(match.group(1))
        out.append(
            {
                "layer_num": int(layer_num) if isinstance(layer_num, (int, float)) else None,
                "name": item.get("name") or item.get("dependency"),
                "concentration_risk": normalize_level(item.get("concentration_risk")),
                "analogy": item.get("analogy"),
                "notes": item.get("notes") or item.get("supplier"),
            }
        )
    return out


def build_downstream(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "name": item.get("name") or item.get("protocol"),
                "dependency_type": item.get("dependency_type"),
                "impact": item.get("impact") or item.get("impact_if_broken"),
                "lock_in": normalize_level(item.get("lock_in")),
            }
        )
    return out


def build_findings(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items[:4]:
        if not isinstance(item, dict):
            continue
        out.append({"heading": item.get("heading"), "body": item.get("body")})
    return out


def build_comparables(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    self_tvl = data.get("tvl_usd") if isinstance(data.get("tvl_usd"), (int, float)) else None
    rows.append(
        {
            "name": data.get("display_name") or data.get("protocol"),
            "tvl": float(self_tvl) if isinstance(self_tvl, (int, float)) else None,
            "fees_24h": float(data["fees_24h_usd"]) if isinstance(data.get("fees_24h_usd"), (int, float)) else None,
            "category": data.get("category"),
        }
    )
    for entry in data.get("comparable_protocols") or []:
        if not isinstance(entry, dict):
            continue
        tvl = entry.get("tvl") if isinstance(entry.get("tvl"), (int, float)) else None
        rows.append(
            {
                "name": entry.get("name"),
                "tvl": float(tvl) if isinstance(tvl, (int, float)) else None,
                "fees_24h": (
                    float(entry["fees_24h"])
                    if isinstance(entry.get("fees_24h"), (int, float))
                    else None
                ),
                "category": entry.get("category"),
            }
        )
    rows.sort(
        key=lambda row: row["tvl"] if isinstance(row["tvl"], (int, float)) else -1,
        reverse=True,
    )
    return rows


def build_risk(analysis: dict[str, Any]) -> dict[str, Any]:
    raw_risk = analysis.get("risk")
    if not isinstance(raw_risk, dict):
        raw_risk = {}
    score = raw_risk.get("score")
    if isinstance(score, str):
        score = int(score) if score.isdigit() else None
    if not isinstance(score, (int, float)):
        score = None
    return {
        "score": int(score) if isinstance(score, (int, float)) else None,
        "primary_risk": raw_risk.get("primary_risk") or analysis.get("primary_risk"),
        "reasoning": raw_risk.get("reasoning") or analysis.get("risk_reasoning"),
    }


def build_content_hooks(analysis: dict[str, Any]) -> dict[str, Any]:
    raw = analysis.get("content_hooks") if isinstance(analysis.get("content_hooks"), dict) else {}
    return {
        "video": raw.get("video") or analysis.get("video_hook"),
        "substack": raw.get("substack") or analysis.get("substack_angle"),
        "x_thread": raw.get("x_thread") or analysis.get("x_thread_opener"),
    }


def build_report_data(
    protocol_slug: str,
    data: dict[str, Any],
    analysis: dict[str, Any],
) -> dict[str, Any]:
    layer_num = infer_layer(data)
    return {
        "meta": build_meta(data, protocol_slug),
        "kpis": build_kpis(data, layer_num),
        "metrics": build_metrics(data),
        "tldr": analysis.get("tldr"),
        "layer": build_layer(layer_num, analysis),
        "tvl_history": build_tvl_history(data.get("tvl_history_30d")),
        "upstream": build_upstream(analysis.get("upstream") or analysis.get("upstream_dependencies")),
        "downstream": build_downstream(analysis.get("downstream") or analysis.get("downstream_dependents")),
        "hidden_dependency": analysis.get("hidden_dependency") or analysis.get("hidden_dependency_insight"),
        "risk": build_risk(analysis),
        "comparables": build_comparables(data),
        "findings": build_findings(analysis.get("findings")),
        "key_insight": analysis.get("key_insight") or analysis.get("key_insight_paragraph"),
        "content_hooks": build_content_hooks(analysis),
        "tokenomics_notes": analysis.get("tokenomics_notes"),
    }


# ----------------------------------------------------------------------------
# Output


def write_report_data_js(output_dir: Path, payload: dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "report_data.js"
    body = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    contents = (
        "// Generated by scripts/report_generator.py — do not edit by hand.\n"
        f"window.REPORT_DATA = {body};\n"
    )
    output_path.write_text(contents, encoding="utf-8")
    return output_path


def copy_template_with_script(output_dir: Path, html_filename: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / html_filename
    template_html = TEMPLATE_PATH.read_text(encoding="utf-8")
    if SCRIPT_TAG in template_html:
        rendered = template_html
    elif "</body>" in template_html:
        rendered = template_html.replace("</body>", f"    {SCRIPT_TAG}\n  </body>", 1)
    else:
        rendered = template_html + f"\n{SCRIPT_TAG}\n"
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


# ----------------------------------------------------------------------------
# CLI


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a YYFoundry HTML research report.")
    parser.add_argument("protocol", help='Protocol or chain slug, e.g. "arbitrum", "aave".')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    protocol_slug = slugify(args.protocol)
    if not protocol_slug:
        print("Error: protocol or chain name is required", file=sys.stderr)
        return 2

    load_dotenv(ROOT_DIR / ".env")

    data_path = run_fetcher(protocol_slug)
    data = load_json(data_path)
    if "error" in data:
        print(f"Error: fetcher returned {data['error']}", file=sys.stderr)
        return 1

    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        print(
            "Warning: ANTHROPIC_API_KEY not set. Narrative fields will render as 'Data unavailable'.\n"
            "Copy .env.example to .env and set your key for full agent output.",
            file=sys.stderr,
        )

    analysis = call_claude(protocol_slug, data)
    payload = build_report_data(protocol_slug, data, analysis)

    output_dir = ROOT_DIR / "workspace" / protocol_slug
    write_report_data_js(output_dir, payload)
    html_path = copy_template_with_script(output_dir, f"{protocol_slug}_report.html")

    relative = html_path.relative_to(ROOT_DIR)
    print(f"Report ready -> {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# Re-export for compatibility / backwards imports.
__all__ = [
    "build_report_data",
    "call_claude",
    "main",
    "run_fetcher",
    "write_report_data_js",
]
