import os
import re
import smtplib
import sys
import anthropic
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from pathlib import Path
import yaml
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

CONFIG_PATH = Path(__file__).parent / "config.yaml"
if not CONFIG_PATH.exists():
    sys.exit("config.yaml not found. Run /setup in Claude Code, or copy config.example.yaml to config.yaml.")
CONFIG = yaml.safe_load(CONFIG_PATH.read_text())

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
# Email settings are only needed to send; --dry-run works without them.
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL")
if not ANTHROPIC_API_KEY:
    sys.exit("ANTHROPIC_API_KEY is not set. Add it to .env or the repo's Actions secrets.")

MODEL = CONFIG.get("model", "claude-opus-5")
DIGEST_NAME = CONFIG.get("digest_name", "The Town Crier")
TAGLINE = CONFIG.get("tagline", "your local edge, delivered.")
MAX_CONTINUATIONS = 5


def build_prompts(config: dict) -> tuple[str, str]:
    interests = config["interests"]
    priority = "\n".join(
        f"{i}. {item['name']}" + (f": {item['focus']}" if item.get("focus") else "")
        for i, item in enumerate(interests, 1)
    )
    exclusions = "\n".join(f"- {e}" for e in config.get("exclude", []))
    themes = config.get("quote_themes", [])

    system = f"""You are a personal event curator for {config['reader']} in {config['region']}.
Your reader's interests, in priority order:
{priority}

Never recommend these, even if they match an interest:
{exclusions or "- (none)"}

Write in a concise, warm, intelligent tone. Surface only real, confirmed events.
The entire digest must be readable in 10 minutes or less. Do not fabricate details.
Never use em dashes (—) except to attribute a quote to its author. Rephrase all other sentences to read naturally without them.
Never use markdown horizontal rules (---) anywhere in your response."""

    headers = "\n".join(f"## {item['name']}" for item in interests)
    quote = (
        f"One short powerful quote on {', '.join(themes)}.\n"
        'Format exactly as: "Quote text." — Author Name'
        if themes else "Leave this section empty."
    )

    user = f"""Today is {date.today().strftime('%B %d, %Y')}.

Search for in-person events in {config['region']} ({', '.join(config['areas'])}, and nearby) over the next {config.get('window_weeks', 4)} weeks.

Output your response using EXACTLY these four section markers on their own lines:

[QUOTE]
{quote}

[SUMMARY]
2–3 sentences. What is the highlight of this week's scan? Why should the reader pay attention?

[EVENTS]
List relevant events found. Group them under these category headers (only include a category if events were found):

{headers}

For each event use this exact format:

**Event Name**
📅 Date & Time | 📍 Venue, City | 💰 Cost
- Why this matches the reader's interests (be specific)
- What makes it stand out or worth attending
- Notable speakers, exhibitors, or networking potential
🔗 https://url-here.com

[RECAP]
2–3 sentences naming the single best action item from this week — the one event most worth the reader's time and why."""
    return system, user


def run_scan() -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system, user = build_prompts(CONFIG)
    print("Scanning for events...")

    messages = [{"role": "user", "content": user}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 10}]
    # Opus 5 and Fable can decline a request; fallbacks re-run it on another model server-side.
    fallback = {}
    if MODEL.startswith(("claude-opus-5", "claude-fable")):
        fallback = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}

    for _ in range(MAX_CONTINUATIONS + 1):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=64000,
            system=system,
            tools=tools,
            messages=messages,
            **fallback,
        ) as stream:
            response = stream.get_final_message()

        # Web search runs server-side; a long search loop pauses and resumes from the same turn.
        if response.stop_reason == "pause_turn":
            messages = [
                {"role": "user", "content": user},
                {"role": "assistant", "content": response.content},
            ]
            continue
        if response.stop_reason == "refusal":
            sys.exit(f"Scan declined: {response.stop_details}")
        return "\n".join(b.text for b in response.content if b.type == "text")

    sys.exit(f"Scan did not finish after {MAX_CONTINUATIONS} continuations.")


def clean_text(text: str) -> str:
    """Remove stray markdown horizontal rules and trim blank lines they leave behind."""
    lines = [l for l in text.splitlines() if l.strip() not in ("---", "***", "___")]
    return "\n".join(lines)


