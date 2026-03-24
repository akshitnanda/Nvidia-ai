# Release Process

## What Happens On A Tag

Pushing a tag that matches `v*` triggers the release workflow.

The workflow:

1. installs build and docs dependencies
2. runs the test suite
3. builds the Python wheel and source distribution
4. builds the docs site
5. uploads release assets to GitHub Releases

## Assets Produced

- wheel
- source distribution
- zipped docs site
- `SHA256SUMS.txt`

## Example

```bash
git tag v0.1.1
git push origin v0.1.1
```

## Manual Releases

If needed, run the `Release` workflow manually from GitHub Actions using `workflow_dispatch`.
