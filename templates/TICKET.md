# Ticket template

The ticket description is the prompt. Four parts, in this order:

```
Outcome: one sentence: what exists when it's done.
Done means: 2 to 4 checks a command or screenshot proves.
Not allowed: files and shortcuts that are off-limits. Never edit the checks.
Proof: paste the check command's full output.
```

One change per ticket. If it needs two outcomes, write two tickets.

## Example: a bakery menu page

```
Title: Menu page for Rosa's Bakery

Outcome: index.html shows the menu and hours from content.md, styled by style.css.

Done means:
- Every item and price on the page is word for word from content.md.
- No sideways scroll at 320px wide; screenshots at 390px and 1280px attached.
- python3 checks/verify_page.py . --content content.md exits 0 with no FAIL.

Not allowed:
- Editing content.md, checks/, AGENTS.md or anything under .github/.
- JavaScript, new dependencies, fonts or images from other sites.
- New prices, dishes or claims ("best in town") that aren't in content.md.

Proof: paste the checker's full output and attach the two screenshots.
```

## Example: proving CI can fail

```
Outcome: a throwaway PR shows the PR checks go red on a broken page, then green.
Done means: one commit breaks a link and the run is red; a revert makes it green;
  both run links are in your final message; the PR is closed, not merged.
Not allowed: new excludes, continue-on-error, or any edit to the workflow.
Proof: the two run links and the failing step's log line.
```

Untested: Fredrin's site says "Fix CI is on by default for new projects" (https://www.fredrin.com/vs/sculptor), so the red run may be sent straight back to a Worker to fix. Watch for that.
