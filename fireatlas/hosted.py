"""Render entry point: authentic bootstrap and one ASGI worker.

The free deployment uses ephemeral /tmp storage. Native exports are the backup.
"""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def public_origin(environ):
    value=(environ.get('FIREATLAS_PUBLIC_ORIGIN') or environ.get('RENDER_EXTERNAL_URL') or '').rstrip('/')
    if any(c.isspace() or ord(c)<32 for c in value):
        raise ValueError('Public origin must not contain whitespace or control characters.')
    parsed=urlsplit(value)
    local=parsed.hostname in {'localhost','127.0.0.1','::1'}
    if (parsed.scheme not in ({'http','https'} if local else {'https'}) or not parsed.hostname
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise ValueError('Set FIREATLAS_PUBLIC_ORIGIN to the application HTTPS origin (or use Render\'s RENDER_EXTERNAL_URL).')
    # Validate malformed ports before opening stores or a listener.
    parsed.port
    return value


def prepare_database(root):
    """Only new hosted stores receive the bundled authentic source samples."""
    from .core import connect
    from .bootstrap import populate_showcase
    from .archive import import_bundle
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    database=root/'fireatlas.sqlite3';pending=root/'.authentic-bootstrap-pending'
    if not database.exists():pending.touch()
    if database.exists():
        with connect(database) as db:
            if db.execute('SELECT 1 FROM batches WHERE demo=1 LIMIT 1').fetchone():
                raise ValueError('Refusing to serve synthetic observations as an authentic hosted archive.')
    if pending.exists():
        # Publish only a complete bootstrap. A killed/failed import must not
        # cause populate_showcase's existing-batch guard to skip remaining years.
        with tempfile.TemporaryDirectory(dir=root,prefix='.bootstrap-') as temporary:
            staged=Path(temporary)/'fireatlas.sqlite3'
            populate_showcase(staged)
            import_bundle(staged)
            staged.replace(database)
        pending.unlink()
    return database


def create_hosted_app(environ=None):
    env=os.environ if environ is None else environ
    origin=public_origin(env)
    database=prepare_database(env.get('FIREATLAS_DATA_DIR','/tmp/fireatlas'))
    # One authoritative application origin; never trust a client Host header.
    os.environ['FIREATLAS_ASSISTANT_ORIGIN']=origin
    os.environ['FIREATLAS_STUDIO_ORIGIN']=origin
    from .assistant.gateway import create_app
    return create_app(database,origin)


def main():
    import uvicorn
    port=int(os.environ.get('PORT','10000'))
    if not 1<=port<=65535:raise ValueError('PORT must be between 1 and 65535.')
    uvicorn.run(create_hosted_app(),host='0.0.0.0',port=port,workers=1,limit_concurrency=32,timeout_keep_alive=5)


if __name__=='__main__':main()
