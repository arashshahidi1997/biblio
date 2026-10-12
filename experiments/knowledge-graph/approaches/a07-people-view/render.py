"""Render people.json as one self-contained HTML page (cards, network, institutions).

Photos are hotlinked Commons thumbnails with author and license shown on the card.
"""
from __future__ import annotations

import json

D3 = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"

CSS = """
:root{--bg:#f7f6f3;--panel:#fff;--ink:#1d1d1b;--muted:#6b6a65;--line:#e4e2dc;--accent:#2f6f8f;
--first:#2f6f8f;--last:#8f4f2f;--middle:#9a988f;--chip:#efede7}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161615;--panel:#1f1f1d;--ink:#ecebe6;
--muted:#9c9a92;--line:#33322f;--accent:#7fb4cf;--first:#7fb4cf;--last:#d49a78;--middle:#77756e;--chip:#2a2a27}}
:root[data-theme="dark"]{--bg:#161615;--panel:#1f1f1d;--ink:#ecebe6;--muted:#9c9a92;--line:#33322f;--accent:#7fb4cf;
--first:#7fb4cf;--last:#d49a78;--middle:#77756e;--chip:#2a2a27}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 16px 60px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:36px 0 12px}
.sub{color:var(--muted);margin:0 0 18px}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.stat b{display:block;font-size:20px}.stat span{color:var(--muted);font-size:13px}
nav{display:flex;gap:6px;margin:24px 0 0;flex-wrap:wrap}nav button{border:1px solid var(--line);background:var(--panel);
color:var(--ink);padding:6px 12px;border-radius:999px;cursor:pointer;font:inherit}
nav button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:8px}
.card:target{outline:2px solid var(--accent)}
.head{display:flex;gap:12px;align-items:center}.av{width:64px;height:64px;border-radius:50%;flex:none;object-fit:cover;
background:var(--chip);display:flex;align-items:center;justify-content:center;font-weight:600;color:#fff;font-size:20px}
.name{font-weight:600;font-size:16px}.inst{color:var(--muted);font-size:13px}.links a{font-size:12px;margin-right:8px}
.metrics{display:flex;gap:14px;font-size:13px;color:var(--muted)}.metrics b{color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:4px}.chip{background:var(--chip);border-radius:4px;padding:1px 6px;font-size:12px}
ul.papers{margin:0;padding:0;list-style:none;font-size:13px}ul.papers li{padding:2px 0;display:flex;gap:6px;align-items:baseline}
.pos{font-size:10px;text-transform:uppercase;letter-spacing:.04em;border-radius:3px;padding:0 4px;color:#fff;flex:none}
.pos.first{background:var(--first)}.pos.last{background:var(--last)}.pos.middle{background:var(--middle)}
.corr{font-size:10px;color:var(--muted)}.off{opacity:.55}
.credit{font-size:11px;color:var(--muted)}.label{font-size:12px;color:var(--muted);margin-bottom:2px}
#net{background:var(--panel);border:1px solid var(--line);border-radius:10px;width:100%;height:620px}
#net text{font-size:10px;fill:var(--ink);pointer-events:none}
table{width:100%;border-collapse:collapse;background:var(--panel);font-size:13px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{color:var(--muted);font-weight:500}
.tl{display:grid;gap:2px}.cell{height:18px;border-radius:2px;background:var(--accent)}
input[type=search]{width:100%;max-width:360px;padding:7px 10px;border:1px solid var(--line);border-radius:6px;
background:var(--panel);color:var(--ink);font:inherit;margin-bottom:10px}
.wrap{overflow-x:auto}.hidden{display:none}.note{font-size:13px;color:var(--muted)}
"""

