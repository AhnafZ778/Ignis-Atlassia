"""Bounded, resumable literal search of an investigation's private sources."""
import base64
import csv
import hashlib
import io
import json
import re
import time

from . import datasets, source_documents
from .errors import StudioError


def search(store, principal, document_id, query, cancelled=lambda: False, deadline=None, cursor=None):
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 100:
        raise StudioError('Search for 2 to 100 characters.')
    query = query.strip()
    needle = re.compile(re.escape(query), re.IGNORECASE)
    tables = datasets.list_datasets(store, principal, document_id)
    documents = source_documents.list_documents(store, principal, document_id)
    sources = [('csv', item) for item in tables] + [('pdf', item) for item in documents]
    identity = hashlib.sha256(json.dumps([document_id, query, [(kind, item['id'], item['sha256']) for kind, item in sources]], separators=(',', ':')).encode()).hexdigest()
    state = {'version': 1, 'identity': identity, 'source': 0, 'row': 0, 'column': 0, 'page': 1}
    if cursor is not None:
        try:
            if not isinstance(cursor, str) or len(cursor) > 1000:
                raise ValueError()
            state = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            if (not isinstance(state, dict) or state.get('version') != 1 or state.get('identity') != identity
                    or any(type(state.get(key)) is not int for key in ('source', 'row', 'column', 'page'))
                    or not 0 <= state['source'] <= len(sources) or not 0 <= state['row'] <= 50000
                    or not 0 <= state['column'] <= 100 or not 1 <= state['page'] <= 20):
                raise ValueError()
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            raise StudioError('Search sources changed or the continuation is invalid. Start a new search.') from None
    matches, problems = [], []
    scanned_tables = scanned_pages = visited = 0
    stopped = False

    def check():
        if cancelled() or (deadline is not None and time.monotonic() >= deadline):
            raise InterruptedError('Investigation stopped.')

    def excerpt(text, match):
        return text[max(0, match.start() - 180):min(len(text), match.end() + 180)]

    def next_source():
        state.update(source=state['source'] + 1, row=0, column=0, page=1)

    # Each call has bounded work. The opaque continuation retains the exact
    # source, row/column and page and is invalidated when membership changes.
    while state['source'] < len(sources) and visited < 4 and scanned_pages < 12 and len(matches) < 8:
        check()
        kind, source = sources[state['source']]
        visited += 1
        if kind == 'csv':
            info, data = datasets.read(store, principal, document_id, source['id'])
            reader = csv.reader(io.StringIO(data.decode('utf-8-sig'), newline=''), strict=True)
            columns = next(reader)
            scanned_tables += 1
            start_row, start_column = state['row'], state['column']
            for row_index, row in enumerate(reader):
                if row_index % 500 == 0:
                    check()
                if row_index < start_row:
                    continue
                for column_index, (column, value) in enumerate(zip(columns, row)):
                    if row_index == start_row and column_index < start_column:
                        continue
                    hit = needle.search(value)
                    if hit:
                        matches.append({'kind': 'csv', 'name': info['name'], 'source_id': info['id'],
                            'source_sha256': info['sha256'], 'row_offset': row_index, 'column': column, 'excerpt': excerpt(value, hit)})
                        if len(matches) == 8:
                            state.update(row=row_index, column=column_index + 1)
                            stopped = True
                            break
                if stopped:
                    break
            if not stopped:
                next_source()
        else:
            info, data = source_documents.read(store, principal, document_id, source['id'])
            count = source_documents.page_count(data)
            last_page = min(count, 20) if count is not None else 20
            if state['page'] > last_page:
                next_source()
                continue
            while state['page'] <= last_page and scanned_pages < 12 and len(matches) < 8:
                check()
                page = state['page']
                try:
                    extracted = source_documents.extract_page(data, page)
                except StudioError:
                    problems.append({'name': info['name'], 'page': page, 'reason': 'Page unavailable or unreadable'})
                    next_source()
                    break
                scanned_pages += 1
                if extracted['truncated']:
                    problems.append({'name': info['name'], 'page': page, 'reason': 'Only the extracted page prefix was searched'})
                text = extracted['text']
                hit = needle.search(text)
                if hit:
                    matches.append({'kind': 'pdf', 'name': info['name'], 'source_id': info['id'],
                        'source_sha256': info['sha256'], 'page': page, 'excerpt': excerpt(text, hit), 'page_truncated': extracted['truncated']})
                if page == last_page:
                    if count is not None and count > 20:
                        problems.append({'name': info['name'], 'page': 21, 'reason': 'Pages beyond the first 20 were not searched'})
                    next_source()
                    break
                state['page'] += 1
    continuation = base64.urlsafe_b64encode(json.dumps(state, separators=(',', ':')).encode()).decode() if state['source'] < len(sources) else None
    return {'query': query, 'matches': matches, 'scanned_tables': scanned_tables, 'available_tables': len(tables),
        'scanned_pages': scanned_pages, 'available_documents': len(documents), 'document_page_limit': 20,
        'source_limit': 4, 'stopped_at_match_limit': len(matches) >= 8, 'next_cursor': continuation, 'unavailable': problems,
        'note': 'Literal text search. Continue with next_cursor to scan further; extracted PDF text may be incomplete. No match does not establish absence.'}
