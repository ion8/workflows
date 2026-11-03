import json
import subprocess

import check
import pytest
from changelog import Entry, Section, parse

MISSING = 'Add an entry to CHANGELOG.md, or add the "no changelog" label'

CHANGELOG = """# Changelog

## November 2026

### Fixed

- Connecting Salesforce works again.

## October 2026

### Added

- The dashboard now flags integrations that need reconnecting.
"""
NOVEMBER_ENTRY = "- Connecting Salesforce works again.\n"
OCTOBER_ENTRY = "- The dashboard now flags integrations that need reconnecting.\n"
UNRELEASED = CHANGELOG.replace(
    "## November 2026", "## Unreleased\n\n### Added\n\n- Faxes log once.\n- Meetings log once.\n\n## November 2026"
)
RELEASE_CUT = UNRELEASED.replace("## Unreleased", "## Unreleased\n\n## 0.2.0 - 2026-11-20")
ACCENTED = UNRELEASED.replace("Connecting Salesforce", "Connecting Salesforce in Montréal")


def add_after(text, line, new_line):
    return text.replace(line, f"{line}{new_line}\n", 1)


@pytest.fixture(autouse=True)
def summary(tmp_path, monkeypatch):
    path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(path))
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    return path


class Repo:
    def __init__(self, path):
        self.path = path
        self.git("init", "-q")

    def git(self, *args):
        return subprocess.run(
            ["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid", *args],
            cwd=self.path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self, files):
        for name, content in files.items():
            (self.path / name).write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", "change")
        return self.git("rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    path = tmp_path / "repo"
    path.mkdir()
    monkeypatch.chdir(path)
    return Repo(path)


def check_pr(repo, base_files, head_files, author="octocat", labels=()):
    base = repo.commit(base_files)
    head = repo.commit(head_files)
    return check.main(["--base", base, "--head", head, "--author", author, "--labels", json.dumps(list(labels))])


def check_text(tmp_path, text):
    path = tmp_path / "CHANGELOG.md"
    path.write_bytes(text.encode("utf-8"))
    return check.main(["--file", str(path)])


def test_parse_returns_releases_and_sections_in_file_order():
    releases, problems = parse(
        "## October 2026\n\n### Changed\n\n- One.\n\n### Added\n\n- Two.\n- Three.\n### Changed\n- Five.\n\n"
        "## 0.1.0 - 2026-09-30\n\n### Removed\n\n- Four.\n"
    )
    assert problems == []
    assert [release.heading for release in releases] == ["October 2026", "0.1.0 - 2026-09-30"]
    assert list(releases[0].sections) == [Section.CHANGED, Section.ADDED]
    assert releases[0].sections[Section.ADDED] == [Entry("Two.", 9), Entry("Three.", 10)]
    assert releases[0].sections[Section.CHANGED] == [Entry("One.", 5), Entry("Five.", 12)]
    assert releases[1].sections == {Section.REMOVED: [Entry("Four.", 18)]}


@pytest.mark.parametrize("heading", ["November 2026", "Unreleased", "0.2.0 - 2026-11-20"])
def test_each_heading_shape_passes(tmp_path, heading):
    assert check_text(tmp_path, f"# Changelog\n\n## {heading}\n\n### Fixed\n\n- Calls log again.\n") == 0


def test_unknown_heading_lists_the_three_shapes(tmp_path, summary):
    assert check_text(tmp_path, "## Next\n\n### Fixed\n\n- Calls log again.\n") == 1
    text = summary.read_text(encoding="utf-8")
    assert "**Line 1.**" in text
    for shape in ("## November 2026", "## Unreleased", "## 0.2.0 - 2026-11-20"):
        assert shape in text


def test_missing_changelog_change_fails(repo, summary):
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG, "app.py": "x = 1\n"}, {"app.py": "x = 2\n"}) == 1
    text = summary.read_text(encoding="utf-8")
    assert text.startswith(MISSING)
    assert "## November 2026" in text
    assert check.README in text


def test_no_changelog_label_skips_the_check(repo):
    base = {"CHANGELOG.md": CHANGELOG, "app.py": "x = 1\n"}
    assert check_pr(repo, base, {"app.py": "x = 2\n"}, labels=["bug", "no changelog"]) == 0


def test_dependabot_skips_the_check(repo):
    base = {"CHANGELOG.md": CHANGELOG, "requirements.txt": "requests==2.31.0\n"}
    assert check_pr(repo, base, {"requirements.txt": "requests==2.32.3\n"}, author="dependabot[bot]") == 0


