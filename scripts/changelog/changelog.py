import re
from dataclasses import dataclass, field
from enum import Enum

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
UNRELEASED = "Unreleased"
# A version has one to four numbers, the format Chrome Web Store builds use.
_HEADING = re.compile(rf"{UNRELEASED}|(?:{'|'.join(MONTHS)}) \d{{4}}|\d+(?:\.\d+){{0,3}} - \d{{4}}-\d{{2}}-\d{{2}}")
SECTIONS = "`### Added`, `### Changed`, `### Fixed`, or `### Removed`"
EXAMPLE_ENTRY = "- Connecting Salesforce works again."


class Section(Enum):
    ADDED = "Added"
    CHANGED = "Changed"
    FIXED = "Fixed"
    REMOVED = "Removed"


_SECTION_NAMES = {section.value: section for section in Section}


@dataclass(frozen=True)
class Entry:
    text: str
    line: int


@dataclass
class Release:
    heading: str
    line: int
    sections: dict[Section, list[Entry]] = field(default_factory=dict)


@dataclass(frozen=True)
class Problem:
    line: int
    message: str
    example: str = ""


def parse(text: str) -> tuple[list[Release], list[Problem]]:
    """Return the releases in file order and every format problem.

    Each release maps its sections, in file order, to their entries. A section
    that appears twice under one heading adds to the first.
    """
    releases: list[Release] = []
    problems: list[Problem] = []
    entries: list[Entry] | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.rstrip()
        if not line:
            continue
        if line.startswith("## "):
            heading = line[3:].strip()
            releases.append(Release(heading, number))
            entries = None
            if not _HEADING.fullmatch(heading):
                problems.append(
                    Problem(
                        number,
                        f"`{line}` is not a release heading. Use a month, `## Unreleased`, or a version and date.",
                        "## November 2026\n## Unreleased\n## 0.2.0 - 2026-11-20",
                    )
                )
        elif line.startswith("### "):
            name = line[4:].strip()
            if not releases:
                entries = []
                problems.append(
                    Problem(
                        number,
                        f"`{line}` is above the first release heading. Put it under a release heading.",
                        f"## November 2026\n\n{line}",
                    )
                )
            elif name in _SECTION_NAMES:
                entries = releases[-1].sections.setdefault(_SECTION_NAMES[name], [])
            else:
                entries = []
                problems.append(
                    Problem(number, f"`{line}` is not a section. Use {SECTIONS}.", f"### Fixed\n\n{EXAMPLE_ENTRY}")
                )
        elif line.startswith("- "):
            text = line[2:].strip()
            if entries is None:
                problems.append(
                    Problem(
                        number, f"This entry is not under a section. Put it under {SECTIONS}.", f"### Fixed\n\n- {text}"
                    )
                )
            else:
                entries.append(Entry(text, number))
        elif releases:
            problems.append(
                Problem(
                    number,
                    "Under a release heading, write each change as one line that starts with `- `.",
                    EXAMPLE_ENTRY,
                )
            )
    return releases, problems
