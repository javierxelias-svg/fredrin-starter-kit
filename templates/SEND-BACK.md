# Sending work back

Reject with a constraint, not a mood. "It doesn't feel right" gives the agent nothing to check.

Each line of a send-back should be:
- **One thing.** Split "fix the header and the colors" into two lines.
- **Checkable.** You can see it in a screenshot or a command output.
- **Located.** Name the section, file or screen width.
- **Sourced.** If it's a fact, point at `content.md`. If it's a look, point at `DESIGN.md`.

End with the proof you want back. Two send-backs on the same ticket that don't fix it: close it and write a sharper ticket.

## Example (the bakery menu page)

```
Sending back. Fix these, then paste the checker output and attach new screenshots:

1. The croissant shows $3.75; content.md says $3.50. Use content.md.
2. "The best bread in town" isn't in content.md. Remove it.
3. At 390px wide, the hours paragraph runs off the right edge. No sideways scroll at 320px.
4. Prices sit on their own line under each item. Put each price on the same line as its item.
5. style.css changed the body text to 15px. DESIGN.md says 19px.

Don't touch content.md, checks/ or AGENTS.md.
```
