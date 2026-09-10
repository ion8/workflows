# ion8 Shared Workflows

Reusable GitHub Actions workflows for the ion8 org. Every workflow here is consumed by other repositories via `workflow_call`, so changes to `main` are live immediately for all downstream repos. Test carefully before merging.

## How Downstream Repos Call These

```yaml
jobs:
  my-job:
    uses: ion8/workflows/.github/workflows/<workflow-file>@main
    with:
      some_input: value
    secrets:
      SOME_SECRET: ${{ secrets.SOME_SECRET }}
```

## Testing Changes Before Merging to Main

When you're working on a branch and need to test in a downstream repo, the lighthouse and link-checker workflows have a commented-out `ref:` line in their checkout steps. Uncomment it and point it at your branch:

```yaml
- uses: actions/checkout@v4
  with:
    repository: ion8/workflows
    path: .workflows
    ref: your-branch-name  # uncomment this line
```

Remove the `ref:` line (or re-comment it) before merging to main.

## Workflows

### CI

**`ci-nextjs.yaml`** - Builds and tests Next.js apps.
- Uses yarn + Node 14
- Caches yarn downloads and Next.js build artifacts
- Runs codeceptjs headless tests if codeceptjs is in dependencies (skips if not)
- No inputs or secrets required

**`ci-python.yaml`** - Lints and tests Python apps.
- Uses Poetry + Python 3.10
- All linting tools are optional - skipped if not in dependencies:
  - flake8, ruff, black for linting
  - pytest for tests
- No inputs or secrets required

**`iac.yaml`** - Lints Terraform files with tflint.
- Requires a `.tflint.hcl` config in the calling repo
- No inputs or secrets required

### Quality / Auditing

**`lighthouse-ci.yml`** - Runs Lighthouse CI against a URL and posts results as a PR comment.
- Inputs: `preview_url` (required), `pr_number` (optional - defaults to current PR)
- Secrets: `LHCI_GITHUB_APP_TOKEN` (required)
- Thresholds from `lighthouserc.json`: performance ≥60%, accessibility ≥80%, best practices ≥80%, SEO ≥90%
- Runs 3 times and uses the median score
- Uploads full report to temporary public storage and links it in the PR comment
- Emoji indicators: 🟢 comfortably passing, 🟡 at threshold, 🔴 failing

**`link-checker-ci.yml`** - Crawls a site via sitemap and checks for broken links and missing images.
- Inputs: `url` (required), `pr_number` (optional)
- No secrets required
- Discovers pages from sitemap.xml (checks robots.txt first, then `/sitemap.xml`, `/sitemap_index.xml`)
- Internal broken links and missing images = CI failure
- External broken links = warning only (doesn't fail CI)
- Skips anchors, javascript:, mailto:, tel:, and `help.ion8.net` (blocks automated requests)
- Posts a markdown report as a PR comment; uploads as artifact

**`ai_pr_review.yml`** - AI-powered PR review via qodo-ai/pr-agent (OpenAI).
- Secrets: `OPENAI_CODE_REVIEW_API_KEY` (managed at org level - no per-repo setup needed)
- Auto-review and auto-describe are enabled; auto-improve is disabled
- Skips bot-authored events

### Maintenance

**`automaintain-ci.yml`** - Creates a monthly maintenance PR and runs link checker + lighthouse against production.
- Inputs: `website_url` (required)
- Secrets: `LHCI_GITHUB_APP_TOKEN` (required)
- Creates a branch named `<month>-<year>-automaintain` and a PR titled `<Month> <Year> - AutoMaintain`
- Adds `maintenance` and `automated` labels to the PR
- Calls link-checker and lighthouse workflows and posts their results as comments on the new PR

### Compliance

**`cook_python_soup.yml`** - Generates a SOUP.md (Software of Unknown Pedigree) document for Python/Poetry repos.
- Requires `pip-licenses` as a dev dependency in the calling repo
- Generates `licenses-poetry.json` then runs `scripts/cook_soup.py`
- Creates a PR to update `SOUP.md` if anything changed (branch: `update-soup-md`)

**`cook_js_soup.yml`** - Same as above but for JS/npm repos.
- Requires `license-checker` as a dev dependency in the calling repo
- Generates `licenses-npm.json` then runs `scripts/cook_soup.py`

## Scripts

**`scripts/link-checker.js`** - The link checker script. Pure Node.js, no dependencies - uses built-in `fetch`. Run directly with `node scripts/link-checker.js <url>`. Writes output to `link-checker-report.md`.

**`scripts/cook_soup.py`** - Parses `licenses-poetry.json` or `licenses-npm.json` and generates `SOUP.md` using `scripts/cook_soup_template.md`.

## Config Files

**`lighthouserc.json`** - Lighthouse CI thresholds and settings. Skips `is-crawlable`, `third-party-cookies`, and `issues` audits. Blocks Google Tag Manager and Zoho SalesIQ from network requests during audits. Saves reports to `.lighthouseci/`.

## Secrets Reference

| Secret | Where managed | Used by |
|--------|--------------|---------|
| `LHCI_GITHUB_APP_TOKEN` | Per-repo or org | lighthouse-ci, automaintain-ci |
| `OPENAI_CODE_REVIEW_API_KEY` | Org level | ai_pr_review |
