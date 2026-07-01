# Version Diff Policy

Use this reference when preparing an MCP update report.

## Evidence Order

1. Official GitHub releases linked from npm or PyPI package metadata.
2. Official changelog files linked from the package repository or homepage.
3. npm or PyPI metadata: latest version, publish time, description, repository, homepage.
4. Package README only as secondary context.

## Reporting Requirements

For each package with a newer remote version, report:

- current installed version;
- remote latest version;
- release tags or publish dates between those versions when available;
- documented additions, removals, deprecations, breaking changes, and fixes;
- links to official release, changelog, repository, npm, or PyPI pages.

If only metadata is available, report that no structured official release notes were found.

## Safety

Do not infer feature changes from commit titles unless the user explicitly asks for deeper repository research. Do not present unverified community notes as official changes.
