# Replacing README Placeholder Visuals

The README currently points to placeholder SVGs so the GitHub landing page has a visual section even before real captures are available.

## Files To Replace

- `cli-demo-placeholder.svg`
- `dashboard-placeholder.svg`

You can keep the same filenames if you want the README links to keep working unchanged.

## Recommended Real Captures

### CLI

Use a clean terminal window and run:

```powershell
swarm demo --mode plan --task "Show how this repo works"
```

Try to capture:

- the command itself
- the generated plan output
- enough terminal chrome to feel authentic without exposing local clutter

### Dashboard

Use:

```powershell
swarm dashboard
```

Then open `http://127.0.0.1:8787/` and capture:

- the hero section
- the quick start card
- the recent runs panel

## Format Tips

- PNG is best for static screenshots.
- GIF is fine for the CLI slot if you want motion.
- Keep widths around 1200px so GitHub renders them crisply.
- Crop out personal bookmarks, tabs, usernames, and system notifications.
