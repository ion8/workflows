![Workflows Banner](./header.svg)

This repo contains our reusable workflows, used in repositories across the organization.

# ✒️ Linting
## `ci-next.js.yaml`
Build and test a Next.js application that uses yarn. Uses caching for the yarn downloads and Next.js build artifacts where possible.

If codeceptjs is not in the project dependencies, the test step will be skipped.

## `ci-python.yaml`
Lint and test a Python application that uses poetry, flake8 and pytest. Uses caching for the poetry downloads.

If flake8, black, or pytest are not in the dependencies, their steps will be skipped.

# 🤖 AI PR Review
## `ai-pr-review.yml`
When someone comments `/ai-review` on a PR, this posts a review request in #ion8-engineering-pr that @mentions the AI reviewer. The AI reviewer reviews the PR on GitHub, then replies in the Slack thread with a count of findings and a link to the review. A person still reviews and approves the PR.

Nothing runs when a PR is opened, so work in progress isn't reviewed by accident. Comment `/ai-review` when the PR is ready, and again after new commits to ask for a re-review.

- The comment's first line has to be exactly `/ai-review`, and it has to come from someone in the org or invited to the repo.
- 👀 on the comment means the request went out. 😕 means it didn't: the PR is closed, or Slack rejected the message. The Actions tab has the details.
- The AI reviewer only ever leaves a `COMMENT` review. It never approves, requests changes, pushes or merges.
- This workflow never checks out or runs code from the PR.
- If the AI hasn't replied in the Slack thread within 30 minutes, reply in the thread with `@Claude please run the ai-pr-review skill on this PR`.

Today the AI reviewer is Claude, through Claude Tag (Claude in Slack). Its review instructions are the `ai-pr-review` skill in the `ai-pr-reviewer` plugin of [ion8/dev-agents](https://github.com/ion8/dev-agents).

## How do I get AI PR Review working in my repo?

In the target repository, create `.github/workflows/ai-pr-review.yml`:

```yaml
name: AI PR Review

on:
  issue_comment:
    types: [created]

permissions: {}

jobs:
  request-review:
    if: github.event.issue.pull_request && startsWith(github.event.comment.body, '/ai-review')
    permissions:
      pull-requests: write # read the PR and its reviews, react 👀 / 😕 on the comment
    uses: ion8/workflows/.github/workflows/ai-pr-review.yml@main
    with:
      ai_reviewer_slack_user_id: ${{ vars.AI_REVIEWER_SLACK_USER_ID }}
    secrets:
      ENGINEERING_PR_SLACK_WEBHOOK_URL: ${{ secrets.ENGINEERING_PR_SLACK_WEBHOOK_URL }}
```

Merge it to `main` before testing. GitHub only runs comment-triggered workflows from the default branch, so the PR that adds this file can't trigger it.

**Adding a repo** (an org admin does these):
1. Give the AI reviewer access to the repo in Claude Tag's GitHub settings.
2. Add a branch ruleset on `main` that requires one human approval, with no bypass for the AI's GitHub app.
3. Add the repo to the selected repositories of the org secret `ENGINEERING_PR_SLACK_WEBHOOK_URL`.

**One-time org setup:**
- Org secret `ENGINEERING_PR_SLACK_WEBHOOK_URL`: a Slack incoming webhook for #ion8-engineering-pr.
- Org variable `AI_REVIEWER_SLACK_USER_ID`: the AI reviewer's Slack member ID (Slack › its profile › ⋮ › Copy member ID).

# 🤖 AI Review (older OpenAI reviewer, being replaced)
> New repos should use [AI PR Review](#-ai-pr-review) (`/ai-review`) instead. This reviewer stays until the last repo using it has moved over.

## `ai_pr_review.yml`
Automatically reviews pull requests using **PR-Agent**, an AI-powered code review tool. The workflow triggers on pull request events (opened, reopened, ready_for_review) and issue comments, providing automated code review feedback.

The workflow is configured with custom review instructions that emphasize:
- **Code correctness**, security issues, performance risks, and unsafe patterns
- **Exception hygiene** - ensuring exceptions align with project standards
- **Documentation sync** - suggesting README and environment variable documentation updates when public behavior changes
- **Noise control** - keeping feedback brief for small or low-impact PRs

Auto-review and auto-describe are enabled, while auto-improve is disabled by default.

It uses the organization-level `OPENAI_CODE_REVIEW_API_KEY` secret. Don't add it to new repos.

# 🔐 Security
We'll be adding security workflows soon™️.

# ⭐ Compliance
For compliance reasons, we have templates that will generate a list of SOUP (Software of Unknown Pedigree). This works as follows:

#### We have two workflows stored in `.github/workflows/`.
- `cook-python-soup.yml`
- `cook-js-soup.yml`


#### Both will:
- Accept a `branch` input to know which branch to push changes to.
- Check out the target repository (the repo where the workflow is running).
- Check out the `workflows` repository to access `generate_soup.py`.
- Run the appropriate license scanning commands for `pip-license` or `license-checker` to generate a JSON file with dependencies
- Run the Python script to parse the JSON file and generate a `SOUP.md` document with this information presented beautifully.
- Commit and push changes to `SOUP.md` if any changes are detected.

## How do I get SOUP CI/CD working in my repo?

In each target repository, you need to do two things:
- Add the license dependency this workflow depends on. (That's `pip-licenses` for Python and `license-checker` for JavaScript)
- Create a minimal workflow file that triggers on dependency changes and calls the reusable workflow from the `workflows` repository. See example below.

### Python Repository Example

For a Python repo using Poetry, create `.github/workflows/cook-soup-delicious.yml`:

```yaml
name: Cook up some delicious SOUP (Python)

on:
  # Trigger when dependencies change
  push:
    branches: [ main ]
    paths:
      - 'poetry.lock'
      - 'pyproject.toml'

  # Also allow manual triggering
  workflow_dispatch: 
    inputs: 
      branch: 
        type: string 
        default: "main"

jobs:
  call-python-soup:
    # Calls the reusable workflow from the workflows repo
    uses: ion8/workflows/.github/workflows/cook_python_soup.yml@main
    with:
      branch: 'main'
```
_______


### JavaScript Repository Example

For a JS repo using npm, create `.github/workflows/cook-soup-delicious.yml`:

```yaml
name: Cook up some delicious SOUP (JavaScript)

on:
  # Trigger when dependencies change (npm lock file)
  push:
    branches: [ main ]
    paths:
      - 'package-lock.json'
      - 'package.json'
      - 'yarn.lock'

  # Also allow manual triggering
  workflow_dispatch: 
    inputs: 
      branch: 
        type: string 
        default: "main"

jobs:
  call-js-soup:
    uses: ion8/workflows/.github/workflows/cook_js_soup.yml@main
    with:
      branch: 'main'
```