"""Run the complete unittest suite and expose failures as CI annotations."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def annotation(value: str) -> str:
    return value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def main() -> None:
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        for test, traceback in result.errors + result.failures:
            message = annotation(f'{test.id()}\n{traceback}')
            print(f'::error title=Python test failure::{message}', flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
