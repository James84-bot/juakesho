# Working on this repo together

Two assistants work on Kenya on Record, plus James:

- **Cloud side**: works in a copy of this repo in the cloud, writes the pipeline code, and runs and checks it live
  on GitHub Actions. It cannot reach James's computer.
- **Local side**: runs in PowerShell on James's computer. Does whatever needs his machine or his accounts: setting
  GitHub secrets with James at the keyboard, anything on his desktop, and a second look at changes.
- **James** decides. Anything public that can't be undone (deleting a post, posting by hand) waits for his yes.

We talk through this file: write what you did, what you found, and what you need from the other side in the log at
the bottom, newest first. Pull before you read it.

## Rules for both sides

- Commit as `James Ndaiga <jamesndaiga84@gmail.com>`. No co-author or session lines in commits or PRs.
- `git pull --rebase` before pushing. Never force-push or rewrite history.
- Tests must pass before a push: `cd automation` then `python -m unittest discover -s tests`. They need no network.
- Keys and tokens live only in GitHub secrets. Never in a file, a commit, a log or a chat message.
- Don't start an autopilot run while another one is waiting to start: GitHub keeps one waiting run, and a newer
  one cancels it. Check with `gh run list -R James84-bot/juakesho --workflow autopilot.yml -L 3`.
- Start a run with `gh workflow run autopilot.yml -R James84-bot/juakesho -f command="<command>"`.
- No cost: only free services. The paid Claude API stays off (repository variable `JUA_PAID_OK` is not set).
- Test claims with data, and don't state anything unverified as fact.

## How the system runs (short)

- `.github/workflows/listener.yml` runs all the time. It answers Telegram taps and keeps the clock: the four daily
  news editions, breaking-news checks, the two-hourly tick, and the weekly runs.
- `.github/workflows/autopilot.yml` does the work: `python automation/pipeline.py <command>`.
- Posts and their state are in `automation/content/weeks/<year>-W<week>.json`. Renders are in `docs/exports/`.
- The writer uses Google's free Gemini models, then the free backups (Mistral, Groq, OpenRouter) once their keys
  are secrets. `aicheck --dry-run` tests every one of them live.

## Open task for the local side

Add the three free backup keys, with James at the keyboard. Each is free with no card:

1. James creates a key at console.mistral.ai, console.groq.com and openrouter.ai.
2. For each one, run the command below. It asks for the value and hides it; James pastes the key there:
   - `gh secret set MISTRAL_API_KEY -R James84-bot/juakesho`
   - `gh secret set GROQ_API_KEY -R James84-bot/juakesho`
   - `gh secret set OPENROUTER_API_KEY -R James84-bot/juakesho`
3. Start `aicheck --dry-run` (see the rules above). When it finishes, copy the log lines that start with
   `aicheck Mistral`, `aicheck Groq` and `aicheck OpenRouter` into the log below. The keys themselves never go there.

## Log

### 2026-11-22 (cloud side)
- SHA cancer-cover Reel (published 09:47) showed Al-Shabaab fighters and an unrelated official: other reports were
  matched by "SHA" inside "Al-Shabaab". Fixed: names match whole words, and every picture from another report is
  checked by the AI against the story before use. The photo audit re-checks posts waiting to go out.
  Waiting on James: take the SHA Reel down and repost it? (Facebook and YouTube from here; Instagram by hand.)
- A post about a person now uses their picture: searched by the name the post uses (Bien), then reports naming
  them, then their own recent Instagram posts (username from Wikidata), then Wikimedia Commons.
