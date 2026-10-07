"""Run a Python check and expose its traceback in public CI annotations."""
from __future__ import annotations

import os
from pathlib import Path
import runpy
import sys
import traceback


def main() -> None:
    script = Path(sys.argv[1]).resolve()
    sys.argv = sys.argv[1:]
    sys.path.insert(0, str(script.parent))
    try:
        runpy.run_path(str(script), run_name='__main__')
    except BaseException as error:
        if isinstance(error, SystemExit) and error.code in (None, 0):
            return
        if os.environ.get('GITHUB_ACTIONS') == 'true':
            message = traceback.format_exc().replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
            print(f'::error title={script.name} failed::{message}', flush=True)
        raise


if __name__ == '__main__':
    main()
