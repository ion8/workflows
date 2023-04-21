# workflows
A repository for reusable common workflows for the ion8 organisation.

## `ci-next.js.yaml`
Build and test a Next.js application that uses yarn. Uses caching for the yarn downloads and Next.js build artifacts where possible.

If codeceptjs is not in the project dependencies, the test step will be skipped.

## `ci-python.yaml`
Lint and test a Python application that uses poetry, flake8 and pytest. Uses caching for the poetry downloads.

If flake8, black, or pytest are not in the dependencies, their steps will be skipped.

## `iac.yaml`
Check infrastructure-as-code Terraform files for issues. Uses caching for the Terraform plugins.
