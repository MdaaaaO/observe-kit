# Contributing

Thanks for helping. The short version:

- **Open an issue first** for anything bigger than a typo, so we agree on the change before you write it.
- **PR titles are [Conventional Commits](https://www.conventionalcommits.org).** PRs are
  squash-merged, the title becomes the commit, and the commit becomes the changelog line. The
  `pr-title` check enforces this (`feat: async support`, `fix: …`, `docs: …`). Put `!` after
  the type or scope for a breaking change, and explain it in a `BREAKING CHANGE:` footer in the
  PR description.
- **`make ci` passes locally** before you push. It runs ruff, `mypy --strict`, pytest with branch
  coverage, and actionlint. You need [uv](https://docs.astral.sh/uv/). Run `make install` once.
- Maintainer PRs start from an issue and say so: `Closes #N` or `Refs #N` in the description.
  Release PRs and Dependabot are exempt.
- New behaviour comes with a test, for sync and `async def` alike. `MemorySink` collects events,
  so most tests need nothing else.
- The scope is the decorator. Integrations (a Prometheus sink, a Slack notifier) belong in your
  application or in a separate package; the protocols in `observe_kit.sinks` are the extension points.

## Code review

An automated Claude review comments on each PR from this repo's branches, as inline threads plus
one summary comment. Maintainers can ask it again after a fix push with `@claude review`. Release
PRs and Dependabot are not reviewed. The `coverage` job adds a comment with the coverage of the
lines the PR changes; PRs from forks get a read-only token, so there the job runs but cannot comment.

The review is advisory, but its threads are not optional: a PR is merged only when every thread is
answered and resolved (the `main` ruleset requires it). An answer is one of:

1. **A fix on the branch** — the default, even if it costs another review cycle. Reply with the
   commit SHA.
2. **A follow-up issue**, only for what is genuinely outside the PR's scope, labelled
   `review-followup` and cited in the reply. It is picked up first, right after the merge.
3. **A disagreement, with the reason**, citing the commit or issue that makes it checkable.

A finding is never parked without an issue number. PRs are squash-merged only, and the branch is
deleted on merge.

## Releasing (maintainers)

Releases use [conventional-release](https://github.com/MdaaaaO/conventional-release).
`make release` (or `make release ARGS=minor`) opens the `chore(release): X.Y.Z` PR. Squash-merge
it with the title unchanged. `release.yml` then tags the merge commit, publishes the GitHub
Release, publishes to TestPyPI and then to PyPI (the `pypi` environment waits for approval).
`make release-dry` shows what would ship.
