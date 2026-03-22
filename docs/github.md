# GitHub Ops

## Pages

This repo uses a custom GitHub Actions workflow to build the docs site and deploy it to GitHub Pages.

What you need in the repository settings:

1. Open `Settings` -> `Pages`.
2. Set the source to `GitHub Actions`.
3. Push to `main`.

The workflow will build the docs on pull requests and deploy on pushes to `main`.

## Releases

The release workflow publishes:

- the Python source distribution
- the wheel
- a zipped copy of the built docs site
- a `SHA256SUMS.txt` manifest

### Automatic Release Path

Push a tag like:

```bash
git tag v0.1.0
git push origin v0.1.0
```

That tag triggers the release workflow and publishes assets to GitHub Releases automatically.

### Manual Release Path

The release workflow also supports `workflow_dispatch`, which is useful when you want to rebuild assets for a tag from the Actions UI.

## CI

The CI workflow validates the package on:

- Windows
- Ubuntu
- Python 3.11
- Python 3.12

That keeps the public demo path and the release path aligned.
