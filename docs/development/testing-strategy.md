# Testing strategy

Use unit tests for business rules, contract tests for OpenAPI, database tests for
constraints/bootstrap, integration tests across domains, and a short final
smoke/E2E suite. Each defect fix adds a regression test.
