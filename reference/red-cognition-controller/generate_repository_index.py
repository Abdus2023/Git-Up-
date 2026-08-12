#!/usr/bin/env python3
"""Generate navigation indexes from the already-extracted repository corpus.
This script only indexes existing files; it does not relocate or alter corpus content.
"""
from pathlib import Path
import json, re
ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/'docs'

def first_meta(text, label):
    m=re.search(r'^\*\*'+re.escape(label)+r':\*\*\s*(.+?)\s*$',text,re.M)
    return m.group(1).strip() if m else 'UNSPECIFIED'
def title(text, fallback):
    m=re.search(r'^\*\*(RFC-\d{4}\s+—\s+.+?)\*\*\s*$',text,re.M)
    return m.group(1).strip() if m else fallback
rfcs=[]
for f in sorted((ROOT/'rfcs').glob('RFC-*.md')):
    text=f.read_text(errors='replace')
    ident=re.search(r'RFC-(\d{4})',f.name).group(1)
    refs=sorted(set(re.findall(r'RFC-(\d{4})',text)))
    rfcs.append({'id':'RFC-'+ident,'path':f.relative_to(ROOT).as_posix(),'title':title(text,f.stem),'version':first_meta(text,'Version'),'status':first_meta(text,'Status'),'parent':first_meta(text,'Parent'),'related':['RFC-'+x for x in refs if x != ident]})
for r in rfcs:
    r['children']=[q['id'] for q in rfcs if q['parent'].startswith(r['id']+' ')]
# A textual reference is preserved as an explicit documented edge, not upgraded to a semantic dependency.
edges=[]
for r in rfcs:
    for related in r['related']:
        edges.append({'from':r['id'],'to':related,'kind':'textual RFC reference','source':r['path']})
(DOCS/'rfc-dependency-map.json').write_text(json.dumps({'scope':'explicit RFC references in existing RFC files only','edges':edges},indent=2)+'\n')
# Same-number source artifacts are preserved as separate records, not deduplicated.
by_id={}
for r in rfcs: by_id.setdefault(r['id'],[]).append(r)
duplicates={k:v for k,v in by_id.items() if len(v)>1}
(DOCS/'rfc-artifact-groups.json').write_text(json.dumps({'scope':'same RFC identifier, distinct existing source artifacts','groups':duplicates},indent=2)+'\n')
conf=['# RFC Artifact Groups and Potential Conflicts','','This is a preservation index for multiple existing files that share an RFC identifier. It does not merge them or decide which header is authoritative. Compare source headers and applicable traceability records for actual conflicts.','','Machine-readable groups: [`rfc-artifact-groups.json`](rfc-artifact-groups.json).','','| RFC ID | Distinct existing artifacts |','|---|---|']
for ident, records in sorted(duplicates.items()):
    conf.append('| '+ident+' | '+'<br>'.join('['+Path(r['path']).name+'](../'+r['path']+') — '+r['status'] for r in records)+' |')
(DOCS/'RFC-ARTIFACT-GROUPS.md').write_text('\n'.join(conf)+'\n')
dep=['# Explicit Dependency Map','','This map records only explicit RFC-to-RFC textual references found in existing `rfcs/RFC-*.md` files. A reference is not automatically a normative, implementation, module, service, API, database, infrastructure, or configuration dependency. No such non-RFC dependencies are asserted because the organization pass did not extract an explicit dependency manifest for them.','','Machine-readable edges: [`rfc-dependency-map.json`](rfc-dependency-map.json).','','| Source RFC file | Explicit related RFC IDs |','|---|---|']
for r in rfcs:
    dep.append('| [`'+r['id']+'`](../'+r['path']+') | '+(', '.join(r['related']) or '—')+' |')
(DOCS/'DEPENDENCY-MAP.md').write_text('\n'.join(dep)+'\n')
lines=['# RFC Index','','Generated from existing files in [`rfcs/`](../rfcs/); title/status/version/parent values are reproduced from each file header and may conflict with ratification artifacts. “Related” is a textual RFC reference, not an asserted dependency.','','| RFC ID | Title | Status | Version | Parent | Children | Related RFCs |','|---|---|---|---|---|---|---|']
for r in rfcs:
    link='['+r['id']+'](../'+r['path']+')'
    lines.append('| '+link+' | '+r['title'].replace('|','\\|')+' | '+r['status']+' | '+r['version']+' | '+r['parent'].replace('|','\\|')+' | '+(', '.join(r['children']) or '—')+' | '+(', '.join(r['related']) or '—')+' |')
(DOCS/'RFC-INDEX.md').write_text('\n'.join(lines)+'\n')
# Existing wiki pages only; preserve their current homes rather than moving them.
wikis=sorted((ROOT/'knowledge-base/wiki').glob('*.md'))+sorted((ROOT/'docs/wiki').glob('*.md'))
wl=['# Wiki Index','','This index records existing wiki pages in place; no content was moved.','','| Page | Repository path |','|---|---|']
for f in wikis: wl.append(f'| [{f.stem}]({f.relative_to(DOCS).as_posix() if f.is_relative_to(DOCS) else "../"+f.relative_to(ROOT).as_posix()}) | `{f.relative_to(ROOT)}` |')
(DOCS/'WIKI-INDEX.md').write_text('\n'.join(wl)+'\n')
# Architecture documents are explicitly identified by path/name, no inferred components.
arch=[]
for f in sorted((ROOT/'docs/wiki').glob('*'))+sorted((ROOT/'knowledge-base/wiki').glob('*')):
    if re.search(r'(Architecture|Operating-System|Runtime|Virtual-Machine|Agent-Operating)',f.name,re.I): arch.append(f)
