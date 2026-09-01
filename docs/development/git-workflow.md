# Git workflow

1. Move one Trello/WBS card to In Progress.
2. Update local `main`, then create one short-lived task branch.
3. Change only the owning domain where possible.
4. Commit small, meaningful units.
5. Open one pull request for one goal with tests/evidence.
6. Resolve conflicts on the feature branch with the affected file owner.
7. Merge using **Create a merge commit**, then delete the branch.

Coordinate before editing shared hotspots: API router, model registry,
schema.sql, OpenAPI, package locks, and infrastructure.
