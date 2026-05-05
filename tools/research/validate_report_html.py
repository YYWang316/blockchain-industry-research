"""Validate that P5 produced a locked-template ER HTML report, not a simplified page.

This is a deterministic P5/P6 gate. It does not judge prose quality; it catches
the high-cost failure mode where the host model writes a short custom HTML page
instead of extracting the locked report skeleton and replacing placeholders.

Usage:
    python tools/research/validate_report_html.py --run-dir <path> --lang cn
    python tools/research/validate_report_html.py --html <report.html> --skeleton <_locked_cn_skeleton.html>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


REQUIRED_SECTION_IDS = (
    "section-summary",
    "section-financials",
    "section-prediction",
    "section-sankey",
    "section-porter",
    "section-appendix",
)

REQUIRED_MARKERS = (
    "CANONICAL CSS",
    "LOCKED JAVASCRIPT",
    "DATA VARIABLES",
    "drawWaterfall",
    "drawSankey",
    "drawRadar",
    "sankeyActualData",
    "sankeyForecastData",
    "porterScores",
    "waterfallData",
)

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")

PORTER_PANELS = ("company", "industry", "forward")
PORTER_FORCES = (
    ("供应商议价能力", "supplier power"),
    ("买方议价能力", "buyer power"),
    ("新进入者威胁", "threat of new entrants"),
    ("替代品威胁", "threat of substitutes"),
    ("行业竞争强度", "competitive rivalry"),
)

# I-005: metrics table — nine controlled ratio categories.
METRIC_ROW_ALIASES: dict[str, tuple[str, ...]] = {
    "gross_margin": ("毛利率", "Gross Margin", "Gross margin"),
    "operating_margin": ("营业利润率", "Operating Margin", "Operating margin"),
    "net_margin": ("净利率", "Net Margin", "Net margin"),
    "roe": ("ROE",),
    "roa": ("ROA",),
    "debt_to_asset": (
        "资产负债率",
        "Debt-to-asset ratio",
        "Debt-to-Asset Ratio",
        "Asset-liability ratio",
        "Asset-Liability Ratio",
    ),
    "interest_coverage": (
        "利息保障倍数",
        "Interest Coverage",
        "Interest coverage",
        "Interest Coverage Ratio",
    ),
    "eps": (
        "每股收益（EPS）",
        "每股收益(EPS)",
        "稀释EPS",
        "EPS",
        "Diluted EPS",
        "Earnings per share",
        "Earnings per Share",
    ),
    "fcf_margin": (
        "自由现金流利润率",
        "FCF Margin",
        "FCF margin",
        "Free Cash Flow Margin",
        "Free cash flow margin",
    ),
}

_METRIC_NAME_TO_KEY: dict[str, str] = {
    name: key for key, names in METRIC_ROW_ALIASES.items() for name in names
}

METRIC_VERDICT_VOCAB: frozenset[str] = frozenset({
    "显著改善", "改善", "基本持平", "恶化", "显著恶化",
    "权益缺口收窄", "权益缺口扩大", "期末股东权益为负", "不适用",
    "Significantly improved", "Improved", "Stable", "Deteriorated",
    "Significantly deteriorated", "Equity deficit narrowed",
    "Equity deficit widened", "Ending equity negative", "N/A",
})


def _find_single_report(research_dir: Path) -> Path | None:
    candidates = sorted(
        p for p in research_dir.glob("*_Research_*.html")
        if not p.name.startswith("_locked_")
    )
    if len(candidates) != 1:
        return None
    return candidates[0]


def _find_skeleton(research_dir: Path, lang: str) -> Path | None:
    candidates = [
        research_dir / f"_locked_{lang}_skeleton.html",
        research_dir / "_locked_skeleton.html",
        research_dir / "_locked_cn_skeleton.html" if lang == "zh" else research_dir / "_locked_en_skeleton.html",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _count(soup: BeautifulSoup, selector: str) -> int:
    return len(soup.select(selector))


def _porter_li_start_ok(text: str, zh_force: str, en_force: str) -> bool:
    text = " ".join(text.split())
    zh_patterns = (
        rf"^经QC合议，维持{re.escape(zh_force)}为[1-5]分。",
        rf"^经QC合议，决定将{re.escape(zh_force)}评分维持[1-5]分不变。",
        rf"^经QC合议，决定将{re.escape(zh_force)}评分从[1-5]分调整为[1-5]分。",
        rf"^基于初稿评分，{re.escape(zh_force)}为[1-5]分。",
    )
    if any(re.search(pattern, text) for pattern in zh_patterns):
        return True

    lower = text.lower()
    force = re.escape(en_force.lower())
    en_patterns = (
        rf"^dual-qc deliberation maintained (the )?{force} at [1-5]/5\.",
        rf"^after dual-qc deliberation, (the )?{force} remains [1-5]/5\.",
        rf"^dual-qc deliberation adjusted (the )?{force} score from [1-5] to [1-5]/5\.",
        rf"^per draft scoring, (the )?{force} stands at [1-5]/5\.",
    )
    return any(re.search(pattern, lower) for pattern in en_patterns)


def _validate_porter_texts(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for panel in PORTER_PANELS:
        panel_selector = f"#porter-panel-{panel}"
        panel_node = soup.select_one(panel_selector)
        if panel_node is None:
            errors.append(f"missing Porter panel for text validation: {panel_selector}")
            continue

        text_node = panel_node.select_one(".porter-text")
        if text_node is None:
            errors.append(f"{panel_selector} missing .porter-text container")
            continue

        uls = text_node.find_all("ul")
        if len(uls) != 1:
            errors.append(f"{panel_selector} .porter-text must contain exactly one <ul>; got {len(uls)}")
            continue

        lis = uls[0].find_all("li", recursive=False)
        if len(lis) != 5:
            errors.append(f"{panel_selector} .porter-text <ul> must contain exactly five direct <li>; got {len(lis)}")
            continue

        for idx, (li, (zh_force, en_force)) in enumerate(zip(lis, PORTER_FORCES), start=1):
            li_text = li.get_text(" ", strip=True)
            if not li_text:
                errors.append(f"{panel_selector} .porter-text li[{idx}] is empty")
                continue
            if not _porter_li_start_ok(li_text, zh_force, en_force):
                errors.append(
                    f"{panel_selector} .porter-text li[{idx}] must start with the whitelisted "
                    f"QC/no-QC sentence for {zh_force}/{en_force}"
                )
            if len(li_text) < 24:
                warnings.append(f"{panel_selector} .porter-text li[{idx}] is very short")

    return errors, warnings


def _validate_metrics_table(soup: BeautifulSoup) -> tuple[list[str], list[str]]:
    """I-005: Section II metrics table content and verdict cell vocabulary."""
    errors: list[str] = []
    warnings: list[str] = []

    table = soup.select_one("table.metrics-table")
    if table is None:
        errors.append("missing <table class='metrics-table'> (I-005)")
        return errors, warnings

    tbody = table.find("tbody")
    rows = tbody.find_all("tr", recursive=False) if tbody else []
    if not rows:
        errors.append("metrics-table tbody contains no <tr> (I-005)")
        return errors, warnings

    if len(rows) != 9:
        errors.append(
            f"metrics-table must contain exactly 9 <tr>; got {len(rows)} (I-005)"
        )

    seen_keys: set[str] = set()
    for idx, tr in enumerate(rows, start=1):
        tds = tr.find_all("td", recursive=False)
        if len(tds) != 4:
            errors.append(
                f"metrics-table row[{idx}] must have exactly 4 <td>; got {len(tds)} (I-005)"
            )
            continue

        name = tds[0].get_text(" ", strip=True)
        key = _METRIC_NAME_TO_KEY.get(name)
        if key is None:
            errors.append(
                f"metrics-table row[{idx}] first <td> '{name}' is not in the controlled ratio whitelist; "
                "expected one of 毛利率/营业利润率/净利率/ROE/ROA/资产负债率/利息保障倍数/每股收益（EPS）/自由现金流利润率 "
                "or English equivalents (I-005)"
            )
        elif key in seen_keys:
            errors.append(
                f"metrics-table row[{idx}] '{name}' duplicates ratio category '{key}' (I-005)"
            )
        else:
            seen_keys.add(key)

        verdict = tds[3].get_text(" ", strip=True)
        if verdict not in METRIC_VERDICT_VOCAB:
            errors.append(
                f"metrics-table row[{idx}] 4th <td> '{verdict}' is not in the controlled verdict vocabulary "
                "(I-005). Expected: 显著改善/改善/基本持平/恶化/显著恶化/权益缺口收窄/权益缺口扩大/期末股东权益为负/不适用 "
                "or English equivalents."
            )

    if len(rows) == 9 and len(seen_keys) < 9:
        missing = sorted(set(METRIC_ROW_ALIASES.keys()) - seen_keys)
        errors.append(
            f"metrics-table missing required ratio categories: {missing} (I-005)"
        )

    return errors, warnings


def validate_html_report(html_path: Path, skeleton_path: Path | None = None) -> dict[str, Any]:
    html_path = html_path.resolve()
    errors: list[str] = []
    warnings: list[str] = []

    if not html_path.exists():
        return {"status": "critical", "errors": [f"html file not found: {html_path}"], "warnings": []}

    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    skeleton_bytes = None
    if skeleton_path:
        skeleton_path = skeleton_path.resolve()
        if not skeleton_path.exists():
            errors.append(f"locked skeleton not found: {skeleton_path}")
        else:
            skeleton_bytes = len(skeleton_path.read_bytes())
            # The locked CN skeleton is ~38KB. A complete filled report may change
            # byte count, but a bespoke simplified page is usually far smaller.
            min_bytes = int(skeleton_bytes * 0.70)
            actual_bytes = len(html.encode("utf-8"))
            if actual_bytes < min_bytes:
                errors.append(
                    f"html is too small for locked template lineage: {actual_bytes} bytes < {min_bytes} bytes"
                )

    placeholders = sorted(set(PLACEHOLDER_RE.findall(html)))
    if placeholders:
        errors.append(f"unreplaced locked-template placeholders remain: {', '.join(placeholders[:12])}")

    for marker in REQUIRED_MARKERS:
        if marker not in html:
            errors.append(f"missing locked-template marker: {marker}")

    for section_id in REQUIRED_SECTION_IDS:
        if not soup.select_one(f"#{section_id}"):
            errors.append(f"missing required report section: #{section_id}")

    structural_counts = {
        "summary_para": _count(soup, "#section-summary .summary-para"),
        "kpi_card": _count(soup, "#section-financials .kpi-card"),
        "trend_card": _count(soup, "#section-financials .trend-card"),
        "porter_panel": _count(soup, '[id^="porter-panel-"]'),
        "porter_text": _count(soup, "#section-porter .porter-text"),
        "porter_text_ul": _count(soup, "#section-porter .porter-text ul"),
        "porter_text_li": _count(soup, "#section-porter .porter-text ul > li"),
        "sankey_svg": _count(soup, "#chart-sankey-actual") + _count(soup, "#chart-sankey-forecast"),
        "radar_canvas": _count(soup, 'canvas[id^="chart-radar-"]'),
    }
    expected = {
        "summary_para": 4,
        "kpi_card": 4,
        "trend_card": 5,
        "porter_panel": 3,
        "porter_text": 3,
        "porter_text_ul": 3,
        "porter_text_li": 15,
        "sankey_svg": 2,
        "radar_canvas": 3,
    }
    for key, need in expected.items():
        got = structural_counts[key]
        if got < need:
            errors.append(f"locked report structure incomplete: {key} count {got} < {need}")

    porter_errors, porter_warnings = _validate_porter_texts(soup)
    errors.extend(porter_errors)
    warnings.extend(porter_warnings)

    metrics_errors, metrics_warnings = _validate_metrics_table(soup)
    errors.extend(metrics_errors)
    warnings.extend(metrics_warnings)

    script_text = "\n".join(node.get_text("\n") for node in soup.find_all("script"))
    for var_name in ("waterfallData", "sankeyActualData", "sankeyForecastData", "porterScores"):
        if not re.search(rf"\bconst\s+{re.escape(var_name)}\s*=", script_text):
            errors.append(f"missing JS data variable: {var_name}")

    line_count = len(html.splitlines())
    if line_count < 500:
        errors.append(f"html line count is too low for locked report template: {line_count} < 500")

    return {
        "status": "critical" if errors else ("warn" if warnings else "pass"),
        "html_file": str(html_path),
        "skeleton_file": str(skeleton_path) if skeleton_path else None,
        "line_count": line_count,
        "byte_count": len(html.encode("utf-8")),
        "skeleton_byte_count": skeleton_bytes,
        "structural_counts": structural_counts,
        "errors": errors,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument("--run-dir", default=None)
    p.add_argument("--lang", default="cn", choices=["cn", "en", "zh"])
    p.add_argument("--html", default=None)
    p.add_argument("--skeleton", default=None)
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    if args.run_dir:
        research_dir = Path(args.run_dir).resolve() / "research"
        html_path = _find_single_report(research_dir)
        if html_path is None:
            result = {
                "status": "critical",
                "errors": [f"expected exactly one non-locked *_Research_*.html under {research_dir}"],
                "warnings": [],
            }
        else:
            skeleton = Path(args.skeleton).resolve() if args.skeleton else _find_skeleton(research_dir, args.lang)
            result = validate_html_report(html_path, skeleton)
    else:
        if not args.html:
            print("error: provide --run-dir or --html", file=sys.stderr)
            return 2
        result = validate_html_report(
            Path(args.html),
            Path(args.skeleton).resolve() if args.skeleton else None,
        )

    out_path = Path(args.out).resolve() if args.out else None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "critical" else 1


if __name__ == "__main__":
    raise SystemExit(main())
