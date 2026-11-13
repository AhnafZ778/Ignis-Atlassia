"""Validate bounded, descriptive diagram plans against retrieved evidence IDs."""
import re

from pydantic_ai import ModelRetry


def table_source_label(name, columns):
    """Describe a table from its own metadata without inventing values or units."""
    def short(value, limit):
        clean = ' '.join(str(value).split())
        return clean if len(clean) <= limit else clean[:limit-1] + '…'
    title = short(name, 55) if isinstance(name, str) and name.strip() else 'Selected table'
    fields = [short(c, 32) for c in columns if isinstance(c, str) and c.strip()] if isinstance(columns, list) else []
    return title + ('\nFields: ' + ' · '.join(fields[:3]) + (' · …' if len(fields) > 3 else '') if fields else '')


def coalesce_diagram_nodes(diagram):
    """Merge identical source and interpretation nodes while retaining connections."""
    sources, aliases, nodes = {}, {}, []
    for node in diagram['nodes']:
        key = ('evidence', node.get('evidence_id')) if node['kind'] == 'evidence' and node.get('evidence_id') else ('interpretation', node['label']) if node['kind'] == 'interpretation' else None
        if key and key in sources:
            aliases[node['id']] = sources[key]
        else:
            if key:
                sources[key] = node['id']
            nodes.append(node)
    seen, edges = set(), []
    for edge in diagram['edges']:
        source, target = aliases.get(edge['source'], edge['source']), aliases.get(edge['target'], edge['target'])
        key = (source, target, edge['relation'])
        if source != target and key not in seen:
            edges.append({**edge, 'source': source, 'target': target})
            seen.add(key)
    return {**diagram, 'nodes': nodes, 'edges': edges}


def fallback_evidence_diagram(evidence_id, interpretation, *, table=False, allow_interpretation_numbers=False):
    """Connect a source to a safe full interpretation, or to an open question."""
    source = {'id':'source', 'kind':'evidence', 'label':'Selected table' if table else 'Saved evidence', 'evidence_id':evidence_id}
    if interpretation and interpretation.strip():
        text=interpretation.strip()
        candidate={'nodes':[source, {'id':'interpretation','kind':'interpretation','label':text,'evidence_id':None}],
                   'edges':[{'source':'source','target':'interpretation','relation':'context'}]}
        try:
            return validate_diagram(candidate,{evidence_id},text,allow_interpretation_numbers=allow_interpretation_numbers)
        except ModelRetry:
            pass
    return {'nodes':[source, {'id':'question','kind':'question','label':'What does this table support?' if table else 'What does this evidence support?', 'evidence_id':None}],
            'edges':[{'source':'source','target':'question','relation':'question'}]}


def validate_diagram(diagram, evidence_ids, interpretation='', *, allow_interpretation_numbers=False):
    nodes = diagram['nodes']
    ids = [node['id'] for node in nodes]
    if not 1 <= len(nodes) <= 6 or len(set(ids)) != len(ids):
        raise ModelRetry('Use one to six uniquely named diagram nodes.')
    for node in nodes:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,31}', node['id']):
            raise ModelRetry('Use simple unique node identifiers.')
        label_without_platforms=re.sub(r'\bNOAA[- ]?(?:20|21)\b','satellite',node['label'],flags=re.I)
        number_invalid=bool(re.search(r'\d',label_without_platforms)) and not (allow_interpretation_numbers and node['kind']=='interpretation' and node['label']==interpretation)
        if not node['label'].strip() or number_invalid or re.search(r'\b(caus\w*|prov\w*|confirm\w*|predict\w*|forecast\w*|extinguish\w*)\b', node['label'], re.I):
            raise ModelRetry('Use brief descriptive diagram labels without numbers, causal claims or forecasts. Put measurements in checked claims.')
        if node['kind'] == 'context' and len(node['label']) > 120:
            raise ModelRetry('Keep context node labels under 120 characters.')
        if node.get('evidence_id') and node['evidence_id'] not in evidence_ids:
            raise ModelRetry('Use only an exact retrieved evidence ID in a diagram node.')
        if node['kind'] == 'evidence' and not node.get('evidence_id'):
            raise ModelRetry('Every evidence node needs a retrieved evidence ID.')
        if node['kind'] != 'evidence' and node.get('evidence_id'):
            raise ModelRetry('Only evidence nodes can carry an evidence ID.')
        if node['kind'] == 'question' and not node['label'].rstrip().endswith('?'):
            raise ModelRetry('Question nodes must be phrased as questions.')
        if node['kind'] == 'interpretation' and node['label'] != interpretation:
            raise ModelRetry('Interpretation nodes must repeat the checked answer interpretation exactly.')
    edges = diagram['edges']
    if len(edges) > 8 or any(e['source'] not in ids or e['target'] not in ids or e['source'] == e['target'] or e['relation'] not in ('context','question') for e in edges):
        raise ModelRetry('Diagram connections must link distinct existing nodes, with at most eight edges.')
    return diagram
