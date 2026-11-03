"""Check that a pull request adds a valid CHANGELOG.md entry, or lint one file.

Exit 0 when the check passes, 1 when it fails, and 2 on bad arguments.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

# python -I leaves this script's folder off sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from changelog import MONTHS, Entry, Problem, Release, Section, parse

PATH = "CHANGELOG.md"
OPT_OUT_LABEL = "no changelog"
DEPENDABOT = "dependabot[bot]"
MAX_LENGTH = 300
README = "https://github.com/ion8/workflows#changelog-check-and-sync"
MISSING = f'Add an entry to {PATH}, or add the "{OPT_OUT_LABEL}" label if this change is not user-facing.'
_CONFIDENTIAL = re.compile(r"\borg\s*\d+|org_id|[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.IGNORECASE)


def lint(releases: list[Release]) -> list[Problem]:
    problems = []
    for release in releases:
        for entries in release.sections.values():
            for entry in entries:
                if len(entry.text) > MAX_LENGTH:
                    problems.append(
                        Problem(
                            entry.line,
                            f"This entry is {len(entry.text)} characters. Keep it to {MAX_LENGTH} or fewer.",
                        )
                    )
                found = _CONFIDENTIAL.findall(entry.text)
                if found:
                    names = " and ".join(f"`{match}`" for match in found)
                    problems.append(
                        Problem(
                            entry.line,
                            f"This entry contains {names}. Leave out org ids and email addresses.",
                        )
                    )
    return problems


def _by_heading(releases: list[Release]) -> dict[str, list[tuple[Section, Entry]]]:
    grouped: dict[str, list[tuple[Section, Entry]]] = {}
    for release in releases:
        for section, entries in release.sections.items():
            grouped.setdefault(release.heading, []).extend((section, entry) for entry in entries)
    return grouped


def added_under_older_headings(base: list[Release], head: list[Release]) -> list[Problem]:
    if not head:
        return []
    top = head[0].heading
    before = _by_heading(base)
    problems = []
    for heading, entries in _by_heading(head).items():
        old = before.get(heading, [])
        gained_entries = len(entries) > len(old)
        if heading == top or not gained_entries:
            continue
        old_texts = {entry.text for _, entry in old}
        section, entry = next(((s, e) for s, e in entries if e.text not in old_texts), entries[-1])
        problems.append(
            Problem(
                entry.line,
                f"New entries go under the top heading, `## {top}`, not `## {heading}`. Move this entry there.",
                f"## {top}\n\n### {section.value}\n\n- {entry.text}",
            )
        )
    return problems


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8")


def _show(rev: str) -> str | None:
    shown = _git("show", f"{rev}:{PATH}")
    return shown.stdout if shown.returncode == 0 else None


def _git_out(*args: str) -> str:
    done = _git(*args)
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def _missing_summary(head_text: str | None) -> str:
    releases = parse(head_text)[0] if head_text else []
    today = date.today()
    top = releases[0].heading if releases else f"{MONTHS[today.month - 1]} {today.year}"
    return (
        f"{MISSING}\n\n"
        "Put the entry under the top heading, in the section that fits:\n\n"
        f"```markdown\n## {top}\n\n### Fixed\n\n- Describe the change for a customer, in one to three sentences.\n"
        "```\n\n"
        f"[Changelog check and sync]({README}) has the format and the rules."
    )


def _escape(data: str) -> str:
    return data.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _write_summary(markdown: str) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as file:
            file.write(markdown + "\n")


def _error(path: str, message: str, line: int | None = None) -> None:
    if os.environ.get("GITHUB_ACTIONS") == "true":
        where = f" file={path},line={line}" if line else ""
        print(f"::error{where}::{_escape(message)}")
    else:
        print(f"{path}:{line}: {message}" if line else message)


def _report(path: str, problems: list[Problem]) -> int:
    if not problems:
        print(f"{path} passes the changelog check.")
        _write_summary(f"`{path}` passes the changelog check.")
        return 0
    problems = sorted(problems, key=lambda problem: problem.line)
    blocks = [f"Fix each problem below in `{path}`. [Changelog check and sync]({README}) has the format and the rules."]
    for problem in problems:
        message = f"{problem.message}\nExample:\n{problem.example}" if problem.example else problem.message
        _error(path, message, problem.line)
        block = f"**Line {problem.line}.** {problem.message}"
        if problem.example:
            block += f"\n\n```markdown\n{problem.example}\n```"
        blocks.append(block)
    _write_summary("\n\n".join(blocks))
    return 1


def _skip(reason: str) -> int:
    print(f"Skipped, because {reason}.")
    _write_summary(f"Skipped, because {reason}.")
    return 0


def check_file(path: str) -> int:
    releases, problems = parse(Path(path).read_text(encoding="utf-8"))
    return _report(path, problems + lint(releases))


def check_pull_request(base: str, head: str, author: str, labels: list[str]) -> int:
    if author == DEPENDABOT:
        return _skip("Dependabot opened this pull request")
    if OPT_OUT_LABEL in labels:
        return _skip(f'the pull request has the "{OPT_OUT_LABEL}" label')
    head_text = _show(head)
    if not _git_out("diff", "--name-only", f"{base}...{head}", "--", PATH):
        _error(PATH, f"{MISSING} See {README}")
        _write_summary(_missing_summary(head_text))
        return 1
    if head_text is None:
        _error(PATH, f"This pull request deletes {PATH}. Restore it.")
        _write_summary(f"This pull request deletes `{PATH}`. Restore it.")
        return 1
    releases, problems = parse(head_text)
    problems += lint(releases)
    base_text = _show(_git_out("merge-base", base, head))
    if base_text is not None:
        problems += added_under_older_headings(parse(base_text)[0], releases)
    return _report(PATH, problems)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", help="lint this file, with no pull request context")
    parser.add_argument("--base", help="the pull request's base SHA")
    parser.add_argument("--head", help="the pull request's head SHA")
    parser.add_argument("--author", default="", help="the login of the pull request's author")
    parser.add_argument("--labels", type=json.loads, default=[], help="the pull request's label names, as a JSON array")
    args = parser.parse_args(argv)
    if args.file:
        return check_file(args.file)
    if not (args.base and args.head):
        parser.error("pass --file, or --base and --head")
    return check_pull_request(args.base, args.head, args.author, args.labels)


if __name__ == "__main__":
    sys.exit(main())
