# Project rules for Claude

- Do not run `git commit`, `git push`, or `git add`. The user does all of that.
- Never add Claude as a co-author or contributor anywhere. No `Co-Authored-By` lines, no `Claude-Session` lines, and no "Generated with Claude Code" text in commits, files, or the README.
- Commit and pull request attribution is turned off in `.claude/settings.json`. Do not turn it back on.
- A `commit-msg` hook at `.git/hooks/commit-msg` removes any Claude attribution lines from commit messages. It must keep LF line endings.
