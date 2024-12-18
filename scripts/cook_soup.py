"""
Generate a 'SOUP.md' file from license scanner outputs:
  - `licenses-npm.json` (for JavaScript projects using license-checker).
  - `licenses-poetry.json` (for Python projects using pip-licenses).

Also performs automated risk assessment for each dependency:
  * Uses a weighted scoring approach for risk:
      1) Infrequent Commits (>1 year) => 1 point
      2) Low Popularity (<100 stars) => 2 points
      3) Significantly Older Version => 2 points
      4) Excessive Open Issues => 2 points
      5) Last Release Date > 2 years => 2 points
      6) Known CVE/CWEs => 3 points

    Scoring thresholds:
      0-1 => Low
      2-3 => Medium
      >=4 => High
"""

import json
import os
import re
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone


class License:
    """
    Represents metadata about an open-source license:
      - requires_license_file: bool
        Does the license require including a copy of the license text?

      - is_non_commercial_only: bool
        Does the license prohibit commercial use?
    """
    def __init__(
        self, 
        requires_license_file: bool, 
        is_non_commercial_only: bool
    ):
        self.requires_license_file = requires_license_file
        self.is_non_commercial_only = is_non_commercial_only

# Dictionary mapping license identifiers to License class instances
LICENSE_MAPPING = {
    "apache-2.0":    License(requires_license_file=True,  is_non_commercial_only=False),
    "mit":           License(requires_license_file=True,  is_non_commercial_only=False),
    "bsd":           License(requires_license_file=True,  is_non_commercial_only=False),
    "bsd-2-clause":  License(requires_license_file=True,  is_non_commercial_only=False),
    "bsd-3-clause":  License(requires_license_file=True,  is_non_commercial_only=False),
    "gpl-2.0":       License(requires_license_file=True,  is_non_commercial_only=False),
    "gpl-3.0":       License(requires_license_file=True,  is_non_commercial_only=False),
    "lgpl-2.1":      License(requires_license_file=True,  is_non_commercial_only=False),
    "lgpl-3.0":      License(requires_license_file=True,  is_non_commercial_only=False),
    "mpl-2.0":       License(requires_license_file=True,  is_non_commercial_only=False),
    "cc0-1.0":       License(requires_license_file=False, is_non_commercial_only=False),
    "isc":           License(requires_license_file=True,  is_non_commercial_only=False),
    "agpl-3.0":      License(requires_license_file=True,  is_non_commercial_only=False),
    "unlicense":     License(requires_license_file=True,  is_non_commercial_only=False),
    "cc-by-nc-4.0":  License(requires_license_file=True,  is_non_commercial_only=True),

    # Fallback for unrecognized licenses
    "unknown":       License(requires_license_file=False, is_non_commercial_only=False),
}


def get_license_object(license_id: str) -> License:
    """
    Retrieve the License instance for a given license identifier.
    If not found, default to the 'unknown' license object.

    :param license_id: e.g. "mit", "apache-2.0", "unknown"
    :return: License instance
    """
    normalized = license_id.casefold().strip()
    return LICENSE_MAPPING.get(normalized, LICENSE_MAPPING["unknown"])

def normalize_license(license_str: str) -> str:
    """
    Normalize a license string to lowercase. Fallback to 'unknown' if empty.
    """
    if not license_str:
        return "unknown"
    return license_str.casefold().strip()


def process_poetry_licenses(file_path):
    """
    Read and parse the JSON output from `pip-licenses` for Poetry-based Python projects.
    
    :param file_path: Path to `licenses-poetry.json`.
    :return: List of dicts with keys: name, version, url, license.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []
    for item in data:
        normalized = normalize_license(item.get("License", ""))
        results.append({
            "name": item.get("Name", "Unknown"),
            "version": item.get("Version", "Unknown"),
            "url": item.get("URL", ""),
            "license": normalized
        })
    return results

def process_npm_licenses(file_path):
    """
    Read and parse the JSON output from `license-checker` for npm-based projects.
    
    :param file_path: Path to `licenses-npm.json`.
    :return: List of dicts, each with keys: name, version, url, license.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = []
    for package_key, info in data.items():
        # package_key often looks like "react@17.0.2"
        if "@" in package_key:
            name, version = package_key.rsplit("@", 1)
        else:
            name = package_key
            version = "unknown"

        license_str = info.get("licenses", "")
        if isinstance(license_str, list) and license_str:
            license_str = license_str[0]

        normalized = normalize_license(license_str)
        url = info.get("repository") or info.get("url") or ""
        results.append({
            "name": name,
            "version": version,
            "url": url,
            "license": normalized
        })
    return results


