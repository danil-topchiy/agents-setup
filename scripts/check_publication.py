#!/usr/bin/env python3
"""Scan publication files and optional Git history without echoing private values."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from check_config_privacy import EMAIL, find_issues, private_values

PROJECT = Path(__file__).resolve().parent.parent
EXAMPLE_DOMAINS = {"example.com", "example.org", "example.net", "example.invalid"}
TOKEN = re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9_-]{32,}|\d{8,12}:[A-Za-z0-9_-]{30,})")
KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
HOST_PATH = re.compile(r"/" + r"Users/(?!YOUR_USER\b|USERNAME\b)[^/\s\"']+")


def git(project, *args):
    return subprocess.check_output(["git", "-C", str(project), *args], stderr=subprocess.DEVNULL)


def known_private(project):
    values = set(private_values(project))
    try:
        authors = git(project, "log", "--all", "--format=%an%x00%ae%n%cn%x00%ce").decode().splitlines()
    except subprocess.CalledProcessError:
        authors = []
    for record in authors:
        name, email = record.split("\0", 1)
        if not email.endswith(("@example.invalid", "@users.noreply.github.com")):
            values.update(value for value in (name, email) if len(value) >= 8)
    return values


def private_path(path):
    parts = Path(path).parts
    name = Path(path).name
    return (any(p in {".git", ".local", ".openclaw", ".hermes", "output", "memory"} for p in parts)
            or (name.startswith(".env") and name != ".env.example")
            or ".private." in name
            or name.endswith((".pem", ".key", ".db", ".sqlite", ".sqlite3", ".log")))


def inspect_text(path, text, private):
    issues = []
    if private_path(path):
        issues.append("private runtime file")
    if KEY.search(text) or TOKEN.search(text):
        issues.append("credential-shaped value")
    if HOST_PATH.search(text):
        issues.append("personal host path")
    if any(value.casefold() in text.casefold() for value in private if len(value) >= 8):
        issues.append("known private value or author identity")
    for match in EMAIL.finditer(text):
        value = match.group()
        domain = value.rsplit("@", 1)[1].lower()
        public_author = path == "commit metadata" and domain == "users.noreply.github.com"
        if domain not in EXAMPLE_DOMAINS and not value.startswith("YOUR_") and not public_author:
            issues.append("non-example email address")
            break
    if path == "config/openclaw.json":
        try:
            issues.extend(find_issues(text, private))
        except ValueError:
            issues.append("invalid OpenClaw JSON")
    return sorted(set(issues))


def scan_files(project, paths, private):
    findings = []
    for path in paths:
        source = project / path
        if source.is_symlink():
            findings.append((path, ["symbolic link requires manual review"]))
        elif source.is_file():
            try:
                issues = inspect_text(path, source.read_text(), private)
            except UnicodeError:
                issues = ["binary file requires manual review"]
            if issues:
                findings.append((path, issues))
    return findings


def history_findings(project, private):
    findings = []
    commits = git(project, "rev-list", "--all").decode().splitlines()
    seen = set()
    for commit in commits:
        for record in git(project, "ls-tree", "-rz", commit).split(b"\0"):
            if not record:
                continue
            metadata, path = record.split(b"\t", 1)
            _, kind, oid = metadata.split()
            if kind != b"blob" or (oid, path) in seen:
                continue
            seen.add((oid, path))
            issues = inspect_text(path.decode(), git(project, "cat-file", "blob", oid.decode()).decode(errors="replace"), private)
            if issues:
                findings.append((f"history {commit[:7]}:{path.decode()}", issues))
        metadata = git(project, "show", "-s", "--format=%an <%ae>%n%cn <%ce>%n%B", commit).decode()
        issues = inspect_text("commit metadata", metadata, private)
        if issues:
            findings.append((f"commit metadata {commit[:7]}", issues))
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="Also scan reachable commits and author metadata")
    args = parser.parse_args()
    private = known_private(PROJECT)
    paths = [p.decode() for p in git(PROJECT, "ls-files", "-z").split(b"\0") if p]
    findings = scan_files(PROJECT, paths, private)
    if args.history:
        findings.extend(history_findings(PROJECT, private))
    for location, issues in findings:
        print(f"{location}: {', '.join(issues)}")
    if findings:
        raise SystemExit("Publication check failed. Review the named locations privately; values were not printed.")
    print("Publication scan passed for tracked files" + (" and reachable history." if args.history else "."))
    print("Review new personal names, private project details, and unrecognized credentials manually too.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError):
        sys.exit("Publication scan stopped; inspect repository and private-file access locally.")
