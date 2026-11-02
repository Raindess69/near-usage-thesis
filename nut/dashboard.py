"""Write the static dashboard docs/index.html (GitHub Pages serves /docs)."""
from __future__ import annotations

import html
import json

from .config import Paths
from .util import fmt_near, fmt_pct, fmt_usd

REPO = "https://github.com/Raindess69/near-usage-thesis"


def _link(src: str) -> str:
    out = []
    for part in src.split(" "):
        if part.startswith("http"):
            out.append(f'<a href="{html.escape(part)}">{html.escape(part)}</a>')
        else:
            out.append(html.escape(part))
    return " ".join(out)


def summary_paragraph(m: dict) -> str:
    iss, cap, be, ll = m["issuance"], m["capture"], m["breakeven"], m["leadlag"]
    d90 = cap["d90"]
    return (
        f"NEAR mints about {fmt_pct(iss['rpc_annualized_issuance'], 2)} of supply per year ({fmt_near(iss['rpc_minted_per_day_near'])} per day, measured from block headers). "
        f"Over the last 90 days, gas burn offset {fmt_pct(d90['coverage_burn'], 1)} of that and NEAR Intents revenue another {fmt_pct(d90['coverage_intents'], 1)}, "
        f"so usage paid for {fmt_pct(d90['coverage_total'], 1)} of issuance. Intents revenue is now {d90['intents_revenue_over_gas_fees']:.0f}x the chain's gas fees, "
        f"so the long-term case rests on Intents, not on L1 transactions. Break-even needs {be['multiple']:.1f}x more revenue at today's price; "
        f"none of the weekly usage series reliably leads price ({ll['n_significant']} of {ll['n_tests']} lead-lag tests significant after correction)."
        if ll["n_significant"] == 0
        else
        f"NEAR mints about {fmt_pct(iss['rpc_annualized_issuance'], 2)} of supply per year ({fmt_near(iss['rpc_minted_per_day_near'])} per day, measured from block headers). "
        f"Over the last 90 days, gas burn offset {fmt_pct(d90['coverage_burn'], 1)} of that and NEAR Intents revenue another {fmt_pct(d90['coverage_intents'], 1)}, "
        f"so usage paid for {fmt_pct(d90['coverage_total'], 1)} of issuance. Intents revenue is now {d90['intents_revenue_over_gas_fees']:.0f}x the chain's gas fees, "
        f"so the long-term case rests on Intents, not on L1 transactions. Break-even needs {be['multiple']:.1f}x more revenue at today's price; "
        f"{ll['n_significant']} of {ll['n_tests']} lead-lag tests are significant after correction (see chart 8)."
    )


CSS = """
:root{--fg:#1f2328;--muted:#59636e;--line:#d1d9e0;--green:#00a86b;--bg:#fff;--card:#f6f8fa}
*{box-sizing:border-box}body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;color:var(--fg);background:var(--bg)}
main{max-width:980px;margin:0 auto;padding:28px 20px 60px}h1{font-size:28px;margin:0 0 6px}h2{font-size:19px;margin:34px 0 8px}
.meta{color:var(--muted);font-size:13px}.answer{background:var(--card);border-left:4px solid var(--green);padding:14px 16px;margin:18px 0;font-size:15.5px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin:14px 0}
.card{border:1px solid var(--line);border-radius:8px;padding:10px 12px}.card .v{font-size:22px;font-weight:700}.card .k{color:var(--muted);font-size:12.5px}
section.chart{border-top:1px solid var(--line);padding-top:6px;margin-top:26px}section.chart img{width:100%;height:auto;border:1px solid var(--line);border-radius:6px;background:#fff}
.sentence{font-weight:600;margin:8px 0}.src{font-size:13px;color:var(--muted)}.src code{font-size:12.5px}
#live{border:1px dashed var(--green);border-radius:8px;padding:12px 14px;margin:18px 0}#live table{border-collapse:collapse;font-size:13.5px}#live td{padding:2px 10px 2px 0}
code{background:var(--card);padding:1px 4px;border-radius:4px}a{color:#0969da}
"""

LIVE_JS = r"""
(async function(){
  const out = document.getElementById('live-out');
  const S = %SNAPSHOT%;
  const fmt = (x, d=1) => (100*x).toFixed(d) + '%';
  try {
    const [rev, fees, st] = await Promise.all([
      fetch('https://api.llama.fi/summary/fees/near-intents?dataType=dailyRevenue&excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true').then(r=>r.json()),
      fetch('https://api.llama.fi/summary/fees/near?dataType=dailyFees&excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true').then(r=>r.json()),
      fetch('https://api.nearblocks.io/v1/stats').then(r=>r.json())
    ]);
    const s = st.stats[0];
    const price = parseFloat(s.near_price);
    const supply = Number(BigInt(s.total_supply) / 10n**18n) / 1e6;
    const minted30usd = supply * S.issuance_rate * 30/365 * price;
    const burn30usd = fees.total30d * S.burn_to_fee_ratio;
    const cov = (rev.total30d + burn30usd) / minted30usd;
    out.innerHTML = `<table>
      <tr><td>NEAR price (NearBlocks)</td><td><b>$${price.toFixed(3)}</b></td></tr>
      <tr><td>Total supply</td><td><b>${(supply/1e9).toFixed(4)}B NEAR</b></td></tr>
      <tr><td>NEAR Intents revenue, last 30 days (DefiLlama)</td><td><b>$${(rev.total30d/1e6).toFixed(2)}M</b></td></tr>
      <tr><td>Gas fees, last 30 days (DefiLlama) x burn ratio ${S.burn_to_fee_ratio.toFixed(2)}</td><td><b>$${(burn30usd/1e3).toFixed(1)}K</b></td></tr>
      <tr><td>Issuance, 30 days at ${fmt(S.issuance_rate,2)}/yr</td><td><b>$${(minted30usd/1e6).toFixed(2)}M</b></td></tr>
      <tr><td>Share of issuance paid by usage, live estimate</td><td><b>${fmt(cov)}</b> (snapshot ${S.as_of}, 30-day window at daily prices: ${fmt(S.cov30)})</td></tr>
    </table>
    <p class="src">The live estimate values all 30 days of issuance at today's NEAR price; the snapshot values each day at that day's price.
    The two differ when the price moves: a lower price makes the same USD revenue cover more of the NEAR minted (chart 7).</p>`;
  } catch (e) {
    out.textContent = 'Live sources unavailable from this browser (' + e + '). The snapshot numbers below still apply.';
  }
})();
"""


