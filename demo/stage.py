#!/usr/bin/env python3
"""Create a generic assistant workspace or compare it with the starter templates."""
import argparse
import hashlib
from pathlib import Path
import shutil

KIT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def templates():
    return {
        Path('PROJECT.md'): KIT / 'PROJECT.md',
        **{Path(p.name.removesuffix('.example')): p
           for p in (KIT / 'context').glob('*.md.example')},
    }


def verify(workspace):
    expected = templates()
    failures = []
    for relative, original in expected.items():
        actual = workspace / relative
        if actual.is_symlink() or not actual.is_file() or digest(actual) != digest(original):
            failures.append(str(relative))
    if failures:
        raise SystemExit('Files missing or different from the starter templates: ' + ', '.join(failures))
    print(f'Verified {len(expected)} starter context files. Generated deliverables are not checked.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('init', 'verify'))
    parser.add_argument('workspace', type=Path)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    if args.action == 'init':
        if workspace.exists() and (not workspace.is_dir() or any(workspace.iterdir())):
            raise SystemExit('Refusing a nonempty destination. Choose an empty workspace.')
        workspace.mkdir(parents=True, exist_ok=True)
        for relative, source in templates().items():
            shutil.copy2(source, workspace / relative)
        (workspace / 'output').mkdir()
        print(f'Created assistant workspace at {workspace}. Fill in the bracketed placeholders before use.')
    else:
        verify(workspace)


if __name__ == '__main__':
    main()