def inline_md(text: str) -> str:
    """Convert **bold** markdown to HTML <strong> tags (call after html.escape)."""
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)


def parse_sections(text: str) -> dict:
    markers = ["[QUOTE]", "[SUMMARY]", "[EVENTS]", "[RECAP]"]
    sections = {}
    for i, marker in enumerate(markers):
        start = text.find(marker)
        if start == -1:
            sections[marker] = ""
            continue
        start += len(marker)
        end = len(text)
        for next_marker in markers[i + 1:]:
            pos = text.find(next_marker, start)
            if pos != -1:
                end = pos
                break
        sections[marker] = text[start:end].strip()
    return sections


def events_to_html(text: str) -> str:
    lines = text.splitlines()
    out = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        if stripped in ("---", "***", "___"):
            continue

        elif stripped.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            label = escape(stripped[3:])
            out.append(
                f'<p style="margin:32px 0 10px;font-family:Arial,sans-serif;font-size:10px;'
                f'letter-spacing:3px;text-transform:uppercase;color:#8b7355;'
                f'padding-bottom:8px;border-bottom:1px solid #e8e0d5;">{label}</p>'
            )

        elif re.match(r'^\*\*.+\*\*$', stripped):
            if in_list:
                out.append("</ul>")
                in_list = False
            name = escape(stripped[2:-2])
            out.append(
                f'<p style="margin:20px 0 4px;font-family:Georgia,serif;font-size:17px;'
                f'font-weight:bold;color:#1c1c1c;">{name}</p>'
            )

        elif any(e in stripped for e in ["📅", "📍", "💰"]):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(
                f'<p style="margin:0 0 8px;font-family:Arial,sans-serif;font-size:12px;'
                f'color:#777;line-height:1.7;">{escape(stripped)}</p>'
            )

        elif stripped.startswith("- "):
            if not in_list:
                out.append(
                    '<ul style="margin:6px 0 10px;padding-left:18px;">'
                )
                in_list = True
            out.append(
                f'<li style="font-family:Arial,sans-serif;font-size:13px;color:#444;'
                f'line-height:1.75;margin-bottom:4px;">{inline_md(escape(stripped[2:]))}</li>'
            )

        elif stripped.startswith("🔗"):
            if in_list:
                out.append("</ul>")
                in_list = False
            url = escape(stripped[1:].strip())
            out.append(
                f'<p style="margin:8px 0 24px;">'
                f'<a href="{url}" style="font-family:Arial,sans-serif;font-size:12px;'
                f'color:#8b7355;text-decoration:none;border-bottom:1px solid #c9b99a;">'
                f'View Event &rarr;</a></p>'
            )

        elif stripped == "":
            if in_list:
                out.append("</ul>")
                in_list = False

    if in_list:
        out.append("</ul>")

    return "\n".join(out)


