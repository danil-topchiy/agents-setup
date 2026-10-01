#!/usr/bin/env python3
"""Export reviewed tracked files with fresh OpenClaw defaults and no Git history."""
import argparse
import json
from pathlib import Path
import shutil
import sys

from check_publication import PROJECT, git, known_private, private_path, scan_files
from native import starter_config


def export(destination, project=PROJECT):
    project = Path(project).resolve()
    destination = Path(destination).expanduser().absolute()
    if destination.is_symlink() or destination.exists():
        raise ValueError("Choose a new destination; existing files will not be overwritten.")
    paths = [p.decode() for p in git(project, "ls-files", "-z").split(b"\0") if p]
    paths = [p for p in paths if (project / p).exists()]
    if any(private_path(p) for p in paths):
        raise ValueError("A private path is tracked; run the publication check before exporting.")
    private = known_private(project)
    review_paths = [p for p in paths if p != "config/openclaw.json"]
    if scan_files(project, review_paths, private):
        raise ValueError("Publication scan failed; run scripts/check_publication.py for locations.")
    destination.mkdir(parents=True, mode=0o755)
    try:
        for path in review_paths:
            target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(project / path, target)
        config = destination / "config/openclaw.json"
        config.write_text(json.dumps(starter_config(project), indent=2) + "\n")
        copied = [str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file()]
        if scan_files(destination, copied, private):
            raise ValueError("Export did not pass the publication scan.")
    except BaseException:
        shutil.rmtree(destination)
        raise
    print(f"Public starter exported to {destination}")
    print("No Git history, credentials, accounts, or enabled messaging channels were copied.")
    print("Initialize fresh Git history with the public author identity you intend to share.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        export(args.destination)
    except (OSError, ValueError) as error:
        sys.exit(f"Stopped: {error}")