def fetch_github_repo_info(owner, repo):
    """
    Enhanced to fetch:
      - stars
      - last_commit_date (pushed_at)
      - latest_version
      - open_issues_count
      - last_release_date
      - has_known_cve (boolean)

    :param owner: GitHub owner/org.
    :param repo: GitHub repo name.
    :return: dict with keys {stars, last_commit_date, latest_version, open_issues_count, last_release_date, has_known_cve}.
    """
    api_token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"Accept": "application/vnd.github+json"}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"

    base_repo_api_url = f"https://api.github.com/repos/{owner}/{repo}"

    # Default values
    result = {
        "stars": 0,
        "last_commit_date": None,
        "latest_version": None,
        "open_issues_count": 0,
        "last_release_date": None,
        "has_known_cve": False
    }

    # ---------------------------
    # 1) Basic repo info
    #    (includes stars, open_issues_count, pushed_at)
    # ---------------------------
    try:
        req = urllib.request.Request(base_repo_api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            result["stars"] = data.get("stargazers_count", 0)
            result["open_issues_count"] = data.get("open_issues_count", 0)
            pushed_at = data.get("pushed_at", "")
            
            if pushed_at:
                result["last_commit_date"] = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))

    except Exception:
        pass

    # ---------------------------
    # 2) Latest release info (tag_name, published_at)
    # ---------------------------
    releases_api_url = f"{base_repo_api_url}/releases/latest"
    try:
        req = urllib.request.Request(releases_api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            result["latest_version"] = data.get("tag_name")
            published_at = data.get("published_at", "")
            
            if published_at:
                last_release_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                result["last_release_date"] = last_release_date

    except urllib.error.HTTPError as e:
        if e.code != 404:
            pass

    except Exception:
        pass

    # ---------------------------
    # 3) Check for known CVEs or CWEs via GitHub Security Advisories
    #    (Very simplified approach!)
    # ---------------------------
    advisories_url = f"https://api.github.com/repos/{owner}/{repo}/security/advisories"
    try:
        req = urllib.request.Request(advisories_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            advisories_data = json.loads(resp.read().decode("utf-8"))
            
            # If there's any published advisory, we'll set has_known_cve = True
            if isinstance(advisories_data, list) and len(advisories_data) > 0:
                result["has_known_cve"] = True

    except urllib.error.HTTPError as e:
        # If it's 404 or 403, we assume no advisories or no access
        pass
    
    except Exception:
        pass

    return result


def is_significantly_older(local_version, latest_version):
    """
    Determine if local_version is >=1 major versions behind the latest_version using a simple major comparison.
    """
    def parse_major(ver_str):
        ver_str = ver_str.lstrip("v")  # Remove leading 'v'
        match = re.match(r"(\d+)\.", ver_str)
        return int(match.group(1)) if match else 0

    if not local_version or not latest_version:
        return False
    local_major = parse_major(local_version)
    latest_major = parse_major(latest_version)
    return (latest_major - local_major) >= 1


def assess_risk(repo_url, local_version):
    """
    Weighted scoring approach with additional factors:
      1) Infrequent Commits (>1 year) => 1 point
      2) Low Popularity (<100 stars) => 2 points
      3) Significantly Older Version => 2 points
      4) Excessive Open Issues => 1 points
      5) Last Release Date > 2 years => 1 points
      6) Known CVE/CWEs => 3 points

    Scoring thresholds:
      0 => Low
      1-3 => Medium
      >=4 => High
    """
    owner = parse_maintainer_from_url(repo_url)
    if not owner:
        return ("Low", "")  # Not a GitHub URL => skip

    match = re.search(r"github\.com/([^/]+)/([^/]+)", repo_url)
    if not match:
        return ("Low", "")

    repo_name = match.group(2).rstrip(".git")
    info = fetch_github_repo_info(owner, repo_name)

    score = 0
    notes_list = []

    # (1) Infrequent Commits
    if info["last_commit_date"]:
        days_since_push = (datetime.now(timezone.utc) - info["last_commit_date"]).days
        if days_since_push > 365:
            score += 1
            notes_list.append("Infrequent Commits")

    # (2) Low Popularity
    if info["stars"] < 100:
        score += 2
        notes_list.append("Low Popularity")

    # (3) Significantly Older Version
    if is_significantly_older(local_version, info["latest_version"]):
        score += 2
        notes_list.append("Version Behind Latest")

    # (4) Excessive Open Issues
    #    A naive ratio: open_issues_count * 100 / max(stars, 1).
    issues_per_100_stars = info["open_issues_count"] * 100 / max(info["stars"], 1)
    # Example threshold: If ratio > 50 => "Excessive Open Issues" 
    if issues_per_100_stars > 50:
        score += 1
        notes_list.append("Excessive Open Issues")

    # (5) Last Release Date > 2 years
    if info["last_release_date"]:
        days_since_release = (datetime.now(timezone.utc) - info["last_release_date"]).days
        if days_since_release > 730:
            score += 1
            notes_list.append("Stale Release (>2y)")

    # (6) Open CVE / CWEs
    if info["has_known_cve"]:
        score += 3
        notes_list.append("Known CVE/CWEs")

    # Determine risk
    if score <= 1:
        risk_level = "Low"
    elif score <= 3:
        risk_level = "Medium"
    else:
        risk_level = "High"

    notes = ", ".join(notes_list)
    return (risk_level, notes)


def main():
    """
    Main entry: checks for JSON files, merges results, deduplicates, writes 'SOUP.md'.
    """
    npm_file = "licenses-npm.json"
    poetry_file = "licenses-poetry.json"

    entries = []
    if os.path.exists(npm_file):
        entries.extend(process_npm_licenses(npm_file))
    if os.path.exists(poetry_file):
        entries.extend(process_poetry_licenses(poetry_file))

    # Deduplicate by (name, version, license)
    unique_map = {}
    for e in entries:
        key = (e["name"], e["version"], e["license"])
        if key not in unique_map:
            unique_map[key] = e
    final_entries = list(unique_map.values())

    # Enrich each entry with license requirements, risk level, and notes
    for entry in final_entries:
        license_obj = get_license_object(entry["license"])
        license_req = "Include License File" if license_obj.requires_license_file else "No License File Required"
        if license_obj.is_non_commercial_only:
            license_req += ", NON-COMMERCIAL USE ONLY"

        risk_level, notes = assess_risk(entry["url"], entry["version"])

        # If it's an unknown license, manual review is required
        if entry["license"] == "unknown":
            risk_level = "High"
            notes = "Unknown License, Manual Review Required"

        entry["risk_level"] = risk_level
        entry["license_req"] = license_req
        entry["notes"] = notes

    # Custom sort by Risk Level then by component name
    risk_priority = {"High": 1, "Medium": 2, "Low": 3}
    final_entries.sort(
        key=lambda e: (risk_priority.get(e["risk_level"], 999), e["name"].lower())
    )

    # Time to append the data to SOUP.md
    md_lines = []
    md_lines.append("| Risk Level | Component Name | Version | License | License Requirements | Notes | GitHub Repo URL |")
    md_lines.append("|------------|---------------|---------|---------|----------------------|-------|-----------------|")

    for entry in final_entries:
        md_lines.append(
            f"| {entry['risk_level']} "
            f"| {entry['name']} "
            f"| {entry['version']} "
            f"| {entry['license']} "
            f"| {entry['license_req']} "
            f"| {entry['notes']} "
            f"| {entry['url']} |"
        )

    # Load template and write it to a file
    with open(".workflowsRepo/scripts/cook_soup_template.md", "r", encoding="utf-8") as soup_template:
        template_content = soup_template.read()

    final_content = template_content.replace("{{DEPENDENCY_TABLE}}", "\n".join(md_lines))
    with open("SOUP.md", "w", encoding="utf-8") as out_file:
        out_file.write(final_content)


if __name__ == "__main__":
    main()
