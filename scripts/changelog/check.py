"""Check that a pull request adds a valid CHANGELOG.md entry, or lint one file.

Exit 0 when the check passes, 1 when it fails, and 2 on bad arguments.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import date
from itertools import chain
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
NOT_UTF8 = f"This line is not UTF-8. Save `{PATH}` as UTF-8."
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


def _texts(entries: Iterable[tuple[Section, Entry]]) -> Counter[str]:
    return Counter(entry.text for _, entry in entries)


def added_under_older_headings(base: list[Release], head: list[Release]) -> list[Problem]:
    """Return a problem for each heading below the top one that gained entries.

    An entry is new when its text is nowhere in the base file, and gone when
    its text is nowhere in the head file. A heading gained entries when it has
    more new entries than gone ones.
    """
    if not head:
        return []
    top = head[0].heading
    before, after = _by_heading(base), _by_heading(head)
    base_texts, head_texts = _texts(chain(*before.values())), _texts(chain(*after.values()))
    problems = []
    for heading, entries in after.items():
        added = _texts(entries) - base_texts
        removed = _texts(before.get(heading, [])) - head_texts
        if heading == top or added.total() <= removed.total():
            continue
        section, entry = next((s, e) for s, e in entries if e.text in added)
        problems.append(
            Problem(
                entry.line,
                f"New entries go under the top heading, `## {top}`, not `## {heading}`. Move this entry there.",
                f"## {top}\n\n### {section.value}\n\n- {entry.text}",
            )
        )
    return problems


def _parse_bytes(data: bytes) -> tuple[list[Release], list[Problem]]:
    """Parse a CHANGELOG.md from its bytes, with or without a UTF-8 byte order mark.

    A byte that is not UTF-8 adds a problem at its line, and the rest of the
    file still parses.
    """
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        releases, problems = parse(data.decode("utf-8-sig", "replace"))
        return releases, [Problem(data.count(b"\n", 0, error.start) + 1, NOT_UTF8), *problems]
    return parse(text)


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], capture_output=True)


def _show(rev: str) -> bytes | None:
    shown = _git("show", f"{rev}:{PATH}")
    return shown.stdout if shown.returncode == 0 else None


def _git_out(*args: str) -> str:
    done = _git(*args)
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.decode().strip()}")
    return done.stdout.decode().strip()


def _missing_summary(head_data: bytes | None) -> str:
    releases = _parse_bytes(head_data)[0] if head_data else []
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
    releases, problems = _parse_bytes(Path(path).read_bytes())
    return _report(path, problems + lint(releases))


def check_pull_request(base: str, head: str, author: str, labels: list[str]) -> int:
    if author == DEPENDABOT:
        return _skip("Dependabot opened this pull request")
    if OPT_OUT_LABEL in labels:
        return _skip(f'the pull request has the "{OPT_OUT_LABEL}" label')
    head_data = _show(head)
    if not _git_out("diff", "--name-only", f"{base}...{head}", "--", PATH):
        _error(PATH, f"{MISSING} See {README}")
        _write_summary(_missing_summary(head_data))
        return 1
    if head_data is None:
        _error(PATH, f"This pull request deletes {PATH}. Restore it.")
        _write_summary(f"This pull request deletes `{PATH}`. Restore it.")
        return 1
    releases, problems = _parse_bytes(head_data)
    problems += lint(releases)
    base_data = _show(_git_out("merge-base", base, head))
    if base_data is not None:
        problems += added_under_older_headings(_parse_bytes(base_data)[0], releases)
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
