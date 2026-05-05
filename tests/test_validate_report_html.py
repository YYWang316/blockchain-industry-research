from __future__ import annotations

from pathlib import Path

from tools.research.validate_report_html import validate_html_report


def _porter_text(valid: bool = True) -> str:
    if not valid:
        return '<div class="porter-text">品牌心智强、SKU聚焦；但成本波动仍影响扩张节奏。</div>'

    forces = (
        "供应商议价能力",
        "买方议价能力",
        "新进入者威胁",
        "替代品威胁",
        "行业竞争强度",
    )
    lis = "\n".join(
        f"<li>基于初稿评分，{force}为3分。这里保留每个维度的公司事实、行业证据和评分解释。</li>"
        for force in forces
    )
    return f'<div class="porter-text"><ul style="margin:0;padding-left:1.25em;">{lis}</ul></div>'


def _metrics_table(valid: bool = True) -> str:
    if not valid:
        # Buggy table: 7 absolute-amount rows, no controlled ratio names.
        rows = "\n".join(
            f'<tr><td>{name}</td><td>1</td><td>2</td><td class="metric-down">显著恶化</td></tr>'
            for name in (
                "营业收入（百万人民币）",
                "毛利润（百万人民币）",
                "营业利润（百万人民币）",
                "净利润（百万人民币）",
                "稀释EPS（人民币）",
                "经营现金流（百万人民币）",
                "自由现金流（百万人民币）",
            )
        )
        return f'<table class="metrics-table"><tbody>{rows}</tbody></table>'

    canonical = (
        ("毛利率", "改善"),
        ("营业利润率", "基本持平"),
        ("净利率", "改善"),
        ("ROE", "显著改善"),
        ("ROA", "改善"),
        ("资产负债率", "恶化"),
        ("利息保障倍数", "显著改善"),
        ("每股收益（EPS）", "改善"),
        ("自由现金流利润率", "基本持平"),
    )
    rows = "\n".join(
        f'<tr><td>{name}</td><td>1.0</td><td>1.0</td><td class="metric-up">{verdict}</td></tr>'
        for name, verdict in canonical
    )
    return f'<table class="metrics-table"><tbody>{rows}</tbody></table>'


def _locked_like_html(porter_valid: bool = True, metrics_valid: bool = True) -> str:
    sections = "\n".join(
        f'<div class="section" id="{sid}"></div>'
        for sid in (
            "section-summary",
            "section-financials",
            "section-prediction",
            "section-sankey",
            "section-porter",
            "section-appendix",
        )
    )
    summary = "\n".join('<p class="summary-para">x</p>' for _ in range(4))
    kpis = "\n".join('<div class="kpi-card"></div>' for _ in range(4))
    trends = "\n".join('<div class="trend-card"></div>' for _ in range(5))
    metrics = _metrics_table(valid=metrics_valid)
    porters = "\n".join(
        f'<div id="porter-panel-{i}">{_porter_text(valid=porter_valid)}</div>'
        for i in ("company", "industry", "forward")
    )
    radar = "\n".join(f'<canvas id="chart-radar-{i}"></canvas>' for i in ("company", "industry", "forward"))
    filler = "\n".join("<!-- locked filler -->" for _ in range(520))
    return f"""<!doctype html>
<html>
<head><style>CANONICAL CSS</style></head>
<body>
{sections}
<div id="section-summary">{summary}</div>
<div id="section-financials">{kpis}{trends}{metrics}</div>
<div id="section-sankey"><svg id="chart-sankey-actual"></svg><svg id="chart-sankey-forecast"></svg></div>
<div id="section-porter">{porters}{radar}</div>
<script>
LOCKED JAVASCRIPT
DATA VARIABLES
const waterfallData = [];
const sankeyActualData = {{}};
const sankeyForecastData = {{}};
const porterScores = {{}};
function drawWaterfall() {{}}
function drawSankey() {{}}
function drawRadar() {{}}
</script>
{filler}
</body>
</html>"""


def test_validate_report_html_rejects_simplified_page(tmp_path: Path) -> None:
    html = tmp_path / "Simple_Research_CN.html"
    html.write_text("<html><body><h1>简化版</h1></body></html>", encoding="utf-8")

    result = validate_html_report(html)

    assert result["status"] == "critical"
    assert any("missing locked-template marker" in e for e in result["errors"])
    assert any("line count is too low" in e for e in result["errors"])


def test_validate_report_html_accepts_locked_like_page(tmp_path: Path) -> None:
    skeleton = tmp_path / "_locked_cn_skeleton.html"
    html = tmp_path / "Company_Research_CN.html"
    payload = _locked_like_html()
    skeleton.write_text(payload, encoding="utf-8")
    html.write_text(payload.replace("locked filler", "filled filler"), encoding="utf-8")

    result = validate_html_report(html, skeleton)

    assert result["status"] == "pass"
    assert result["errors"] == []


def test_validate_report_html_rejects_freeform_porter_text(tmp_path: Path) -> None:
    skeleton = tmp_path / "_locked_cn_skeleton.html"
    html = tmp_path / "Company_Research_CN.html"
    skeleton.write_text(_locked_like_html(), encoding="utf-8")
    html.write_text(_locked_like_html(porter_valid=False), encoding="utf-8")

    result = validate_html_report(html, skeleton)

    assert result["status"] == "critical"
    assert any(".porter-text" in e for e in result["errors"])


def test_validate_report_html_rejects_metrics_table_with_pl_amounts(tmp_path: Path) -> None:
    """I-005: metrics table emitting absolute P&L amounts must fail validation."""
    skeleton = tmp_path / "_locked_cn_skeleton.html"
    html = tmp_path / "Company_Research_CN.html"
    skeleton.write_text(_locked_like_html(), encoding="utf-8")
    html.write_text(_locked_like_html(metrics_valid=False), encoding="utf-8")

    result = validate_html_report(html, skeleton)

    assert result["status"] == "critical"
    assert any("metrics-table" in e and "I-005" in e for e in result["errors"])
    assert any("9 <tr>" in e for e in result["errors"])
    assert any("not in the controlled ratio whitelist" in e for e in result["errors"])
