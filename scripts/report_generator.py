#!/usr/bin/env python3
"""Generate a YYFoundry HTML report for a DeFi protocol."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv


DATA_UNAVAILABLE = "[DATA_UNAVAILABLE]"
ROOT_DIR = Path(__file__).resolve().parents[1]
FETCHER_PATH = ROOT_DIR / "scripts" / "defi_llama_fetcher.py"
AGENT_PROMPT_PATH = ROOT_DIR / "agents" / "upstream_downstream.md"
TEMPLATE_PATH = ROOT_DIR / "templates" / "report_template.html"


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
    data_path = ROOT_DIR / "workspace" / protocol_slug / "data.json"
    if not data_path.exists():
        raise FileNotFoundError(f"Fetcher did not create {data_path}")
    return data_path


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def format_value(value: Any, money: bool = False, pct: bool = False) -> str:
    if value in (None, "", DATA_UNAVAILABLE):
        return unavailable()
    if isinstance(value, (int, float)):
        if money:
            return f"${value:,.0f}"
        if pct:
            return f"{value:+.2f}%"
        return f"{value:,.2f}"
    return escape(str(value))


def unavailable() -> str:
    return '<span class="data-unavailable">[DATA_UNAVAILABLE]</span>'


def format_chains(chains: Any) -> str:
    if not isinstance(chains, list) or not chains:
        return unavailable()
    return escape(", ".join(str(chain) for chain in chains))


def comparable_table(comparables: Any) -> str:
    if not isinstance(comparables, list) or not comparables:
        return unavailable()

    rows = []
    for item in comparables[:10]:
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('name', DATA_UNAVAILABLE)))}</td>"
            f"<td>{escape(str(item.get('slug', DATA_UNAVAILABLE)))}</td>"
            f"<td>{format_value(item.get('tvl_usd'), money=True)}</td>"
            f"<td>{format_chains(item.get('chains'))}</td>"
            "</tr>"
        )

    if not rows:
        return unavailable()

    return (
        "<table>"
        "<thead><tr><th>Protocol</th><th>Slug</th><th>TVL</th><th>Chains</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def infer_layer(data: dict[str, Any]) -> tuple[str, str]:
    category = str(data.get("category", "")).lower()
    description = str(data.get("description", "")).lower()
    text = f"{category} {description}"

    if any(term in text for term in ("bridge", "rollup", "l2", "scaling")):
        return "2", "Protocol/Execution layer: execution, settlement routing, bridges, or scaling infrastructure."
    if any(term in text for term in ("oracle", "index", "rpc", "storage")):
        return "3", "Middleware/Infrastructure layer: data, access, and coordination services for applications."
    if any(term in text for term in ("lending", "dex", "staking", "yield")):
        return "4", "Application layer: user-facing smart contract markets and protocol logic."
    return "4", "Application/protocol layer with upstream infrastructure dependencies and downstream application effects."


def extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Claude response did not contain a JSON object")
    return json.loads(text[start : end + 1])


def missing_api_key_analysis(protocol_slug: str, data: dict[str, Any]) -> dict[str, Any]:
    """Placeholder analysis when ANTHROPIC_API_KEY is not set. No invented metrics."""
    name = str(data.get("protocol", protocol_slug))
    desc = str(data.get("description", ""))[:300]
    return {
        "tldr": (
            f"{name}: supply chain analysis is disabled until you set ANTHROPIC_API_KEY in the project .env. "
            f"Data below is from DeFi Llama only. {desc or ''}"
        )[:500],
        "stack_description": "Set ANTHROPIC_API_KEY to generate protocol-specific stack text from the upstream_downstream agent.",
        "hidden_dependency_insight": "[DATA_UNAVAILABLE] — set ANTHROPIC_API_KEY to run the supply-chain sub-agent; do not guess suppliers or operator locations.",
        "key_insight_paragraph": "[DATA_UNAVAILABLE] — full YYFoundry angle requires the Claude pass; narrative-only insights would risk sounding authoritative without the structured dependency pass.",
        "upstream_dependencies": [],
        "downstream_dependents": [],
        "risk_score": DATA_UNAVAILABLE,
        "primary_risk": "[DATA_UNAVAILABLE] — risk scoring is produced by the agent pass.",
        "risk_reasoning": "Add ANTHROPIC_API_KEY to .env to compute supply chain risk with reasoning tied to the fetched metrics.",
        "video_hook": f"Set your API key — then we can narrate {name} from Layer 0 to Layer 6.",
        "substack_angle": f"DeFi Llama data for {name} is in workspace/{protocol_slug}/data.json; the missing piece is the Atoms to Bits write-up (API key).",
        "x_thread_opener": f"{name} on paper vs {name} in the supply stack — thread starts after the agent runs (ANTHROPIC_API_KEY).",
    }


def call_claude(protocol_slug: str, data: dict[str, Any]) -> dict[str, Any]:
    load_dotenv(ROOT_DIR / ".env")
    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        return missing_api_key_analysis(protocol_slug, data)
    client = Anthropic()
    system_prompt = AGENT_PROMPT_PATH.read_text(encoding="utf-8")

    user_message = {
        "protocol": protocol_slug,
        "fetched_data": data,
        "required_output": {
            "tldr": "Two precise sentences.",
            "upstream_dependencies": "List of supply chain dependency objects.",
            "downstream_dependents": "List of downstream dependent objects.",
            "hidden_dependency_insight": "One paragraph.",
            "key_insight_paragraph": "One paragraph.",
            "risk_score": "Integer 1-10.",
            "primary_risk": "One sentence.",
            "risk_reasoning": "One paragraph.",
            "video_hook": "One punchy sentence.",
            "substack_angle": "One sentence.",
            "x_thread_opener": "One sentence.",
        },
    }

    response = client.messages.create(
        model="claude-3-5-sonnet-latest",
        max_tokens=3500,
        temperature=0.2,
        system=(
            f"{system_prompt}\n\n"
            "Return only valid JSON. Do not wrap it in Markdown. Do not fabricate unavailable metrics."
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


def html_list(items: Any, item_type: str) -> str:
    if not isinstance(items, list) or not items:
        return unavailable()

    rendered = []
    for item in items:
        if not isinstance(item, dict):
            rendered.append(f"<li>{escape(str(item))}</li>")
            continue

        if item_type == "upstream":
            title = f"{item.get('layer', DATA_UNAVAILABLE)}: {item.get('dependency', DATA_UNAVAILABLE)}"
            body = (
                f"Supplier/control point: {item.get('supplier', DATA_UNAVAILABLE)}. "
                f"Concentration risk: {item.get('concentration_risk', DATA_UNAVAILABLE)}. "
                f"Analogy: {item.get('analogy', DATA_UNAVAILABLE)}"
            )
        else:
            title = str(item.get("protocol", DATA_UNAVAILABLE))
            body = (
                f"Dependency type: {item.get('dependency_type', DATA_UNAVAILABLE)}. "
                f"Impact if broken: {item.get('impact_if_broken', DATA_UNAVAILABLE)}"
            )

        rendered.append(f"<li><strong>{escape(title)}</strong><br>{escape(body)}</li>")

    return f"<ul>{''.join(rendered)}</ul>"


def replace_placeholders(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def build_values(protocol_slug: str, data: dict[str, Any], analysis: dict[str, Any]) -> dict[str, str]:
    layer_number, stack_description = infer_layer(data)
    risk_score = analysis.get("risk_score")
    if risk_score is None and isinstance(analysis.get("supply_chain_risk_score"), dict):
        risk_score = analysis["supply_chain_risk_score"].get("score")

    risk_bar_pct = "0"
    if isinstance(risk_score, (int, float)):
        risk_bar_pct = str(int(max(0, min(10, int(risk_score))) * 10))
    elif isinstance(risk_score, str) and risk_score != DATA_UNAVAILABLE and risk_score.isdigit():
        risk_bar_pct = str(int(max(0, min(10, int(risk_score))) * 10))

    return {
        "PROTOCOL_NAME": escape(str(data.get("protocol") or protocol_slug)),
        "DATE": datetime.now(timezone.utc).date().isoformat(),
        "TLDR": escape(str(analysis.get("tldr", DATA_UNAVAILABLE))),
        "TVL_USD": format_value(data.get("tvl_usd"), money=True),
        "TVL_30D_CHANGE": format_value(data.get("tvl_30d_change_pct"), pct=True),
        "CATEGORY": format_value(data.get("category")),
        "CHAINS": format_chains(data.get("chains")),
        "FEES_24H": format_value(data.get("fees_24h_usd"), money=True),
        "LAYER_NUMBER": escape(str(layer_number)),
        "STACK_DESCRIPTION": escape(str(analysis.get("stack_description", stack_description))),
        "UPSTREAM_ANALYSIS": html_list(analysis.get("upstream_dependencies"), "upstream"),
        "HIDDEN_DEPENDENCY_INSIGHT": escape(str(analysis.get("hidden_dependency_insight", DATA_UNAVAILABLE))),
        "DOWNSTREAM_ANALYSIS": html_list(analysis.get("downstream_dependents"), "downstream"),
        "RISK_SCORE": escape(str(risk_score if risk_score is not None else DATA_UNAVAILABLE)),
        "RISK_BAR_PCT": risk_bar_pct,
        "PRIMARY_RISK": escape(str(analysis.get("primary_risk", DATA_UNAVAILABLE))),
        "RISK_REASONING": escape(str(analysis.get("risk_reasoning", DATA_UNAVAILABLE))),
        "COMPARABLE_TABLE": comparable_table(data.get("comparable_protocols")),
        "KEY_INSIGHT_PARAGRAPH": escape(str(analysis.get("key_insight_paragraph", analysis.get("key_insight", DATA_UNAVAILABLE)))),
        "VIDEO_HOOK": escape(str(analysis.get("video_hook", DATA_UNAVAILABLE))),
        "SUBSTACK_ANGLE": escape(str(analysis.get("substack_angle", DATA_UNAVAILABLE))),
        "X_THREAD_OPENER": escape(str(analysis.get("x_thread_opener", DATA_UNAVAILABLE))),
    }


def inject_unavailable_style(html: str) -> str:
    css = "      .data-unavailable { color: var(--muted); font-style: italic; }\n"
    return html.replace("      .muted {\n", f"{css}\n      .muted {{\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a YYFoundry HTML report.")
    parser.add_argument("protocol", help='Protocol slug, e.g. "arbitrum", "aave", or "uniswap".')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    protocol_slug = slugify(args.protocol)
    if not protocol_slug:
        print("Error: protocol name is required", file=sys.stderr)
        return 2

    load_dotenv(ROOT_DIR / ".env")
    data_path = run_fetcher(protocol_slug)
    data = load_json(data_path)
    if "error" in data:
        print(f"Error: fetcher returned {data['error']}", file=sys.stderr)
        return 1

    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        print(
            "Warning: ANTHROPIC_API_KEY not set. Using placeholder analysis. "
            "Copy .env.example to .env and set your key for full agent output.",
            file=sys.stderr,
        )

    template = inject_unavailable_style(TEMPLATE_PATH.read_text(encoding="utf-8"))
    analysis = call_claude(protocol_slug, data)
    rendered = replace_placeholders(template, build_values(protocol_slug, data, analysis))

    output_path = ROOT_DIR / "workspace" / protocol_slug / f"{protocol_slug}_report.html"
    output_path.write_text(rendered, encoding="utf-8")
    relative_output = output_path.relative_to(ROOT_DIR)
    print(f"Report saved to {relative_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
