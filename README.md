# workflows
A repository for reusable common workflows for the ion8 organisation.

## `ci-next.js.yaml`
Build and test a Next.js application that uses yarn. Uses caching for the yarn downloads and Next.js build artifacts where possible.

## `ci-python.yaml`
Lint and test a Python application that uses poetry, flake8 and pytest. Uses caching for the poetry downloads.

## `iac.yaml`
Check infrastructure-as-code Terraform files for issues. Uses caching for the Terraform plugins.
