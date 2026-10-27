"""Self-contained, script-free HTML summaries; all research data is rendered as text."""

from __future__ import annotations

import json
from collections import Counter
from html import escape
from typing import Any

STYLES = """
:root{color-scheme:dark;--bg:#0c1220;--panel:#141e30;--ink:#e8eef8;
--muted:#aebcd0;--line:#2c3c54;--accent:#65e1d3}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 system-ui,Segoe UI,sans-serif}main{max-width:1400px;margin:auto;padding:32px 24px}
header{border:1px solid var(--line);border-radius:16px;padding:28px;background:var(--panel)}
.brand{color:var(--accent);font-weight:700;letter-spacing:.16em;font-size:12px}
h1{margin:8px 0;font-size:clamp(26px,4vw,42px);overflow-wrap:anywhere}
h2{margin:32px 0 12px;font-size:22px}p{margin:8px 0}.muted,small{color:var(--muted)}
a{color:var(--accent);text-underline-offset:3px}a:focus-visible,summary:focus-visible{
outline:3px solid #e1a4ff;outline-offset:4px}
nav{display:flex;gap:18px;flex-wrap:wrap;margin-top:18px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:12px;margin:20px 0}
.card{padding:18px;background:var(--panel);border:1px solid var(--line);border-radius:12px}
.card strong{display:block;font-size:28px}.card span{color:var(--muted);font-size:13px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px}
table{width:100%;border-collapse:collapse;text-align:left;background:var(--panel)}
th,td{padding:12px 14px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
td{overflow-wrap:anywhere}tr:last-child td{border-bottom:0}.host{min-width:240px}
.state{display:inline-block;border:1px solid var(--line);border-radius:6px;padding:2px 8px;
white-space:nowrap}.up{color:#87ebbc}.down{color:#ffbaa6}.unknown{color:#eed18a}
details{margin:8px 0}summary{cursor:pointer;color:var(--accent)}pre{white-space:pre-wrap;
overflow-wrap:anywhere;background:var(--bg);padding:12px;border-radius:8px;font-size:12px}
.note{border-left:3px solid #e1a4ff;padding:8px 16px;margin:18px 0;color:var(--muted)}
.empty{padding:24px;border:1px dashed var(--line);border-radius:12px;color:var(--muted)}
footer{margin:32px 0;color:var(--muted);font-size:13px}
@media(max-width:600px){main{padding:16px 12px}header{padding:20px}th,td{padding:10px}}
@media print{:root{color-scheme:light;--bg:#fff;--panel:#fff;--ink:#111;--muted:#444;
--line:#bbb;--accent:#145d61}main{padding:0}header,.card{break-inside:avoid}
.scroll{overflow:visible}.up,.down,.unknown{color:#111}nav{display:none}}
"""


def text(value: Any) -> str:
    return escape(str(value) if value is not None else "—", quote=True)


