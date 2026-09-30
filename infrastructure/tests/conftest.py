import pytest


@pytest.fixture(autouse=True)
def isolate_workflow_summary(monkeypatch):
    """Keep simulated releases out of the real GitHub Actions job summary."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
