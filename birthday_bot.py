import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from tabulate import tabulate

# ---- CONFIG (via env) ----
SLACK_TOKEN = os.environ["SLACK_TOKEN"]
SOURCE_CHANNEL_ID = os.environ["SOURCE_CHANNEL_ID"]          # channel to scan members from
ANNOUNCE_CHANNEL_ID = os.environ["ANNOUNCE_CHANNEL_ID"]      # channel to post public message in
BIRTHDAY_FIELD_ID = os.environ.get("BIRTHDAY_FIELD_ID", "Xf05STPV0Z3R")
PROFILE_DELAY = float(os.environ.get("PROFILE_FETCH_DELAY_SECONDS", "0.2"))
TZ = os.environ.get("TZ_NAME", "Europe/Lisbon")

DM_TEMPLATE = os.environ.get(
    "DM_TEMPLATE",
    "Happy Birthday, {name}! 🎉🥳 Hope you have an amazing day!"
)
CHANNEL_TEMPLATE = os.environ.get(
    "CHANNEL_TEMPLATE",
    "🎂 Happy Birthday {mentions}! 🎉"
)

client = WebClient(token=SLACK_TOKEN)


def call(fn, **kwargs):
    """Retry on Slack rate limits (HTTP 429)."""
    while True:
        try:
            return fn(**kwargs)
        except SlackApiError as e:
            if getattr(e.response, "status_code", None) == 429:
                time.sleep(int(e.response.headers.get("Retry-After", "1")))
                continue
            raise


def all_members(channel_id: str) -> list[str]:
    members, cursor = [], None
    while True:
        r = call(client.conversations_members, channel=channel_id, limit=200, cursor=cursor)
        members.extend(r.get("members", []))
        cursor = (r.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            return members


def month_day(raw: str):
    """Parse lots of common date formats; return (month, day) or None."""
    if not raw:
        return None
    s = raw.strip().split("T", 1)[0]  # allow ISO-ish timestamps
    for fmt in (
        "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
        "%m/%d", "%d/%m", "%m-%d", "%d-%m",
    ):
        try:
            d = datetime.strptime(s, fmt)
            return d.month, d.day
        except ValueError:
            pass
    return None


def dm_user(user_id: str, name: str):
    dm = call(client.conversations_open, users=user_id)["channel"]["id"]
    call(client.chat_postMessage, channel=dm, text=DM_TEMPLATE.format(name=name or "there"))


def announce(user_ids: list[str]):
    mentions = ", ".join(f"<@{u}>" for u in user_ids)
    call(client.chat_postMessage, channel=ANNOUNCE_CHANNEL_ID, text=CHANNEL_TEMPLATE.format(mentions=mentions))


def main():
    today = datetime.now(ZoneInfo(TZ)).date()
    today_md = (today.month, today.day)

    rows, birthdays = [], []

    for uid in all_members(SOURCE_CHANNEL_ID):
        try:
            prof = call(client.users_profile_get, user=uid)["profile"]
            name = prof.get("real_name") or prof.get("display_name") or ""
            fields = prof.get("fields") or {}
            braw = (fields.get(BIRTHDAY_FIELD_ID) or {}).get("value")
            is_today = (month_day(braw) == today_md)

            rows.append([name, uid, braw or "", "YES" if is_today else ""])
            if is_today:
                birthdays.append((uid, name))

            time.sleep(PROFILE_DELAY)
        except SlackApiError as e:
            print(f"Profile error for {uid}: {e.response['error']}")

    print(f"\nSlack Channel Members (Birthday Check) — {today.isoformat()} ({TZ})\n")
    print(tabulate(rows, headers=["Name", "Slack ID", "Birthday Value", "Birthday Today"], tablefmt="github"))
    print(f"\nTotal users processed: {len(rows)} | Birthdays today: {len(birthdays)}")

    if birthdays:
        for uid, name in birthdays:
            try:
                dm_user(uid, name)
            except SlackApiError as e:
                print(f"DM error for {uid}: {e.response['error']}")
        try:
            announce([uid for uid, _ in birthdays])
        except SlackApiError as e:
            print(f"Announce error: {e.response['error']}")


if __name__ == "__main__":
    main()
