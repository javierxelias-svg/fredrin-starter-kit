# DESIGN.md: the look, written down

Rules make an agent follow standards. They don't make it match a look. Write the look as numbers and pictures it can check.

<!-- Copy to the repo root. Replace every <placeholder>. Every line should be something
     you could point at in a screenshot. Words like "clean" or "modern" don't count. -->

**Reference:** <screenshots in design/ (phone and desktop, light and dark)>. Match them.

**In one line:** <the look in one sentence, plus what it must never look like.>

## Type
- <Font for body text>: <size>px, weight <n>, line height <n>.
- Headings: h1 <size>, h2 <size>. Only <n> sizes and <n> weights on the page.

## Color and themes
- Background <hex> (light) and <hex> (dark). Text <hex> / <hex>. One accent: <hex>.
- Theme follows `prefers-color-scheme`. <Switch, if any: where and how it looks.>

## Layout
- Max width <n>px. Text column about 65 characters. Spacing steps: <e.g. 8, 16, 24, 48px>.
- Phone (390px): <what stacks, what hides>. Desktop (1280px): <columns>.

## States
- Links: <normal, hover, focus>. Focus outline always visible.
- <Buttons, open/closed sections, empty states.>

## Never
- <The looks you've rejected, e.g. "no gradients on text, no stock photos, no icon libraries".>