JS = r"""
const D = JSON.parse(document.getElementById('data').textContent);
const P = D.persons, papers = D.papers, insts = D.institutions;
const byId = Object.fromEntries(P.map(p => [p.id, p]));
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const hue = s => [...s].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
const initials = n => n.split(/\s+/).filter(Boolean).map(w => w[0]).slice(0, 2).join('').toUpperCase();
function avatar(p, size) {
  if (p.photo && p.photo.thumb) return `<img class="av" style="width:${size}px;height:${size}px" src="${esc(p.photo.thumb)}" alt="${esc(p.name)}" loading="lazy">`;
  return `<div class="av" style="width:${size}px;height:${size}px;background:hsl(${hue(p.name)} 35% 45%)">${esc(initials(p.name))}</div>`;
}
function card(p) {
  const inst = (p.last_known[0] || {}).name || Object.keys(p.institutions).map(i => insts[i]?.name)[0] || '';
  const links = [
    p.orcid && `<a href="https://orcid.org/${p.orcid}" target="_blank">ORCID</a>`,
    p.openalex && `<a href="https://openalex.org/${p.openalex}" target="_blank">OpenAlex</a>`,
    p.wikidata && `<a href="https://www.wikidata.org/wiki/${p.wikidata.item}" target="_blank">Wikidata</a>`,
  ].filter(Boolean).join('');
  const ps = [...p.papers].sort((a, b) => (b.year || 0) - (a.year || 0)).map(r => {
    const pp = papers[r.citekey];
    return `<li class="${r.on_topic ? '' : 'off'}"><span class="pos ${r.position}">${r.position[0]}</span>
      <span>${esc(pp.title)} <span class="corr">${pp.year || ''}${r.corresponding ? ' · corresponding' : ''}</span></span></li>`;
  }).join('');
  const co = p.coauthors.slice(0, 8).map(c => `<a class="chip" href="#${cssId(c.id)}">${esc(byId[c.id].name)}${c.papers.length > 1 ? ' ×' + c.papers.length : ''}</a>`).join('');
  const adv = p.wikidata?.advisors?.length ? `<div><div class="label">Doctoral advisor (Wikidata)</div>${p.wikidata.advisors.map(a => esc(a.label)).join(', ')}</div>` : '';
  const credit = !p.photo ? '' : p.photo.origin === 'local'
    ? `<div class="credit">Photo: local file, private</div>`
    : `<div class="credit">Photo: ${esc(p.photo.artist || 'unknown')}, <a href="${esc(p.photo.page)}" target="_blank">${esc(p.photo.license || 'see Commons')}</a> (Wikimedia Commons)</div>`;
  return `<div class="card" id="${cssId(p.id)}">
    <div class="head">${avatar(p, 64)}<div><div class="name">${esc(p.name)}</div><div class="inst">${esc(inst)}</div><div class="links">${links}</div></div></div>
    <div class="metrics"><span><b>${p.papers.length}</b> in corpus</span>${p.h_index != null ? `<span>h <b>${p.h_index}</b></span>` : ''}${p.works_count != null ? `<span><b>${p.works_count}</b> works</span>` : ''}</div>
    ${p.topics.length ? `<div class="chips">${p.topics.map(t => `<span class="chip">${esc(t)}</span>`).join('')}</div>` : ''}
    <div><div class="label">Papers in corpus</div><ul class="papers">${ps}</ul></div>
    ${co ? `<div><div class="label">Co-authors in corpus</div><div class="chips">${co}</div></div>` : ''}
    ${adv}${credit}</div>`;
}
const cssId = id => id.replace(/[^a-zA-Z0-9_-]/g, '_');

function renderCards(all) {
  const list = all ? P : P.filter(p => p.score_topic > 0);
  document.getElementById('cards').innerHTML = list.map(card).join('');
}
renderCards(false);
document.getElementById('showall').onchange = e => renderCards(e.target.checked);

// people table
function renderTable(q) {
  q = (q || '').toLowerCase();
  const rows = P.filter(p => !q || p.name.toLowerCase().includes(q) || Object.keys(p.institutions).some(i => (insts[i]?.name || '').toLowerCase().includes(q)));
  document.getElementById('ptable').innerHTML = rows.map(p => `<tr><td><a href="#${cssId(p.id)}" onclick="show('contrib');document.getElementById('showall').checked=true;renderCards(true)">${esc(p.name)}</a></td>
    <td>${p.papers.length}</td><td>${p.score_topic}</td><td>${p.orcid ? '✓' : ''}</td><td>${p.photo ? '✓' : ''}</td>
    <td>${esc(Object.keys(p.institutions).map(i => insts[i]?.name).join('; '))}</td></tr>`).join('');
}
renderTable('');
document.getElementById('q').oninput = e => renderTable(e.target.value);

// institutions over time
(function () {
  const years = Object.values(papers).map(p => p.year).filter(Boolean);
  const y0 = Math.min(...years), y1 = Math.max(...years);
  const rows = {};
  for (const p of P) for (const r of p.papers) for (const i of r.institutions) {
    rows[i] ??= {}; rows[i][r.citekey] = r.year;
  }
  const ranked = Object.entries(rows).map(([i, cks]) => [i, Object.values(cks)]).sort((a, b) => b[1].length - a[1].length).slice(0, 25);
  const span = y1 - y0 + 1;
  document.getElementById('itable').innerHTML = ranked.map(([i, ys]) => {
    const cells = Array.from({length: span}, (_, k) => { const n = ys.filter(y => y === y0 + k).length;
      return `<div class="cell" title="${y0 + k}: ${n}" style="opacity:${n ? Math.min(1, .35 + .3 * n) : .06}"></div>`; }).join('');
    return `<tr><td>${esc(insts[i]?.name)}</td><td>${esc(insts[i]?.country)}</td><td>${ys.length}</td>
      <td style="min-width:${span * 7}px"><div class="tl" style="grid-template-columns:repeat(${span},1fr)">${cells}</div></td></tr>`;
  }).join('');
  document.getElementById('yspan').textContent = `${y0} to ${y1}`;
})();

// co-author network (topic papers only)
let netDone = false;
function drawNet() {
  if (netDone || typeof d3 === 'undefined') return; netDone = true;
  const keep = new Set(P.filter(p => p.score_topic > 0).map(p => p.id));
  const nodes = P.filter(p => keep.has(p.id)).map(p => ({id: p.id, p}));
  const links = [];
  for (const p of P) if (keep.has(p.id)) for (const c of p.coauthors)
    if (keep.has(c.id) && p.id < c.id) {
      const k = c.papers.filter(ck => papers[ck].on_topic).length;
      if (k) links.push({source: p.id, target: c.id, w: k});
    }
  const svg = d3.select('#net'), W = svg.node().clientWidth, H = 620;
  svg.attr('viewBox', `0 0 ${W} ${H}`);
  const defs = svg.append('defs'), g = svg.append('g');
  svg.call(d3.zoom().scaleExtent([.3, 4]).on('zoom', e => g.attr('transform', e.transform)));
  const r = d => 5 + 3.5 * Math.sqrt(d.p.papers.filter(x => x.on_topic).length);
  nodes.forEach(d => { if (d.p.photo?.thumb) defs.append('pattern').attr('id', 'ph_' + cssId(d.id)).attr('width', 1).attr('height', 1)
    .attr('patternContentUnits', 'objectBoundingBox').append('image').attr('href', d.p.photo.thumb).attr('width', 1).attr('height', 1).attr('preserveAspectRatio', 'xMidYMid slice'); });
  const sim = d3.forceSimulation(nodes).force('link', d3.forceLink(links).id(d => d.id).distance(l => 50 / l.w).strength(.4))
    .force('charge', d3.forceManyBody().strength(-60)).force('center', d3.forceCenter(W / 2, H / 2)).force('collide', d3.forceCollide(d => r(d) + 2));
  const link = g.append('g').attr('stroke', 'var(--line)').selectAll('line').data(links).join('line').attr('stroke-width', d => Math.min(5, d.w));
  const node = g.append('g').selectAll('circle').data(nodes).join('circle').attr('r', r)
    .attr('fill', d => d.p.photo?.thumb ? `url(#ph_${cssId(d.id)})` : `hsl(${hue(d.p.name)} 35% 50%)`)
    .attr('stroke', 'var(--panel)').attr('stroke-width', 1.5).style('cursor', 'pointer')
    .on('click', (e, d) => { show('contrib'); location.hash = cssId(d.id); })
    .call(d3.drag().on('start', (e, d) => { if (!e.active) sim.alphaTarget(.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; }).on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = d.fy = null; }));
  node.append('title').text(d => `${d.p.name} (${d.p.papers.length} papers)`);
  const label = g.append('g').selectAll('text').data(nodes.filter(d => d.p.score_topic >= 1.5)).join('text').text(d => d.p.name).attr('dy', -10).attr('text-anchor', 'middle');
  sim.on('tick', () => {
    link.attr('x1', d => d.source.x).attr('y1', d => d.source.y).attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    node.attr('cx', d => d.x).attr('cy', d => d.y); label.attr('x', d => d.x).attr('y', d => d.y);
  });
}

function show(id) {
  for (const s of document.querySelectorAll('section[data-tab]')) s.classList.toggle('hidden', s.dataset.tab !== id);
  for (const b of document.querySelectorAll('nav button')) b.classList.toggle('on', b.dataset.tab === id);
  if (id === 'net') drawNet();
}
for (const b of document.querySelectorAll('nav button')) b.onclick = () => show(b.dataset.tab);
show('contrib');
"""


