"""Private immutable PDF source bytes for the Investigation whiteboard.

Rendering and structural parsing belong to the client PDF reader. A file with a
PDF signature is stored as opaque bytes and must still be parsed before display.
"""
import hashlib
import os
import re
import secrets
import shutil
import select
import subprocess
import tempfile
import time

from .errors import LimitExceeded, NotFound, StudioError

MAX_BYTES = 10 * 1024 * 1024
MAX_BOARD_BYTES = 50 * 1024 * 1024


def validate(name, data):
    if not isinstance(name, str) or not name.strip() or len(name) > 200 or any(ord(c) < 32 for c in name):
        raise StudioError('Choose a valid document name.', code='invalid-document')
    if not isinstance(data, bytes) or not data or len(data) > MAX_BYTES:
        raise LimitExceeded('Choose a PDF up to 10 MiB.', code='document-limit')
    if not data.startswith(b'%PDF-'):
        raise StudioError('Choose a PDF document.', code='invalid-document')


def add(store, principal, document_id, name, data):
    validate(name, data)
    checksum = hashlib.sha256(data).hexdigest()
    with store.connection(write=True) as db:
        store.require(db, principal, document_id, 'editor')
        existing = db.execute('SELECT id,name FROM source_documents WHERE document_id=? AND sha256=?', (document_id, checksum)).fetchone()
        if existing:
            return {'id': existing['id'], 'name': existing['name'], 'sha256': checksum, 'bytes': len(data), 'existing': True}
        used = db.execute('SELECT COALESCE(SUM(length(content)),0) FROM source_documents WHERE document_id=?', (document_id,)).fetchone()[0]
        if used + len(data) > MAX_BOARD_BYTES:
            raise LimitExceeded('This board exceeds its 50 MiB document limit.', code='document-limit')
        identifier = 'source_' + secrets.token_urlsafe(12)
        db.execute('INSERT INTO source_documents VALUES(?,?,?,?,?,?,?)', (identifier, document_id, principal, name.strip(), checksum, data, store.clock()))
    return {'id': identifier, 'name': name.strip(), 'sha256': checksum, 'bytes': len(data), 'existing': False}


def read(store, principal, document_id, identifier):
    with store.connection() as db:
        store.require(db, principal, document_id)
        row = db.execute('SELECT * FROM source_documents WHERE document_id=? AND id=?', (document_id, identifier)).fetchone()
        if not row:
            raise NotFound('Document not found.')
        data = bytes(row['content'])
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise StudioError('Stored document integrity check failed.', code='document-corrupt')
        return {'id': row['id'], 'name': row['name'], 'sha256': row['sha256'], 'bytes': len(data)}, data


def list_documents(store, principal, document_id):
    with store.connection() as db:
        store.require(db, principal, document_id)
        return [dict(row) for row in db.execute('SELECT id,name,sha256,length(content) AS bytes FROM source_documents WHERE document_id=? ORDER BY created,id', (document_id,))]


def page_count(data):
    """Return a verified PDF page count, or None if it cannot be read."""
    executable = shutil.which('pdfinfo')
    if not executable:
        return None
    try:
        with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as output:
            source.write(data); source.seek(0)
            process = subprocess.run([executable, '-'], stdin=source, stdout=output,
                                     stderr=subprocess.DEVNULL, timeout=10, check=False)
            if process.returncode:
                return None
            output.seek(0)
            match = re.search(rb'^Pages:\s*([0-9]+)\s*$', output.read(65536), re.MULTILINE)
            count = int(match.group(1)) if match else 0
            return count if count > 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def extract_page(data, page):
    """Extract one bounded page locally; PDF text is untrusted source material."""
    if type(page) is not int or not 1 <= page <= 20:
        raise StudioError('Choose a page between 1 and 20.', code='invalid-document')
    executable = shutil.which('pdftotext')
    if not executable:
        raise StudioError('PDF text extraction is not available on this server.', code='document-reader-unavailable')
    try:
        with tempfile.TemporaryFile() as source:
            source.write(data);source.seek(0)
            process=subprocess.Popen([executable,'-f',str(page),'-l',str(page),'-enc','UTF-8','-','-'],
                                     stdin=source,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            raw=bytearray();deadline=time.monotonic()+10
            try:
                while len(raw)<=12000:
                    remaining=deadline-time.monotonic()
                    if remaining<=0 or not select.select([process.stdout],[],[],remaining)[0]:raise subprocess.TimeoutExpired(executable,10)
                    chunk=os.read(process.stdout.fileno(),min(4096,12001-len(raw)))
                    if not chunk:break
                    raw.extend(chunk)
                if len(raw)>12000:process.kill()
                if process.wait(timeout=max(0.01,deadline-time.monotonic())) and len(raw)<=12000:
                    raise StudioError('This document page could not be read.',code='invalid-document')
            finally:
                if process.poll() is None:process.kill();process.wait()
                process.stdout.close()
    except subprocess.TimeoutExpired:
        raise StudioError('Reading this PDF page took too long.', code='document-reader-unavailable') from None
    text=bytes(raw[:12000]).decode('utf-8',errors='replace').strip()
    return {'text':text, 'truncated':len(raw)>12000}
