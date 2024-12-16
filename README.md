![Workflows Banner](./header.svg)

This repo contains our reusable workflows, used in repositories across the organization.

# ✒️ Linting
## `ci-next.js.yaml`
Build and test a Next.js application that uses yarn. Uses caching for the yarn downloads and Next.js build artifacts where possible.

If codeceptjs is not in the project dependencies, the test step will be skipped.

## `ci-python.yaml`
Lint and test a Python application that uses poetry, flake8 and pytest. Uses caching for the poetry downloads.

If flake8, black, or pytest are not in the dependencies, their steps will be skipped.

# 🔐 Security
We'll be adding security workflows soon™️.

# ⭐ Compliance
For compliance reasons, we have templates that will generate a list of SOUP (Software of Unknown Pedigree). This works as follows:

#### We have two workflows stored in `.github/workflows/`.
- `generate-soup-python.yml`
- `generate-soup-js.yml`


#### Both will:
- Accept a `branch` input to know which branch to push changes to.
- Check out the target repository (the repo where the workflow is running).
- Check out the `workflows` repository to access `generate_soup.py`.
- Run the appropriate license scanning commands for `pip-license` or `license-checker` to generate a JSON file with dependencies
- Run the Python script to parse the JSON file and generate a `SOUP.md` document with this information presented beautifully.
- Commit and push changes to `SOUP.md` if any changes are detected.

## How do I get SOUP CI/CD working in my repo?

In each target repository, you create a minimal workflow file that triggers on dependency changes and calls the reusable workflow from the `workflows` repository.

### Python Repository Example

For a Python repo using Poetry, create `.github/workflows/run-generate-soup.yml`:

```yaml
name: Run Generate SOUP (Python)

on:
  # Trigger when dependencies change
  push:
    branches: [ main ]
    paths:
      - 'poetry.lock'
      - 'pyproject.toml'
  pull_request:
    branches: [ main ]
    paths:
      - 'poetry.lock'
      - 'pyproject.toml'

jobs:
  call-python-soup:
    # Calls the reusable workflow from the workflows repo
    uses: ion8/workflows/.github/workflows/generate-soup-python.yml@main
    with:
      branch: 'main'

```
_______


### JavaScript Repository Example

For a JS repo using npm, create `.github/workflows/run-generate-soup.yml`:

```yaml
name: Run Generate SOUP (JavaScript)

on:
  # Trigger when dependencies change (npm lock file)
  push:
    branches: [ main ]
    paths:
      - 'package-lock.json'
  pull_request:
    branches: [ main ]
    paths:
      - 'package-lock.json'

jobs:
  call-js-soup:
    uses: ion8/workflows/.github/workflows/generate-soup-js.yml@main
    with:
      branch: 'main'

```
## Ensuring Commit Permissions

- By specifying `permissions: contents: write` in the reusable workflows, the `GITHUB_TOKEN` automatically has sufficient permissions to commit and push changes to `soup.md`.
- If you have branch protection rules, ensure that the `GITHUB_TOKEN` can bypass them or that the workflow runs under conditions where it can push successfully.
- Confirm that the default `GITHUB_TOKEN` permissions in your organization are not restricted. The default settings typically allow committing with `contents: write`.