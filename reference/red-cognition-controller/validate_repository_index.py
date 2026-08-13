#!/usr/bin/env python3
"""Validate generated repository-navigation artifacts against existing corpus paths."""
from pathlib import Path
import json, re, sys
ROOT=Path(__file__).resolve().parents[1]; DOCS=ROOT/'docs'
errors=[]
try:
    inventory=json.loads((DOCS/'repository-file-index.json').read_text()).get('files',[])
except Exception as exc:
    inventory=[]; errors.append(f'cannot read file index: {exc}')
indexed={x.get('path') for x in inventory}
# The corpus scope intentionally includes RFC source artifacts, not this directory's generated README.
expected={f.relative_to(ROOT).as_posix() for f in (ROOT/'rfcs').glob('RFC-*.md')}
for rel in ('docs/specifications','knowledge-base/sources','knowledge-base/reports','knowledge-base/wiki','docs/wiki'):
    expected|={f.relative_to(ROOT).as_posix() for f in (ROOT/rel).rglob('*') if f.is_file()}
missing=sorted(expected-indexed); stale=sorted(indexed-expected)
if missing: errors.append(f'indexed corpus files missing: {len(missing)}')
if stale: errors.append(f'stale indexed corpus files: {len(stale)}')
rfc_text=(DOCS/'RFC-INDEX.md').read_text() if (DOCS/'RFC-INDEX.md').is_file() else ''
rfc_files=sorted((ROOT/'rfcs').glob('RFC-*.md'))
rfc_ids={re.search(r'RFC-(\d{4})',f.name).group(0) for f in rfc_files}
missing_rfcs=sorted(f.name for f in rfc_files if f'](../rfcs/{f.name})' not in rfc_text)
if missing_rfcs: errors.append(f'RFC index omissions: {", ".join(missing_rfcs)}')
wiki_text=(DOCS/'WIKI-INDEX.md').read_text() if (DOCS/'WIKI-INDEX.md').is_file() else ''
wiki_paths=[f.relative_to(ROOT).as_posix() for base in ('knowledge-base/wiki','docs/wiki') for f in (ROOT/base).glob('*.md')]
missing_wikis=sorted(x for x in wiki_paths if f'`{x}`' not in wiki_text)
if missing_wikis: errors.append(f'wiki index omissions: {len(missing_wikis)}')
# Dependency navigation may list only references that occur in an indexed RFC artifact.
try:
    dependency_edges=json.loads((DOCS/'rfc-dependency-map.json').read_text()).get('edges',[])
except Exception as exc:
    dependency_edges=[]; errors.append(f'cannot read dependency map: {exc}')
rfc_paths={f.relative_to(ROOT).as_posix() for f in rfc_files}
for edge in dependency_edges:
    if edge.get('source') not in rfc_paths: errors.append(f"dependency edge has unknown source: {edge.get('source')}")
    if edge.get('kind') != 'textual RFC reference': errors.append('dependency edge has unsupported inferred kind')
try:
    artifact_groups=json.loads((DOCS/'rfc-artifact-groups.json').read_text()).get('groups',{})
except Exception as exc:
    artifact_groups={}; errors.append(f'cannot read RFC artifact groups: {exc}')
actual_groups={}
for f in rfc_files:
    ident=re.search(r'RFC-(\d{4})',f.name).group(0)
    actual_groups.setdefault(ident,[]).append(f.relative_to(ROOT).as_posix())
actual_groups={k:v for k,v in actual_groups.items() if len(v)>1}
if set(artifact_groups) != set(actual_groups): errors.append('RFC artifact group identifier mismatch')
for ident, paths in actual_groups.items():
    listed={x.get('path') for x in artifact_groups.get(ident,[])}
    if listed != set(paths): errors.append(f'RFC artifact group paths mismatch: {ident}')
result={'indexed_files':len(indexed),'expected_files':len(expected),'missing_files':missing,'stale_files':stale,'rfc_files':len(rfc_files),'unique_rfc_ids':len(rfc_ids),'missing_rfcs':missing_rfcs,'wiki_pages':len(wiki_paths),'missing_wiki_pages':missing_wikis,'dependency_edges':len(dependency_edges),'rfc_artifact_groups':len(artifact_groups),'result':'PASS' if not errors else 'FAIL','errors':errors}
(DOCS/'repository-index-validation.json').write_text(json.dumps(result,indent=2)+'\n')
print('REPOSITORY INDEX VALIDATION\n===========================')
for k in ('indexed_files','expected_files','rfc_files','unique_rfc_ids','wiki_pages','dependency_edges','rfc_artifact_groups'): print(f'{k.replace("_"," ").title()+":":<24} {result[k]}')
print('RESULT:',result['result'])
for error in errors: print('ERROR:',error)
sys.exit(0 if not errors else 1)
