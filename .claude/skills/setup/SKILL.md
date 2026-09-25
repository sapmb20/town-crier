---
name: setup
description: "Configure this event scanner through a short survey: city, interests in priority order, events to exclude, schedule, and email delivery. Writes config.yaml and the workflow schedule, then walks through secrets and a dry run. Use when the user says /setup, 'configure the scanner', 'set this up', or 'change my interests'."
---

# Set up Town Crier

You are configuring a copy of this template for one person. The result is a `config.yaml` (the
format is documented in `config.example.yaml`), a schedule line in
`.github/workflows/scanner.yml`, and the four secrets the workflow needs.

If `config.yaml` already exists, read it first. Treat this as an edit: ask only about what the
user wants to change, and show a before/after of the fields you touch.

## 1. Survey

Ask with the AskUserQuestion tool, up to 4 questions per call, and offer concrete options with
an "Other" escape. Don't make the user type long text when options will do. Cover:

1. **Where:** the metro region, and which nearby towns they'd actually travel to.
2. **Who:** one sentence about the reader (role or stage, what they want out of events).
3. **Interests, in priority order:** 2–5 categories. For each, what counts: for example, "hands-on
   workshops only" or "industry-side events, not consumer ones". Ask them to rank the list.
4. **Exclusions:** organizers or kinds of events to never recommend. Prompt with examples: free
   seminars that upsell a course, brand-hosted retail "experiences", recurring events they've
   already been to.
5. **Schedule:** day of week and local time, plus their time zone.
6. **Look-ahead window** (2, 4 or 6 weeks), **digest name**, and **quote themes** (or no quote).
7. **Model:** default `claude-opus-5`. Offer `claude-sonnet-5` as the cheaper option. Don't pick
   the cheaper one on their behalf.

## 2. Write the files

- Write `config.yaml`, using `config.example.yaml`'s key names and comments.
- Convert the chosen local day and time to **UTC** and rewrite the `cron:` line in
  `.github/workflows/scanner.yml`. Tell the user that GitHub cron is UTC, so the local time
  shifts by an hour when daylight saving changes.
- `config.yaml` is committed, because the workflow reads it from the repo. **If the repo is public,
  everything in it is public.** Say so, and keep names, emails and anything private out of it.
  The email addresses go in secrets only.

## 3. Secrets and delivery

The digest is sent from a Gmail account using an **app password** (Google Account → Security →
2-Step Verification → App passwords). Never ask the user to paste a password or API key into
the chat. Tell them where each value goes:

| Secret | Value |
|---|---|
| `ANTHROPIC_API_KEY` | from console.anthropic.com |
| `GMAIL_ADDRESS` | the sending Gmail address |
| `GMAIL_APP_PASSWORD` | the 16-character app password |
| `RECIPIENT_EMAIL` | where the digest goes |

- For GitHub Actions, the values go under repo **Settings → Secrets and variables → Actions**. If the `gh`
  CLI is installed and authenticated, the user can run `gh secret set NAME` themselves; it
  prompts for the value.
- For local runs, the same four go in `.env`, which is already in `.gitignore`. Check that it is
  still ignored before they create it.

## 4. Test

1. `pip install -r requirements.txt`
2. `python scanner.py --dry-run` prints the digest without sending email. It needs only
   `ANTHROPIC_API_KEY`. Read it with the user:
   check whether the categories are right and whether anything excluded slipped through.
   Tighten `exclude` or the interest `focus` lines if so.
3. Commit `config.yaml` and the workflow change, then push.
4. Trigger a real run from the repo's **Actions** tab (**Run workflow**) and confirm the email
   arrives.

A dry run makes real API calls with web search, so it costs a little. Say that before running it.