def build_html(quote: str, summary: str, events_html: str, recap: str) -> str:
    issue = date.today().isocalendar()[1]
    today = date.today().strftime("%b %d, %Y").upper()

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background-color:#f0ebe3;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f0ebe3;">
  <tr><td align="center" style="padding:40px 16px;">
    <table width="600" cellpadding="0" cellspacing="0" border="0"
           style="max-width:600px;width:100%;background:#ffffff;">

      <!-- HEADER BAR -->
      <tr><td style="background:#1c1c1c;padding:22px 40px;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="color:#c9b99a;font-family:Arial,sans-serif;font-size:10px;
                       letter-spacing:3px;text-transform:uppercase;">
              {escape(DIGEST_NAME)}
            </td>
            <td align="right" style="color:#c9b99a;font-family:Arial,sans-serif;
                                     font-size:10px;letter-spacing:1px;">
              #{issue} &nbsp;|&nbsp; {today}
            </td>
          </tr>
        </table>
      </td></tr>

      <!-- TITLE -->
      <tr><td align="center" style="padding:52px 40px 36px;">
        <p style="margin:0 0 8px;font-family:Arial,sans-serif;font-size:10px;
                  letter-spacing:3px;color:#8b7355;text-transform:uppercase;">
          Welcome to your
        </p>
        <h1 style="margin:0;font-family:Georgia,serif;font-size:46px;
                   font-weight:normal;color:#1c1c1c;line-height:1.1;">
          Weekly Digest
        </h1>
        <p style="margin:12px 0 0;font-family:Georgia,serif;font-style:italic;
                  font-size:15px;color:#8b7355;">
          {escape(TAGLINE)}
        </p>
        <div style="margin:28px auto 0;width:36px;height:2px;background:#1c1c1c;"></div>
      </td></tr>

      <!-- QUOTE -->
      <tr><td style="padding:0 40px 40px;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td style="border-left:3px solid #c9b99a;padding:14px 22px;
                       background:#faf7f2;">
              <p style="margin:0;font-family:Georgia,serif;font-style:italic;
                        font-size:16px;color:#1c1c1c;line-height:1.75;">
                {escape(quote)}
              </p>
            </td>
          </tr>
        </table>
      </td></tr>

      <tr><td style="padding:0 40px;">
        <div style="height:1px;background:#e8e0d5;"></div>
      </td></tr>

      <!-- SUMMARY -->
      <tr><td style="padding:36px 40px;">
        <p style="margin:0 0 14px;font-family:Arial,sans-serif;font-size:10px;
                  letter-spacing:3px;color:#8b7355;text-transform:uppercase;">
          This Week at a Glance
        </p>
        <p style="margin:0;font-family:Arial,sans-serif;font-size:14px;
                  color:#333;line-height:1.85;">
          {inline_md(escape(summary))}
        </p>
      </td></tr>

      <tr><td style="padding:0 40px;">
        <div style="height:1px;background:#e8e0d5;"></div>
      </td></tr>

      <!-- EVENTS -->
      <tr><td style="padding:36px 40px 20px;">
        <p style="margin:0 0 20px;font-family:Arial,sans-serif;font-size:16px;
                  letter-spacing:3px;color:#8b7355;text-transform:uppercase;
                  text-align:center;">
          Events &amp; Opportunities
        </p>
        {events_html}
      </td></tr>

      <tr><td style="padding:0 40px;">
        <div style="height:1px;background:#e8e0d5;"></div>
      </td></tr>

      <!-- RECAP -->
      <tr><td style="padding:36px 40px 52px;">
        <p style="margin:0 0 14px;font-family:Arial,sans-serif;font-size:10px;
                  letter-spacing:3px;color:#8b7355;text-transform:uppercase;">
          Your Action Item This Week
        </p>
        <p style="margin:0;font-family:Arial,sans-serif;font-size:14px;
                  color:#333;line-height:1.85;">
          {inline_md(escape(recap))}
        </p>
      </td></tr>

      <!-- FOOTER -->
      <tr><td style="background:#1c1c1c;padding:22px 40px;text-align:center;">
        <p style="margin:0;font-family:Arial,sans-serif;font-size:10px;
                  color:#555;letter-spacing:1px;">
          {escape(DIGEST_NAME)} &nbsp;&middot;&nbsp; Powered by Claude
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def send_email(digest: str) -> None:
    missing = [n for n in ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "RECIPIENT_EMAIL") if not os.environ.get(n)]
    if missing:
        sys.exit(f"Cannot send email, missing: {', '.join(missing)}. Use --dry-run to preview instead.")
    sections = parse_sections(clean_text(digest))
    quote = sections.get("[QUOTE]", "")
    summary = sections.get("[SUMMARY]", "")
    events_text = sections.get("[EVENTS]", "")
    recap = sections.get("[RECAP]", "")

    events_html = events_to_html(events_text)
    html = build_html(quote, summary, events_html, recap)

    issue = date.today().isocalendar()[1]
    subject = f"{DIGEST_NAME} #{issue} — {date.today().strftime('%B %d, %Y')}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(digest, "plain"))
    msg.attach(MIMEText(html, "html"))

    print("Sending email digest...")
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())
    print(f"Email sent to {RECIPIENT_EMAIL}")


if __name__ == "__main__":
    digest = run_scan()
    if "--dry-run" in sys.argv:
        print(digest)
        sys.exit(0)
    print("\n--- DIGEST PREVIEW ---")
    print(digest[:600], "...\n")
    send_email(digest)
    print("Done.")
