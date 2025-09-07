#!/usr/bin/env python3
"""
Generate static HTML snapshots from Hugo-generated markdown section files.
Scans site/content/periods/*/_index.md and writes site/public/periods/<period>/index.html.
Ensures table links point to a single '#user-<id>' anchor (no duplicate 'user-' prefix).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / 'site' / 'content' / 'periods'
PUBLIC = ROOT / 'site' / 'public' / 'periods'

md_files = sorted(CONTENT.glob('**/_index.md'))
if not md_files:
    print('No _index.md files found under', CONTENT)
    raise SystemExit(0)

for md in md_files:
    rel = md.relative_to(CONTENT)
    period_dir = PUBLIC / rel.parent.name
    period_dir.mkdir(parents=True, exist_ok=True)
    out = period_dir / 'index.html'

    text = md.read_text(encoding='utf-8')
    # remove front matter
    text = re.sub(r'^---.*?---\n', '', text, flags=re.S)
    lines = text.splitlines()

    html = []
    html.append('<!doctype html>')
    html.append('<html lang="ko">')
    html.append('<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/css/style.css"><title>Contributions %s</title></head>' % rel.parent.name)
    html.append('<body>')
    html.append('<header><h1><a href="/">Kubernetes Contributions Dashboard</a></h1></header>')
    html.append('<main>')
    html.append('<section class="summary">')

    in_table = False
    for l in lines:
        if l.strip().startswith('| User'):
            in_table = True
            cols = [c.strip() for c in l.strip().strip('|').split('|')]
            html.append('<table class="summary-table"><thead><tr>' + ''.join(f'<th>{c}</th>' for c in cols) + '</tr></thead><tbody>')
            continue
        if in_table:
            if l.strip() == '' or not l.strip().startswith('|'):
                html.append('</tbody></table>')
                in_table = False
            else:
                cols = [c.strip() for c in l.strip().strip('|').split('|')]
                name_md = cols[0]
                m = re.match(r'\[(.*?)\]\(#(.*?)\)', name_md)
                if m:
                    display = m.group(1)
                    anchor_raw = m.group(2)
                    # normalize anchor: strip any leading 'user-' so we add it exactly once
                    anchor_id = re.sub(r'^(user-)+', '', anchor_raw)
                    anchor = 'user-' + anchor_id
                    name_html = f'<a href="#{anchor}">{display}</a>'
                else:
                    name_html = cols[0]
                other_cols = ''.join([f'<td>{c}</td>' for c in cols[1:]])
                html.append('<tr>' + f'<td>{name_html}</td>' + other_cols + '</tr>')
            continue
        # keep anchors and headings
        if l.startswith('<a id="user-'):
            html.append(l)
            continue
        if l.startswith('## '):
            name = l[3:].strip()
            anchor = 'user-' + re.sub(r'[^a-z0-9_-]', '', name.lower().replace(' ', '-'))
            html.append(f'<h2 id="{anchor}">{name}</h2>')
            continue
        if l.startswith('**- '):
            txt = re.sub(r'\*\*', '', l).strip()
            html.append(f'<h3>{txt}</h3>')
            continue
        if l.startswith('- [#'):
            m = re.match(r'- \[(#\d+.*?)\]\((https?://[^)]+)\)(.*)', l)
            if m:
                title = m.group(1)
                url = m.group(2)
                rest = m.group(3)
                html.append(f'<ul><li><a href="{url}" target="_blank">{title}</a>{rest}</li></ul>')
                continue
        if l.startswith('- '):
            html.append('<ul><li>' + l[2:].strip() + '</li></ul>')
            continue
        if l.strip() == '':
            html.append('')
        else:
            html.append(f'<p>{l}</p>')

    html.append('</section>')
    html.append('</main>')
    html.append('<footer><small>Generated static snapshot</small></footer>')
    html.append('</body></html>')

    out.write_text('\n'.join(html), encoding='utf-8')
    print('Wrote', out)

print('Done')