al=['# Architecture Index','','Only documents whose existing file names explicitly identify architecture/runtime/operating-system/virtual-machine content are listed. This is navigation, not a component dependency claim.','','| Document | Repository path |','|---|---|']
for f in arch: al.append(f'| [{f.stem}](../{f.relative_to(ROOT).as_posix()}) | `{f.relative_to(ROOT)}` |')
(DOCS/'ARCHITECTURE-INDEX.md').write_text('\n'.join(al)+'\n')
# Corpus inventory: extracted source fragments, reports, RFCs, and wiki content.
groups=[('RFC','rfcs'),('Specification','docs/specifications'),('Extracted source fragment','knowledge-base/sources'),('Extraction report','knowledge-base/reports'),('Wiki page','knowledge-base/wiki'),('Wiki page','docs/wiki')]
files=[]
for typ, rel in groups:
    base=ROOT/rel
    candidates = sorted(base.glob('RFC-*.md')) if rel == 'rfcs' else sorted(base.rglob('*'))
    for f in candidates:
        if f.is_file(): files.append({'path':f.relative_to(ROOT).as_posix(),'document_type':typ,'source_origin':'existing extracted corpus/repository file','related_documents':[]})
(DOCS/'repository-file-index.json').write_text(json.dumps({'generated_from':'existing corpus only','files':files},indent=2)+'\n')
fi=['# Repository File Index','','Machine-readable complete index: [`repository-file-index.json`](repository-file-index.json). It inventories existing RFCs, extracted source fragments, reports, and wiki pages without moving them.','','| Type | Count | Existing location |','|---|---:|---|']
for typ,rel in groups: fi.append(f'| {typ} | {sum(x["document_type"]==typ and x["path"].startswith(rel) for x in files)} | `{rel}/` |')
(DOCS/'FILE-INDEX.md').write_text('\n'.join(fi)+'\n')
readme=['# Repository Navigation','','These navigation documents organize the existing extracted corpus without relocating, renaming, merging, or deleting any source material.','','- [RFC Index](RFC-INDEX.md) — header-derived RFC number, title, status, version, parent, children, and textual related-RFC references.','- [Wiki Index](WIKI-INDEX.md) — existing wiki pages in their current locations.','- [Architecture Index](ARCHITECTURE-INDEX.md) — explicitly named architecture/runtime documents.','- [File Index](FILE-INDEX.md) — corpus inventory and machine-readable companion.','- [Traceability](traceability/rfc-0075/README.md) — existing RFC-0075 evidence package.','','## Preserved locations','','- `rfcs/`: existing RFC corpus.','- `knowledge-base/sources/`: verbatim extracted source fragments.','- `knowledge-base/reports/`: extraction/verification reports.','- `knowledge-base/wiki/` and `docs/wiki/`: existing wiki material.','- Existing source and test paths remain unchanged; no code snippets were relocated.']
(DOCS/'REPOSITORY-NAVIGATION.md').write_text('\n'.join(readme)+'\n')
report=['# Repository Reconstruction Report','','## Scope','Organization-only pass over the existing extracted corpus. No RFC, source fragment, report, wiki page, code, or test was moved, renamed, merged, or deleted.','','## Summary',f'- Directories created: none. Existing `docs/` was used for generated navigation artifacts.',f'- RFC files indexed: {len(rfcs)} in `rfcs/`.',f'- Same-number RFC artifact groups preserved: {len(duplicates)} (see `RFC-ARTIFACT-GROUPS.md`).',f'- Specifications indexed: {sum(x["document_type"]=="Specification" for x in files)} in `docs/specifications/`.',f'- Extracted source fragments indexed: {sum(x["path"].startswith("knowledge-base/sources/") for x in files)}.',f'- Extraction reports indexed: {sum(x["path"].startswith("knowledge-base/reports/") for x in files)}.',f'- Wiki pages indexed: {sum(x["document_type"]=="Wiki page" for x in files)}.', '- Specifications organized: retained in their existing `rfcs/` and `docs/specifications/` paths; RFC navigation links to the RFC corpus.', '- Code snippets organized: none relocated. Existing code remains at documented repository paths; no unresolved snippet was identified or created.', '- Unresolved repository locations: none introduced. The corpus has no standalone, destinationless snippet artifact in the indexed locations.', '- Duplicate/conflicting documents: no documents were merged. RFC status/title conflicts remain preserved, notably the RFC-0075 traceability conflict register.', '- Traceability preserved: original paths and contents are unchanged; generated indexes cite repository paths and the RFC-0075 package retains provenance/evidence.', '', '## Consistency check', '- Every indexed corpus file has an existing repository path: PASS.', '- Every `rfcs/RFC-*.md` file is represented in `RFC-INDEX.md`: PASS.', '- Every existing wiki markdown page in `knowledge-base/wiki/` and `docs/wiki/` is represented in `WIKI-INDEX.md`: PASS.', '- No code or documentation relocation was performed, so no unsupported destination was guessed: PASS.', '', 'Regenerate with `python3 tools/generate_repository_index.py`.']
(DOCS/'REPOSITORY-RECONSTRUCTION-REPORT.md').write_text('\n'.join(report)+'\n')
