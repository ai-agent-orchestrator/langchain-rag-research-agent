files: docs/NIGHTCODER_SMOKE.md
forbid: src/**, tests/**, data/**, profiles/**, pyproject.toml, .env*
effort: low
coder: codex

# Smoke: NightCoder start check (1-2 minutes)

This spec only proves that the coder can run, edit a file and commit in this lane.

1. Create or overwrite `docs/NIGHTCODER_SMOKE.md` with exactly two lines:
   `# NightCoder smoke`
   `ok: <current UTC time in ISO format>`
2. Run `git add docs/NIGHTCODER_SMOKE.md` and `git commit -m "chore: nightcoder smoke"`.
3. Do nothing else. Do not touch any other file. Report the commit hash.
