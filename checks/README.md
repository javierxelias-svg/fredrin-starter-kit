# checks/

A checker the agent runs and never edits. It reads a static page and compares it with the facts you wrote.

```
python3 checks/verify_page.py . --content content.md
```

It never edits the page. It runs six checks and writes a receipt to `checks/receipts/` (not committed):

1. **Facts:** every number, date and "X of Y" on the page must appear in `content.md`. An invented or rounded number is a FAIL. Sentences that aren't word for word are a WARN.
2. **Links:** every local file and `#anchor` exists, outside links answer and open in a new tab with `rel="noopener"`. If `facts.json` sets `email`, every `mailto:` must use it.
3. **HTML basics:** doctype, `lang`, title, viewport, exactly one `h1`, alt text, no scripts loaded from other sites.
4. **Render:** headless Chrome screenshots at 390 and 1280px; no sideways scroll at 320 or 390px.
5. **Contrast:** the colors Chrome actually computed, 4.5:1 target (WARN only).
6. **Size:** the page weight.

Exit codes: `0` = PASS or WARN only, `1` = something FAILed, `2` = couldn't start (for example, no page yet).

Needs Python 3 (standard library only). Check 4 needs Chrome or Chromium: the macOS default path, `google-chrome` / `chromium` on your PATH, or `CHROME=/path/to/chrome`.

## Set it up
1. Fill in `facts.json`: the exact spelling of your name, misspellings to catch, claims the page must never make.
2. Run it before any page exists. It should print `ERROR: no page found` and exit 2. Save that output in `history/`: it's your proof the check can fail.
3. Record its fingerprint: `shasum -a 256 checks/verify_page.py > checks/history/checker-sha256.txt`. If the hash changes in a PR, someone edited the grader.

## History
- `history/2026-10-25-sample-PASS.txt`: the sample page in `examples/sample-page/` passes.
- `history/2026-10-25-sample-FAIL.txt`: a deliberately broken copy (`broken.html`) fails: an invented price, a misspelled name, a banned claim and a missing CSS file.

Adapted from the checker in [javierxelias-svg/about-me](https://github.com/javierxelias-svg/about-me/tree/main/checks).