def write(paths: Paths, m: dict, specs: list[dict]) -> None:
    iss, cap, be, ll, use = m["issuance"], m["capture"], m["breakeven"], m["leadlag"], m["usage"]
    d90, d30 = cap["d90"], cap["d30"]
    cards = [
        (fmt_pct(iss["rpc_annualized_issuance"], 2), "gross issuance per year, onchain (last epochs)"),
        (fmt_pct(d90["coverage_burn"], 2), "of issuance offset by gas burn (90 days)"),
        (fmt_pct(d90["coverage_intents"], 1), "offset by NEAR Intents revenue (90 days)"),
        (f"{be['multiple']:.1f}x", "revenue growth needed to cover issuance at today's price"),
        (fmt_usd(be["required_daily_intents_volume_usd"]), f"Intents volume per day needed (now {fmt_usd(be['current_daily_intents_volume_usd'])})"),
        (f"{ll['n_significant']} / {ll['n_tests']}", "lead-lag tests significant after Holm correction"),
        (f"{use['txns_change_from_peak'] * 100:+.0f}%", f"L1 transactions, {use['last_full_month']} vs peak month {use['txns_peak_month']}"),
        (f"{d90['intents_revenue_over_gas_fees']:.0f}x", "Intents revenue / L1 gas fees (90 days)"),
    ]
    snap = {
        "issuance_rate": iss["rpc_annualized_issuance"],
        "burn_to_fee_ratio": iss["burn_to_fee_ratio"],
        "cov30": d30["coverage_total_usd"],
        "as_of": m["as_of"],
    }
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Can NEAR usage pay for NEAR issuance? - evidence dashboard</title>",
        f"<style>{CSS}</style></head><body><main>",
        "<h1>Can NEAR usage pay for NEAR issuance?</h1>",
        f"<div class='meta'>Snapshot as of <b>{m['as_of']}</b> (raw data fetched {m['fetched_at']}). Every number on this page is computed by "
        f"<code>python -m nut build</code> from <a href='{REPO}/tree/main/data/raw'>data/raw/</a>. Thesis: <a href='{REPO}/blob/main/THESIS.md'>THESIS.md</a> - "
        f"code: <a href='{REPO}'>{REPO.replace('https://', '')}</a></div>",
        f"<div class='answer'>{html.escape(summary_paragraph(m))}</div>",
        "<div class='grid'>" + "".join(f"<div class='card'><div class='v'>{html.escape(v)}</div><div class='k'>{html.escape(k)}</div></div>" for v, k in cards) + "</div>",
        "<div id='live'><b>Live check</b> - recomputed in your browser from DefiLlama and NearBlocks right now (30-day window, the formula of chart 3 with issuance valued at today's price):"
        "<div id='live-out'>loading...</div></div>",
    ]
    for s in specs:
        srcs = "<br>".join(_link(x) for x in s["sources"])
        parts.append(
            f"<section class='chart' id='{s['id']}'><h2>{html.escape(s['title'])}</h2>"
            f"<img src='charts/{s['id']}.svg' alt='{html.escape(s['title'])}' loading='lazy'>"
            f"<p class='sentence'>{html.escape(s['sentence'])}</p>"
            f"<p class='src'><b>Source:</b> {srcs}<br><b>Method:</b> {html.escape(s['method'])}<br>"
            f"<b>Code:</b> <a href='{REPO}/blob/main/{s['code'].split('::')[0]}'><code>{html.escape(s['code'])}</code></a> - "
            f"<b>Data:</b> <a href='{REPO}/blob/main/{s['csv']}'><code>{html.escape(s['csv'])}</code></a></p></section>"
        )
    parts.append(
        "<h2>Reproduce</h2><pre><code>git clone https://github.com/Raindess69/near-usage-thesis && cd near-usage-thesis\n"
        "python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt\n"
        "make build    # offline: rebuilds every chart, this page and THESIS.md from data/raw/\n"
        "make verify   # checks the rebuilt numbers match the committed ones\n"
        "make all      # refetches all raw data (public APIs + archival RPC), then rebuilds</code></pre>"
        "<p class='meta'>Not investment advice. Estimates and scenarios are labelled as such; nothing here is a price forecast.</p>"
    )
    parts.append("<script>" + LIVE_JS.replace("%SNAPSHOT%", json.dumps(snap)) + "</script></main></body></html>")
    paths.docs.mkdir(parents=True, exist_ok=True)
    (paths.docs / "index.html").write_text("\n".join(parts) + "\n", encoding="utf-8")
    (paths.docs / ".nojekyll").write_text("", encoding="utf-8")
