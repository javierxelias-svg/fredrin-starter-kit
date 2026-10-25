# Your first hour with Fredrin on a new repo

> Built from one real run on 2026-10-24 (Fredrin 0.58.0, macOS, repo `javierxelias-svg/about-me`). One repo, one day: a field note, not a benchmark.

## Why this exists

My first Fredrin ticket opened PR #1 at 17:15:03Z, and PR #1 merged itself at 17:15:41Z (GitHub records the merge under my account, because Fredrin acts with my GitHub access). That's 38 seconds, with 0 reviews. I never saw the diff. Fredrin's quickstart says "Read the diff. That is the job." The FAQ says "Nothing reaches your base branch until you merge". Both are true only if you set things up first. The approval gates are "off by default and both are per project" (https://www.fredrin.com/docs/board/review), and my repo had no CI. This checklist is the setup I wish I'd done before that ticket. On 2026-09-25 the founder wrote that a best-practices guide is needed but "we just don't have the resource to do them right now" (https://www.fredrin.com/community/general/cmueg3wyj00000agm1d9lg5mm). Here's one user's attempt.

## The checklist

Each item gives the action, why it matters, and what happened on my run. The minutes are the order I'd use, not times I measured.

**Minute 0: give GitHub access to selected repositories only.**
- Why: "You can grant access to selected repositories rather than all of them. Fredrin only needs the ones you intend to run tickets against." (https://www.fredrin.com/docs/github)
- My run: the screen recommends "All repositories", and GitHub also preselects it. I picked "Only select repositories" by hand.
- Before you start: an empty repo has nothing to branch from, so make one commit first (a README is enough). Push AGENTS.md and your check straight to `main` before you turn on branch protection. After granting access in the browser, switch back to the Fredrin app: the next step waits there.

**Minute 5: set the Merge approval gate to 1 before the first ticket.**
- Why: the Merge gate "Requires N approvals of the *diff* before any merge path proceeds" (docs/board/review). Leave it at 0 and nobody has to approve.
- Where: gates are project settings (https://www.fredrin.com/docs/settings) [Javier: your click path]. Also check the card says Manual merge. Fredrin "merges by itself once checks pass if you let it" (https://www.fredrin.com/vs/nimbalyst).
- My run: I set it after PR #1, not before. PR #1 merged in 38 s. I reverted it in `facb7d5`. With the gate at 1, PR #2 opened at 17:47:54Z and was still unmerged at 21:47Z, waiting for me. [UPDATE AFTER MERGE: PR #2 merged at __:__Z after my GitHub review]

**Minute 10: write AGENTS.md and point CLAUDE.md at it.**
- Why: "Point `CLAUDE.md` at it with a symlink and you have one source of truth." (https://www.fredrin.com/docs/memory/writing)
- What goes in it ([my AGENTS.md](https://github.com/javierxelias-svg/about-me/blob/main/AGENTS.md)): facts (where the truth lives and what can't be reworded), stack (what's allowed), done means (the command to run and the output to paste), and never (no weakening checks, no `git stash`: "never run `git stash` in a worktree", https://www.fredrin.com/docs/board/worktrees).
- My run: AGENTS.md in `526dfcb`, CLAUDE.md symlinked in `adbee44` (git mode `120000`). I ran the same ticket without and with it. The version with AGENTS.md followed 4 rules the first one missed: dark mode, 19px body text, a 65-character line length, and semantic header/main/footer. It also dropped a meta description the first one had. One run each, so read that as a signal, not proof.

**Minute 20: add a check that fails before any code exists.**
- Why: if the check can't fail, a pass tells you nothing.
- My run: my page checker ([`checks/verify_page.py`](https://github.com/javierxelias-svg/about-me/blob/main/checks/verify_page.py); on run day it ran from outside the repo) printed `ERROR: no page found` before the first ticket ([first run](https://github.com/javierxelias-svg/about-me/blob/main/checks/history/2026-10-24-1259-before-any-code.txt)). After both runs it reported 0 FAIL and 1 WARN (LinkedIn blocks bots, so I opened that link by hand). I also compared the checker's SHA-256 before and after the run: same hash, so the grader didn't change during the run. The copy now in the repo still has that hash ([record](https://github.com/javierxelias-svg/about-me/blob/main/checks/history/2026-10-24-1349-checker-sha256.txt)).

**Minute 30: add CI on pull requests so "green" means something.**
- Why: "If a branch requires reviews or passing checks, Fredrin's merge path is subject to them exactly as a human's would be." (docs/github). With no CI, "green" proves nothing.
- My run: **tested locally only, not on GitHub yet.** I had four checks built: no JavaScript or outside loads, valid HTML, working links, and accessibility in light *and* dark. Each check failed on a deliberately broken copy, then passed after the revert. One finding: headless Chrome follows the machine's theme, so a dark-only contrast bug can slip through unless you test both themes on purpose. Branch protection isn't on yet, so nothing blocks a merge today.
- How: on GitHub, Settings → Branches (or Rules → Rulesets), protect `main` and require your CI check. Working alone? Don't require approvals: "Pull request authors cannot approve their own pull requests" (GitHub docs), and Fredrin opens PRs under your account. A green pill alone isn't CI: Workers report their own checks' exit codes, "which stamp CI status on the board's PR pill" (https://www.fredrin.com/faq).

**Minute 40: write tickets as outcome / done means / not allowed / proof.**
- Why: "The ticket description is the prompt. It is the single highest-leverage thing you control" (https://www.fredrin.com/docs/workers/prompting).

  Ticket template:
  ```
  Outcome: one sentence: what exists when it's done.
  Done means: 2 to 4 checks a command or screenshot proves.
  Not allowed: files and shortcuts that are off-limits. Never edit the checks.
  Proof: paste the check command's full output.
  ```
- My run: my CI ticket draft uses this shape. Done means includes a throwaway PR that has to go red and then green, and not allowed includes "no new excludes, no `continue-on-error`". It hasn't been sent yet.

**Minute 50: review the diff and screenshots, and send back with checkable criteria.**
- Why: "Reject with a specific constraint rather than a mood." (https://www.fredrin.com/blog/ai-code-review)

  Review checklist: every Done means line has pasted proof; nothing invented (names, numbers, claims); no file outside the ticket changed, including AGENTS.md and checks; nothing new loaded or installed; you opened the result yourself. Then merge on GitHub (leave a Comment review); the card moves to Completed.
- My run: both builds passed every check. The rules made the agent follow the standards, but neither page looked like me. I wrote the look down in DESIGN.md (`abbe230`) and sent the build back with 8 items, each visible in a screenshot (for example "each project's big number shows WITHOUT clicking"). PR #2 then got a rebuild from DESIGN.md (`a46046a`), then a rebuild in the approved design (`fbeb387` on main, `462d5ee` on the PR). [UPDATE AFTER MERGE: final commit and number of send-backs] [UPDATE AFTER MERGE: my GitHub review (link) and merge time]

**Next:** a weekly watchdog that opens an issue and never merges. [UPDATE AFTER MERGE: live at https://javierxelias-svg.github.io/about-me/ since __]

## What I'd change in Fredrin

- **Make the first ticket of a new project Manual merge, or warn "this will merge without review".** Today the defaults contradict "Nothing reaches your base branch until you merge".
- **Put an Approve button next to "Needs 1 more approval to start building".** With the Build gate at 1, I couldn't find where to approve, so I set it back to 0.
- **Say whether project context changes when a Worker asks.** The docs say a Worker that hits "a decision only a human can make asks the question and waits" (https://www.fredrin.com/docs/workers/blocked). My AGENTS.md says "If the ticket is unclear, ask before building." In a normal run, does my rule win?

Receipts: PR timings come from `gh pr list -R javierxelias-svg/about-me`. Commit SHAs are in that repo's history. The checker and its first failing run are in [`checks/`](https://github.com/javierxelias-svg/about-me/tree/main/checks). The CI and watchdog logs are available on request.

## Use this kit in your repo

Copy in this order. Commit steps 1 to 4 to `main` yourself, before the first ticket.

1. `templates/content.md` → `content.md` at your repo root. Write your facts first.
2. `templates/AGENTS.md` → `AGENTS.md`, then `ln -s AGENTS.md CLAUDE.md`. If the look matters, `templates/DESIGN.md` → `DESIGN.md`.
3. `checks/verify_page.py` and `checks/facts.json` → `checks/`. Fill `facts.json`, run it before any page exists, save the failure in `checks/history/`. It checks static HTML; for anything else, use your own check that fails first.
4. `templates/github/` → `.github/` in your repo (the `pr-checks.yml` workflow and its three `.json` configs). Tested locally (red→green); not yet run on GitHub. Then protect `main` (Minute 30).
5. Tickets: `templates/TICKET.md`. Before merging: `templates/REVIEW-CHECKLIST.md`. Sending back: `templates/SEND-BACK.md`.

`examples/sample-page/` passes the checker and its `broken.html` fails it (outputs in `checks/history/`). Try it: `python3 checks/verify_page.py examples/sample-page --content examples/sample-page/content.md --facts examples/sample-page/facts.json`. Worked example: [about-me](https://github.com/javierxelias-svg/about-me).

Drafted with Claude, checked and decided by me.
