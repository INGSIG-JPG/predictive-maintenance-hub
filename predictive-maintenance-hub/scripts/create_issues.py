"""Create the initial backlog as GitHub issues (public tracker).

Usage:  gh auth login   &&   python scripts/create_issues.py [--repo OWNER/REPO] [--dry-run]
Labels are created if missing. Run it once on a fresh repository.
"""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def gh(*args, check=True):
    return subprocess.run(["gh", *args], check=check, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    issues = json.loads((ROOT / "docs/tracker/issues.json").read_text())
    repo = ["--repo", args.repo] if args.repo else []
    for issue in issues:
        if args.dry_run:
            print(f"[dry-run] {issue['title']}  labels={issue['labels']}")
            continue
        for label in issue["labels"]:
            gh("label", "create", label, "--force", *repo, check=False)
        result = gh("issue", "create", "--title", issue["title"], "--body", issue["body"], "--label", ",".join(issue["labels"]), *repo, check=False)
        print(result.stdout.strip() or result.stderr.strip())
        if result.returncode:
            sys.exit(result.returncode)


if __name__ == "__main__":
    main()