def page(data: dict, stats: dict, run_id: str) -> str:
    def first(v):
        return str(v).split(" ")[0]

    tiles = [
        (stats["persons"], "people"),
        (first(stats["with_orcid"]), "with ORCID"),
        (first(stats["with_wikidata_item"]), "in Wikidata"),
        (first(stats["with_photo"]), "with open photo"),
        (stats["institutions"], "institutions"),
        (stats["countries"], "countries"),
        (f"{stats['papers_on_topic']}/{stats['papers_with_openalex']}", "papers on topic"),
    ]
    stat_html = "".join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for v, k in tiles)
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Corpus People View</title><style>{CSS}</style></head>
<body><main>
<h1>People in the corpus</h1>
<p class="sub">a07 people view · run {run_id} · built from OpenAlex authorships, Wikidata and Wikimedia Commons</p>
<div class="stats">{stat_html}</div>
<nav><button data-tab="contrib">Contributors</button><button data-tab="net">Co-author network</button>
<button data-tab="inst">Institutions over time</button><button data-tab="all">All people</button></nav>

<section data-tab="contrib"><h2>Contributors to ripple and spindle research</h2>
<p class="note">Ranked by authorship on topic papers (first or last author 1.0, middle 0.25, corresponding +0.5).
Greyed papers are outside the topic. <label><input type="checkbox" id="showall"> show everyone</label></p>
<div class="grid" id="cards"></div></section>

<section data-tab="net" class="hidden"><h2>Co-author network, topic papers</h2>
<p class="note">Node size: topic papers. Edge width: shared topic papers. Drag to move, scroll to zoom, click to open a card.</p>
<svg id="net"></svg></section>

<section data-tab="inst" class="hidden"><h2>Institutions over time</h2>
<p class="note">Top 25 institutions by corpus papers. Each cell is a year, <span id="yspan"></span>.</p>
<div class="wrap"><table><thead><tr><th>Institution</th><th>Country</th><th>Papers</th><th>Timeline</th></tr></thead>
<tbody id="itable"></tbody></table></div></section>

<section data-tab="all" class="hidden"><h2>All people</h2>
<input type="search" id="q" placeholder="Filter by name or institution">
<div class="wrap"><table><thead><tr><th>Name</th><th>Papers</th><th>Topic score</th><th>ORCID</th><th>Photo</th><th>Institutions in corpus</th></tr></thead>
<tbody id="ptable"></tbody></table></div></section>
</main>
<script id="data" type="application/json">{payload}</script>
<script src="{D3}"></script>
<script>{JS}</script>
</body></html>
"""
