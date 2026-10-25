# AGENTS.md: rules for any agent working in this repo

<One sentence: what this repo is and who it's for.> Read this file before every ticket.

<!-- Copy to the repo root, replace every <placeholder>, delete lines that don't apply.
     Then: ln -s AGENTS.md CLAUDE.md  (one source of truth).
     Add one line every time the agent makes a mistake you don't want twice. -->

## Facts
- Every name, date, price and number comes from `content.md`. Nothing is added, rounded or reworded.
- Never edit `content.md`. If something there looks wrong, say so in your final message and stop.
- <Name or brand> is always spelled "<exact spelling, accents included>".

## Stack
- <Languages and files allowed, e.g. "Plain HTML and CSS: index.html + style.css. No build step.">
- <What's banned, e.g. "No JavaScript. No new dependencies. Nothing loads from another site.">
- <Where it runs, e.g. "Published by GitHub Pages from main, root folder.">

## Design bar
- The look is defined in `DESIGN.md`. Follow it exactly; don't invent a different style.
- <Hard numbers, e.g. "Body text 18-20px, lines no wider than about 65 characters.">
- <Accessibility, e.g. "Text contrast at least 4.5:1 in light and dark. Exactly one h1. lang set.">
- <Phones, e.g. "No sideways scroll at 320px wide. Tap targets at least 24px.">

## Done means
Run the check and paste its full output in your final message:

```
<your check command, e.g. python3 checks/verify_page.py . --content content.md>
```

Fix every FAIL before finishing. List every WARN and say why it's acceptable or what you changed.
<Optional: "Attach screenshots at 390px and 1280px wide, light and dark.">

## Never
- Never edit, skip or weaken the checks (`checks/`), tests or CI to make them pass.
- Never touch files the ticket doesn't need.
- Never run `git stash` (it's shared across every worktree).
- Don't assume. If the ticket is unclear, ask before building.
