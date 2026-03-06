import os
import time
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from tabulate import tabulate

SLACK_TOKEN = os.environ["SLACK_TOKEN"]
SOURCE_CHANNEL_ID = os.environ["SOURCE_CHANNEL_ID"]
ANNOUNCE_CHANNEL_ID = os.environ["ANNOUNCE_CHANNEL_ID"]
BIRTHDAY_FIELD_ID = os.environ.get("BIRTHDAY_FIELD_ID", "Xf05STPV0Z3R")
PROFILE_DELAY = float(os.environ.get("PROFILE_FETCH_DELAY_SECONDS", "0.2"))
TZ = os.environ.get("TZ_NAME", "Europe/Lisbon")

DM_TEMPLATES = [
    "Happy birthday, {name}! 🎉 Another year older and definitely another year wiser! We at START Lisbon are really grateful to have you as part of the community and hope your day is filled with great moments, good company, and maybe even some cake. Wishing you lots of success, happiness, and exciting opportunities in the year ahead! 💙",
    "Happy birthday, {name}! 🎂 One more year of experiences, stories, and achievements added to the journey! Everyone at START Lisbon is lucky to have you with us, and we hope today brings you plenty of smiles, celebrations, and a well-deserved moment to enjoy your special day. Cheers to an amazing year ahead! 💙",
    "Happy birthday, {name}! 🎈 Another trip around the sun and another milestone worth celebrating! We at START Lisbon are happy to have you as part of the team and wish you a day full of laughter, appreciation, and a bit of birthday magic. May the coming year bring you exciting ideas, new opportunities, and plenty of reasons to celebrate! 💙",
    "Happy birthday, {name}! 🥳 Time to celebrate another fantastic year of you! The START Lisbon community is grateful to have you around and hopes your birthday is filled with joy, good vibes, and maybe a surprise or two. Wishing you all the best today and a year ahead full of inspiration, growth, and memorable moments! 💙",
    "Happy birthday, {name}! 🎉 Today is the perfect excuse to celebrate you and everything you bring to START Lisbon. We’re really glad to have you as part of the community and hope your special day is packed with happiness, great conversations, and well-deserved celebrations. Here’s to a wonderful year ahead filled with success and great experiences! 💙",
]

CHANNEL_TEMPLATES = [
    "WOOOW! It’s {name}’s special day! 🎉 Make sure to congratulate them today, everyone. We at START Lisbon are really happy to have you with us and look forward to another great semester together! 💙",
    "Hold up — it’s {name}’s birthday today! 🎂 Don’t forget to send some birthday wishes their way. START Lisbon is lucky to have you, {name}, and we’re excited for another amazing semester together! 💙",
    "Attention everyone! 🥳 Today we celebrate {name}! Make sure to drop a birthday message and spread the birthday cheer. We at START Lisbon are super happy to have you in the community! 💙",
    "Big news today — it’s {name}’s birthday! 🎈 Let’s make sure they feel the love and send some congratulations. START Lisbon is glad to have you with us, and we’re excited for the times ahead! 💙",
    "Guess what? It’s {name}’s special day! 🎉 Be sure to wish them a happy birthday when you see them. The START Lisbon community is lucky to have you, {name}, and we’re looking forward to another great semester! 💙",
]

client = WebClient(token=SLACK_TOKEN)


def call(fn, **kwargs):
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
    if not raw:
        return None
    s = raw.strip().split("T", 1)[0]
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
    message = random.choice(DM_TEMPLATES).format(name=name or "there")
    call(client.chat_postMessage, channel=dm, text=message)


def announce(user_ids: list[str], names: list[str]):
    for uid, name in zip(user_ids, names):
        message = random.choice(CHANNEL_TEMPLATES).format(name=name)
        call(client.chat_postMessage, channel=ANNOUNCE_CHANNEL_ID, text=message)


def main():
    now = datetime.now(ZoneInfo(TZ))

    if now.hour != 9:
        print(f"Skipping run: local time is {now.strftime('%H:%M')} in {TZ}, not 09:00.")
        return

    today = now.date()
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
        user_ids = [uid for uid, _ in birthdays]
        names = [name for _, name in birthdays]

        for uid, name in birthdays:
            try:
                dm_user(uid, name)
            except SlackApiError as e:
                print(f"DM error for {uid}: {e.response['error']}")

        try:
            announce(user_ids, names)
        except SlackApiError as e:
            print(f"Announce error: {e.response['error']}")


if __name__ == "__main__":
    main()
