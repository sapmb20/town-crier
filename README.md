# Town Crier

A town crier walked the square announcing what was happening that week. This one sends you a
weekly email digest of in-person events near you, picked to match your interests. Claude
searches the web for events over the next few weeks. It groups them by your priorities,
explains why each one is worth your time, and names the single best one to act on.

Everything personal lives in one file, `config.yaml`: your city, what you care about in
priority order, and what to never recommend. The template ships without it, and the
scheduled workflow stays idle until it exists.

## Set up with Claude Code (recommended)

1. Click **Use this template** on GitHub, or fork it, and clone your copy.
2. Open the folder in [Claude Code](https://claude.com/claude-code) and run `/setup`.
3. Answer the survey. Claude writes `config.yaml` and your schedule, then walks you through
   the secrets and a test run.

## Set up by hand

1. Copy `config.example.yaml` to `config.yaml` and edit it.
2. Set the schedule in `.github/workflows/scanner.yml`. GitHub cron runs in UTC.
3. Add these repository secrets under **Settings → Secrets and variables → Actions**:
   `ANTHROPIC_API_KEY`, `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` (a Gmail
   [app password](https://myaccount.google.com/apppasswords)), `RECIPIENT_EMAIL`.
4. Test locally: put `ANTHROPIC_API_KEY` in `.env` (a dry run needs only that), then run
   ```
   pip install -r requirements.txt
   python scanner.py --dry-run
   ```
5. Commit `config.yaml`, push, and trigger a run from the **Actions** tab.

## Notes

- **`config.yaml` is committed**, because the workflow reads it from the repo. In a public repo it
  is public, so keep personal details in secrets, not in the config.
- **Exclusions work best when they're specific.** If the digest keeps suggesting something you
  don't want, name the organizer in `exclude`.
- **Cost:** each run is one Claude request with up to 10 web searches. `model` in the config
  picks the Claude model. `claude-sonnet-5` is cheaper than the default `claude-opus-5`.
