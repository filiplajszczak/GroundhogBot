"""
    GroundhogBot is based on https://github.com/mattmakai/slack-starterbot
"""


import os
import time
import re
import sqlite3
import sys
import argparse
import gettext
import json
from slackclient import SlackClient

# instantiate Slack client
slack_client = SlackClient(os.environ.get('SLACK_API_TOKEN'))
# bot's user ID in Slack: value is assigned after the bot starts up
starterbot_id = None

# constants
RTM_READ_DELAY = 1  # 1 second delay between reading from RTM
EXAMPLE_COMMAND = "do"
MENTION_REGEX = "^<@(|[WU].+)>(.*)"


def database_setup():
    """
        Checks if database is already created. If not creates and populates it with members anc channels data.
    """

    conn = sqlite3.connect('groundhog.sqlite')
    cur = conn.cursor()
    cur.execute('CREATE TABLE IF NOT EXISTS Urls (ts TEXT, user TEXT, channel TEXT, url TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS Members (id TEXT, name TEXT)')
    cur.execute('CREATE TABLE IF NOT EXISTS Channels (id TEXT, name TEXT)')
    cur.execute('SELECT * FROM Members')
    if cur.fetchall() == []:
        members = slack_client.api_call("users.list")["members"]
        for member in members:
            cur.execute('INSERT INTO Members (id, name) VALUES (?, ?)', (member['id'], member['profile']['display_name']))
        channnels = slack_client.api_call("channels.list")["channels"]
        for chan in channnels:
            cur.execute('INSERT INTO Channels (id, name) VALUES (?, ?)', (chan['id'], chan['name']))
        conn.commit()
    conn.close()


def check_url(url, ts, user, chan):
    """
        Checks url for duplicates in database of previously posted urls.
    """
    conn = sqlite3.connect('groundhog.sqlite')
    cur = conn.cursor()
    cur.execute('SELECT ts, user, channel FROM Urls WHERE url = ?', (url,))
    query = cur.fetchall()
    if query == []:
        append_url(url, ts, user, chan)
    else:
        cur.execute('SELECT ts, user, channel FROM Urls WHERE url = ?', (url,))
        first = cur.fetchall()
        (when, who, where) = first[0]
        who = find_user(who)
        where = find_channel(where)
        bad_user = find_user(user)
        minutes = str(int((float(ts) - float(when)) / 60))
        slack_client.api_call(
            "reactions.add",
            channel=chan,
            name=duplicate_url_reaction,
            timestamp=ts)
        slack_client.api_call(
            "chat.postMessage",
            channel=chan,
            username="GroundhogBot",
            text=_("*{user_who_posted_duplicate}*, look! Are you paying attention? "
                 "{duplicate_url} was already posted by *{user_who_posted_first}* "
                 "on channel *#{channel_name}* just *{number_of_minutes} min.* ago.")
                 .format(user_who_posted_duplicate=bad_user, duplicate_url=url, user_who_posted_first=who,
                         channel_name=where, number_of_minutes=minutes))
    conn.close()

def append_url(url, ts, user, chan):
    """
        Appends unique url to the database
    """
    conn2 = sqlite3.connect('groundhog.sqlite')
    cur2 = conn2.cursor()
    cur2.execute("INSERT INTO Urls (ts, user, channel, url) VALUES (?, ?, ?, ?)", (ts, user, chan, url))
    conn2.commit()
    conn2.close()


def parse_events(slack_events):
    """
        Parses a list of events coming from the Slack RTM API
    """
    for event in slack_events:
        print(event)
        if event["type"] == "message" and "subtype" not in event:
            try:
                url = (re.search("(?P<url>https?://[^>]+)", event["text"]).group("url"))
                check_url(url, event["ts"], event["user"], event["channel"])
            except:
                e = sys.exc_info()[0]
                print(e)

        if event["type"] == "message" and "subtype" not in event:
            user_id, message = parse_direct_mention(event["text"])
            if user_id == starterbot_id:
                handle_command(message, event["channel"])

        check_rules(event)


def parse_direct_mention(message_text):
    """
        Finds a direct mention (a mention that is at the beginning) in message text
        and returns the user ID which was mentioned. If there is no direct mention, returns None
    """
    matches = re.search(MENTION_REGEX, message_text)
    # the first group contains the username, the second group contains the remaining message
    return (matches.group(1), matches.group(2).strip()) if matches else (None, None)


def handle_command(command, channel):
    """
        Executes bot command if the command is known
    """
    # Default response is help text for the user
    default_response = "Not sure what you mean. Try *{}*.".format(EXAMPLE_COMMAND)

    # Finds and executes the given command, filling in response
    response = None
    # This is where you start to implement more commands!
    if command.startswith(EXAMPLE_COMMAND):
        response = "Sure...write some more code then I can do that!"

    # Sends the response back to the channel
    slack_client.api_call(
        "chat.postMessage",
        channel=channel,
        text=response or default_response)

def check_rules(event):
    for rule in rules:
        print(rule)
        if (event["type"] == "message"
                and "subtype" not in event
                and rule["text_trigger"] in event["text"].lower()
                and (rule["user_trigger"] == []
                     or find_user(event["user"]) in rule["user_trigger"])):
            reaction_add(event["channel"], rule["emoji_reaction"], event["ts"])
            message_post(event["channel"], rule["text_reaction"])


def find_user(who):
    conn2 = sqlite3.connect('groundhog.sqlite')
    cur2 = conn2.cursor()
    cur2.execute('SELECT name FROM Members WHERE id = ?', (who,))
    who = cur2.fetchall()[0][0]
    conn2.close()
    return who


def find_channel(where):
    conn2 = sqlite3.connect('groundhog.sqlite')
    cur2 = conn2.cursor()
    cur2.execute('SELECT name FROM Channels WHERE id = ?', (where,))
    where = cur2.fetchall()[0][0]
    conn2.close()
    return where


def reaction_add(where, what, target):
    slack_client.api_call(
        "reactions.add",
        channel=where,
        name=what,
        timestamp=target)


def message_post(where, what):
    slack_client.api_call(
        "chat.postMessage",
        channel=where,
        username="GroundhogBot",
        text=what)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--reaction', type=str, default="exclamation",
                        help='Optional groundhog reaction emoji name')
    parser.add_argument('--language', type=str, default="en_US",
                        help='Set other language. (default: en_US, available: pl_PL)')
    parser.add_argument('--rules', type=str, default="default.json",
                        help='Point json file establishing custom set of bot reaction rules (default: default.json)')
    args = parser.parse_args()
    duplicate_url_reaction = args.reaction
    rules = json.load(open(args.rules, encoding='utf8'))["reactions"]
    if args.language == "pl_PL":
        pl_PL = gettext.translation('GroundhogBot', localedir='locale', languages=['pl_PL'])
        pl_PL.install()
    else:
        _ = lambda s: s
    if slack_client.rtm_connect(with_team_state=False):
        print("Starter Bot connected and running!")
        # Read bot's user ID by calling Web API method `auth.test`
        starterbot_id = slack_client.api_call("auth.test")["user_id"]
        database_setup()
        while True:
            parse_events(slack_client.rtm_read())
            time.sleep(RTM_READ_DELAY)
    else:
        print("Connection failed. Exception traceback printed above.")