def test_entry_under_the_top_heading_passes(repo):
    head = add_after(CHANGELOG, NOVEMBER_ENTRY, "- Meetings log once.")
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG}, {"CHANGELOG.md": head}) == 0


def test_unknown_section_lists_the_four_sections(repo, summary):
    head = CHANGELOG.replace("### Fixed", "### Bugfixes")
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG}, {"CHANGELOG.md": head}) == 1
    text = summary.read_text(encoding="utf-8")
    assert "`### Bugfixes` is not a section" in text
    for section in ("### Added", "### Changed", "### Fixed", "### Removed"):
        assert section in text


def test_bullet_with_no_section_fails(repo, summary):
    head = CHANGELOG.replace("## November 2026\n", "## November 2026\n\n- Meetings log once.\n")
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG}, {"CHANGELOG.md": head}) == 1
    assert "not under a section" in summary.read_text(encoding="utf-8")


@pytest.mark.parametrize(("length", "code"), [(300, 0), (301, 1)])
def test_entry_length_limit(repo, summary, length, code):
    head = add_after(CHANGELOG, NOVEMBER_ENTRY, "- " + "a" * length)
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG}, {"CHANGELOG.md": head}) == code
    if code:
        assert "301 characters" in summary.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("entry", "matches"),
    [
        ("Seen for org 2093.", ["org 2093"]),
        ("Calls log again for jane.doe@example.com.", ["jane.doe@example.com"]),
        ("Seen for org 2093 by jane.doe@example.com.", ["org 2093", "jane.doe@example.com"]),
        ("Fixed the lookup by org_id.", ["org_id"]),
    ],
)
def test_confidential_entry_fails_and_names_each_match(repo, summary, entry, matches):
    head = add_after(CHANGELOG, NOVEMBER_ENTRY, f"- {entry}")
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG}, {"CHANGELOG.md": head}) == 1
    text = summary.read_text(encoding="utf-8")
    for match in matches:
        assert f"`{match}`" in text


def test_entry_added_under_an_older_heading_fails(repo, summary):
    head = add_after(CHANGELOG, OCTOBER_ENTRY, "- Meetings log once.")
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG}, {"CHANGELOG.md": head}) == 1
    text = summary.read_text(encoding="utf-8")
    assert "**Line 14.**" in text
    assert "top heading, `## November 2026`" in text
    assert "## November 2026\n\n### Added\n\n- Meetings log once." in text


def test_correcting_an_older_entry_passes(repo):
    head = CHANGELOG.replace("need reconnecting", "need to be reconnected")
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG}, {"CHANGELOG.md": head}) == 0


def test_deleting_an_older_entry_passes(repo):
    head = CHANGELOG.replace(OCTOBER_ENTRY, "")
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG}, {"CHANGELOG.md": head}) == 0


@pytest.mark.parametrize(
    "head",
    [RELEASE_CUT, UNRELEASED.replace("## Unreleased", "## 0.2.0 - 2026-11-20")],
    ids=["new-unreleased-on-top", "rename-only"],
)
def test_releasing_the_unreleased_entries_passes(repo, head):
    assert check_pr(repo, {"CHANGELOG.md": UNRELEASED}, {"CHANGELOG.md": head}) == 0


def test_entry_added_under_a_released_version_fails(repo, summary):
    head = add_after(RELEASE_CUT, "- Meetings log once.\n", "- Calls log once.")
    assert check_pr(repo, {"CHANGELOG.md": UNRELEASED}, {"CHANGELOG.md": head}) == 1
    text = summary.read_text(encoding="utf-8")
    assert "top heading, `## Unreleased`, not `## 0.2.0 - 2026-11-20`" in text
    assert "## Unreleased\n\n### Added\n\n- Calls log once." in text


def test_new_changelog_with_older_months_passes(repo):
    assert check_pr(repo, {"app.py": "x = 1\n"}, {"CHANGELOG.md": CHANGELOG}) == 0


def test_crlf_line_endings_pass(repo):
    head = add_after(CHANGELOG, NOVEMBER_ENTRY, "- Meetings log once.").replace("\n", "\r\n")
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG}, {"CHANGELOG.md": head}) == 0


def test_byte_order_mark_is_ignored(repo, tmp_path):
    head = "\ufeff" + add_after(CHANGELOG, NOVEMBER_ENTRY, "- Meetings log once.").removeprefix("# Changelog\n\n")
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG}, {"CHANGELOG.md": head}) == 0
    assert check_text(tmp_path, head) == 0


