"""Genereert het HTML dashboard (docs/index.html) voor GitHub Pages."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Template

TEMPLATE = Template("""<!doctype html>
<html lang="nl">
<head>
<meta charset="utf-8">
<title>Card Tracker - Pokemon & One Piece NL</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg: #0f172a; --panel:#1e293b; --muted:#94a3b8; --fg:#e2e8f0;
    --accent:#38bdf8; --good:#22c55e; --warn:#f59e0b; --bad:#ef4444;
    --border:#334155;
  }
  * { box-sizing: border-box; }
  body { margin:0; font-family: ui-sans-serif, system-ui, sans-serif; background:var(--bg); color:var(--fg); }
  header { padding: 24px 32px; border-bottom:1px solid var(--border); }
  header h1 { margin:0 0 4px 0; font-size: 22px; }
  header .meta { color: var(--muted); font-size: 13px; }
  main { padding: 24px 32px; max-width: 1200px; margin: 0 auto; }
  h2 { margin-top: 36px; font-size: 18px; border-bottom:1px solid var(--border); padding-bottom:8px; }
  h3 { margin: 18px 0 8px; font-size: 15px; color: var(--accent); }
  table { width:100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align:left; padding: 8px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
  th { color: var(--muted); font-weight: 500; font-size: 12px; text-transform: uppercase; letter-spacing: .5px; }
  tr.changed { background: rgba(56,189,248,0.08); }
  tr.error { background: rgba(239,68,68,0.10); }
  .badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; }
  .b-good { background: rgba(34,197,94,0.15); color: var(--good); }
  .b-warn { background: rgba(245,158,11,0.15); color: var(--warn); }
  .b-bad { background: rgba(239,68,68,0.18); color: var(--bad); }
  .b-info { background: rgba(56,189,248,0.15); color: var(--accent); }
  .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(240px,1fr)); gap: 12px; }
  .card { background: var(--panel); border:1px solid var(--border); border-radius: 8px; padding: 12px; }
  .card .name { font-weight:600; font-size:14px; }
  .card .meta { color: var(--muted); font-size: 12px; margin-top:4px; }
  .card.new { outline: 2px solid var(--accent); }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .changes { font-size: 12px; color: var(--muted); }
  .changes .real { color: var(--fg); }
  .pill { font-size:11px; padding:1px 6px; border-radius:4px; background:#334155; color:var(--muted); margin-right:4px; }
  details > summary { cursor: pointer; padding: 4px 0; color: var(--muted); }
  .empty { color: var(--muted); font-style: italic; }
</style>
</head>
<body>
<header>
  <h1>Card Tracker - Pokemon & One Piece (NL)</h1>
  <div class="meta">Laatst bijgewerkt: {{ generated_at }} - regio Maastricht en NL online</div>
</header>
<main>

<h2>Set releases (officiele APIs)</h2>

<h3>Pokemon TCG - laatste sets</h3>
{% if pkm_sets %}
<div class="grid">
{% for s in pkm_sets %}
  <div class="card {% if s.id in new_pkm_ids %}new{% endif %}">
    <div class="name">{{ s.name }} {% if s.id in new_pkm_ids %}<span class="badge b-info">NIEUW</span>{% endif %}</div>
    <div class="meta">
      <span class="pill">{{ s.series or "?" }}</span>
      <span class="pill">{{ s.releaseDate or "?" }}</span>
      {% if s.total %}<span class="pill">{{ s.total }} kaarten</span>{% endif %}
    </div>
  </div>
{% endfor %}
</div>
{% else %}
<p class="empty">Geen data (API niet bereikbaar?).</p>
{% endif %}

<h3>One Piece TCG - laatste sets</h3>
{% if op_sets %}
<div class="grid">
{% for s in op_sets %}
  <div class="card {% if s.id in new_op_ids %}new{% endif %}">
    <div class="name">{{ s.name or s.id }} {% if s.id in new_op_ids %}<span class="badge b-info">NIEUW</span>{% endif %}</div>
    <div class="meta">
      {% if s.id %}<span class="pill">{{ s.id }}</span>{% endif %}
      {% if s.releaseDate %}<span class="pill">{{ s.releaseDate }}</span>{% endif %}
      {% if s.total %}<span class="pill">{{ s.total }} kaarten</span>{% endif %}
    </div>
  </div>
{% endfor %}
</div>
{% else %}
<p class="empty">Geen data (API niet bereikbaar?).</p>
{% endif %}

{% if api_errors %}
<details>
<summary>API fouten ({{ api_errors|length }})</summary>
<ul>
{% for e in api_errors %}<li><b>{{ e.name }}</b>: {{ e.error }}</li>{% endfor %}
</ul>
</details>
{% endif %}

<h2>Maastricht en omstreken</h2>
{{ shop_table(shop_results|selectattr("region","equalto","maastricht")|list) }}

<h2>NL webshops</h2>
{{ shop_table(shop_results|selectattr("region","equalto","nl-online")|list) }}

<footer style="margin-top:48px; color:var(--muted); font-size:12px;">
  Tip: pas <code>config/sources.yaml</code> aan om bronnen toe te voegen of te verwijderen.
  Geschiedenis staat in <code>data/history.jsonl</code>.
</footer>
</main>
</body></html>
""")

# Macro is lastig in een Template-string; we doen het via een helper-include via globals.
SHOP_TABLE_TEMPLATE = Template("""
{% if rows %}
<table>
  <thead>
    <tr>
      <th>Shop</th><th>Pagina</th><th>Status</th><th>Items (~)</th><th>Wijzigingen</th>
    </tr>
  </thead>
  <tbody>
  {% for r in rows %}
    {% set has_real = r.changes and not (r.changes|length == 1 and r.changes[0] == "geen wijziging") %}
    <tr class="{% if not r.ok %}error{% elif has_real %}changed{% endif %}">
      <td>{{ r.shop }}</td>
      <td><a href="{{ r.url }}" target="_blank" rel="noopener">{{ r.title or r.url }}</a></td>
      <td>
        {% if r.ok %}
          <span class="badge b-good">{{ r.status }}</span>
        {% else %}
          <span class="badge b-bad">{{ r.status or "ERR" }}</span>
        {% endif %}
      </td>
      <td>{{ r.price_count }}</td>
      <td class="changes">
        {% for c in r.changes %}
          <div class="{{ 'real' if c != 'geen wijziging' else '' }}">- {{ c }}</div>
        {% endfor %}
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% else %}
<p class="empty">Geen bronnen geconfigureerd voor deze regio.</p>
{% endif %}
""")


def _shop_table(rows):
    return SHOP_TABLE_TEMPLATE.render(rows=rows)


TEMPLATE.globals["shop_table"] = _shop_table


def render(*, out: Path, generated_at: str, shop_results: list[dict],
           pkm_sets: list[dict], op_sets: list[dict],
           new_pkm_ids: list[str], new_op_ids: list[str],
           api_errors: list[dict]) -> None:
    html = TEMPLATE.render(
        generated_at=generated_at,
        shop_results=shop_results,
        pkm_sets=pkm_sets,
        op_sets=op_sets,
        new_pkm_ids=set(new_pkm_ids),
        new_op_ids=set(new_op_ids),
        api_errors=api_errors,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