def render_html(report: dict[str, Any]) -> str:
    assets = report["assets"]
    states = Counter(a["latest"]["state"] for a in assets)
    cards = [
        ("Discovered hosts", len(assets)),
        ("HTTP responding", states["online"]),
        ("TLS errors", states["tls_error"]),
        ("Down observed", sum(states[s] for s in ("nxdomain", "no_address", "unreachable"))),
        ("Intermittent candidates", sum(bool(a["intermittent_candidate"]) for a in assets)),
        ("Archived URLs", report["archive_summary"]["unique_urls"]),
    ]
    metrics = "".join(
        f'<div class="card"><strong>{count}</strong><span>{label}</span></div>'
        for label, count in cards
    )
    rows = []
    for asset in assets:
        latest = asset["latest"]
        state = latest["state"]
        style = (
            "up"
            if state == "online"
            else ("down" if state in ("nxdomain", "no_address", "unreachable") else "unknown")
        )
        evidence = asset["evidence"]
        # Keep the HTML readable; the adjacent JSON contains all retained evidence/samples.
        detail = {"evidence_preview": evidence[:20], "recent_samples": asset["samples"][-5:]}
        details = (
            f"<details><summary>Evidence ({len(evidence)} records)</summary>"
            '<p class="muted">Preview: first 20 evidence records and latest 5 samples. '
            "Use JSON for the full exported history.</p>"
            f"<pre>{text(json.dumps(detail, indent=2, ensure_ascii=False))}</pre></details>"
        )
        rows.append(
            f'<tr><td class="host"><strong>{text(asset["hostname"])}</strong>{details}</td>'
            f"<td>{text(', '.join(asset['sources']))}</td>"
            f'<td><span class="state {style}">{text(state)}</span>'
            f"<br><small>DNS: {text(latest.get('dns_state', 'unchecked'))}</small></td>"
            f"<td>{text(', '.join(latest.get('addresses', [])) or '—')}</td>"
            f"<td>{text(asset['transitions'])} / {text(asset['dns_transitions'])}"
            f"<br><small>{'Candidate' if asset['intermittent_candidate'] else 'No flag'}"
            "</small></td>"
            f"<td>{text(asset['first_seen'])}<br><small>Last: {text(asset['last_seen'])}"
            "</small></td></tr>"
        )
    hosts = (
        (
            '<div class="scroll"><table><thead><tr><th scope="col">Host / evidence</th>'
            '<th scope="col">Sources</th><th scope="col">Latest state</th>'
            '<th scope="col">Addresses</th>'
            '<th scope="col">Changes HTTP / DNS</th><th scope="col">Local discovery (UTC)</th>'
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        )
        if rows
        else '<p class="empty">No hosts stored yet. Review provider results below.</p>'
    )
    audits = []
    for run in report["provider_runs"]:
        payload = run["payload"]
        coverage = (
            "Incomplete" if payload.get("truncated") or payload.get("error") else "See status"
        )
        audits.append(
            f"<tr><td>{text(run['source'])}</td><td>{text(run['observed_at'])}</td>"
            f"<td>{text(run['status'])}</td><td>{text(payload.get('count', 0))}</td>"
            f"<td>{coverage}</td><td>{text(payload.get('error') or '—')}</td></tr>"
        )
    providers = (
        (
            '<div class="scroll"><table><thead><tr><th scope="col">Source</th>'
            '<th scope="col">Observed (UTC)</th><th scope="col">Status</th>'
            '<th scope="col">Records</th>'
            '<th scope="col">Coverage</th><th scope="col">Error</th></tr></thead><tbody>'
            + "".join(audits)
            + "</tbody></table></div>"
        )
        if audits
        else '<p class="empty">No provider audit entries recorded.</p>'
    )
    notes = "".join(f"<li>{text(note)}</li>" for note in report["notes"])
    parameters = ", ".join(report["archive_summary"]["parameter_names"]) or "None observed"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy"
content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer">
<title>{text(report["target"])} — Wayback Atlas report</title><style>{STYLES}</style></head>
<body><main><header><div class="brand">WAYBACK ATLAS / THE RECON WEB</div>
<h1>{text(report["target"])}</h1>
<p class="muted">Reconnaissance snapshot · {text(report["generated_at"])}</p>
<p>Use only on assets you own or have permission to assess.</p>
<nav aria-label="Companion exports"><a href="report.json">Full JSON</a>
<a href="inventory.csv">Inventory CSV</a><a href="hosts.txt">All hosts</a>
<a href="alive.txt">Alive observations</a><a href="down_observed.txt">Down observations</a>
<a href="intermittent.txt">Intermittent candidates</a></nav></header>
<section aria-label="Summary" class="cards">{metrics}</section>
<p class="note">Offline report: no scripts, external resources or automatic target requests.
Historical evidence is not proof of current ownership or availability.
Treat this report as private research data.</p>
<h2>Host inventory</h2>
<p class="muted">{len(assets)} hosts · Expand a host's evidence for context.</p>{hosts}
<h2>Archive overview</h2>
<p>Unique endpoints: {text(report["archive_summary"]["unique_endpoints"])}</p>
<p>Observed parameter names: {text(parameters)}</p>
<h2>Provider activity</h2>
<p class="muted">Latest 100 audit entries, including page commits and errors.
A successful page does not establish complete provider coverage;
inspect saved run status in Atlas.</p>{providers}
<h2>How to interpret this report</h2><ul>{notes}</ul>
<footer>{text(report["history_window"])}.
Companion links require the other files in this export folder.
Generated locally by Wayback Atlas.</footer></main></body></html>
"""