@pytest.mark.parametrize(
    ("data", "line"),
    [(ACCENTED.encode("cp1252"), 14), (CHANGELOG.encode("utf-16"), 1)],
    ids=["cp1252", "utf-16"],
)
def test_file_that_is_not_utf8_fails_and_says_to_save_it_as_utf8(
    repo, tmp_path, summary, monkeypatch, capsys, data, line
):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    path = tmp_path / "CHANGELOG.md"
    path.write_bytes(data)
    assert check_pr(repo, {"CHANGELOG.md": UNRELEASED}, {"CHANGELOG.md": data}) == 1
    assert check.main(["--file", str(path)]) == 1
    out, err = capsys.readouterr()
    assert err == ""
    assert out.count("::error") == 2
    assert out.count(f"CHANGELOG.md,line={line}::") == 2
    text = summary.read_text(encoding="utf-8")
    assert text.count(f"**Line {line}.**") == 2
    assert text.count("Save `CHANGELOG.md` as UTF-8.") == 2
    assert "deletes" not in out + text


def test_deleting_the_changelog_fails(repo, summary):
    base = repo.commit({"CHANGELOG.md": CHANGELOG})
    (repo.path / "CHANGELOG.md").unlink()
    head = repo.commit({})
    assert check.main(["--base", base, "--head", head, "--author", "octocat", "--labels", "[]"]) == 1
    assert "This pull request deletes `CHANGELOG.md`." in summary.read_text(encoding="utf-8")


def test_saving_a_changelog_that_is_not_utf8_as_utf8_passes(repo):
    assert check_pr(repo, {"CHANGELOG.md": ACCENTED.encode("cp1252")}, {"CHANGELOG.md": ACCENTED}) == 0


def test_missing_entry_beside_a_changelog_that_is_not_utf8_names_the_top_heading(repo, summary):
    base = {"CHANGELOG.md": ACCENTED.encode("cp1252"), "app.py": "x = 1\n"}
    assert check_pr(repo, base, {"app.py": "x = 2\n"}) == 1
    text = summary.read_text(encoding="utf-8")
    assert text.startswith(MISSING)
    assert "## Unreleased" in text


def test_two_identical_month_headings_pass(repo):
    base = CHANGELOG.replace(
        "## November 2026", "## December 2026\n\n### Fixed\n\n- Faxes log once.\n\n## November 2026"
    )
    head = base.replace("## November 2026", "## December 2026\n\n### Added\n\n- Meetings log once.\n\n## November 2026")
    assert [release.heading for release in parse(head)[0]][:2] == ["December 2026", "December 2026"]
    assert check_pr(repo, {"CHANGELOG.md": base}, {"CHANGELOG.md": head}) == 0


def test_union_merge_of_two_new_month_headings_passes(repo):
    repo.commit({".gitattributes": "CHANGELOG.md merge=union\n", "CHANGELOG.md": CHANGELOG})
    trunk = repo.git("branch", "--show-current")
    repo.git("switch", "-q", "-c", "one")
    repo.commit(
        {"CHANGELOG.md": "# Changelog\n\n## December 2026\n\n### Fixed\n\n- Faxes log once.\n" + CHANGELOG[12:]}
    )
    repo.git("switch", "-q", trunk)
    repo.git("switch", "-q", "-c", "two")
    repo.commit(
        {"CHANGELOG.md": "# Changelog\n\n## December 2026\n\n### Added\n\n- Meetings log once.\n" + CHANGELOG[12:]}
    )
    repo.git("switch", "-q", trunk)
    repo.git("merge", "-q", "--no-edit", "one")
    repo.git("switch", "-q", "two")
    repo.git("merge", "-q", "--no-edit", trunk)
    merged = (repo.path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "- Faxes log once." in merged and "- Meetings log once." in merged
    base, head = repo.git("rev-parse", trunk), repo.git("rev-parse", "HEAD")
    assert check.main(["--base", base, "--head", head, "--author", "octocat", "--labels", "[]"]) == 0


def test_errors_are_annotations_in_github_actions(repo, monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG, "app.py": "x = 1\n"}, {"app.py": "x = 2\n"}) == 1
    assert f"::error::{MISSING}" in capsys.readouterr().out
    head = add_after(CHANGELOG, NOVEMBER_ENTRY, "- Seen for org 2093.")
    assert check_pr(repo, {"CHANGELOG.md": CHANGELOG}, {"CHANGELOG.md": head}) == 1
    assert "::error file=CHANGELOG.md,line=8::This entry contains `org 2093`." in capsys.readouterr().out
