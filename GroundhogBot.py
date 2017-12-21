"""
    GroundhogBot is based on https://github.com/mattmakai/slack-starterbot
"""


import os
import time
import re
import sqlite3
import sys
from slackclient import SlackClient

# instantiate Slack client
slack_client = SlackClient(os.environ.get('SLACK_API_TOKEN'))
# bot's user ID in Slack: value is assigned after the bot starts up
starterbot_id = None

# constants
RTM_READ_DELAY = 1  # 1 second delay between reading from RTM
EXAMPLE_COMMAND = "do"
MENTION_REGEX = "^<@(|[WU].+)>(.*)"
REACTION = "exclamation"


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
        cur.execute('SELECT name FROM Members WHERE id = ?', (who,))
        who = cur.fetchall()[0][0]
        cur.execute('SELECT name FROM Channels WHERE id = ?', (where,))
        where = cur.fetchall()[0][0]
        minutes = str(int((float(ts) - float(when)) / 60))
        slack_client.api_call(
            "reactions.add",
            channel=chan,
            name=REACTION,
            timestamp=ts)
        slack_client.api_call(
            "chat.postMessage",
            channel=chan,
            username="GroundhogBot",
            text="Człowieniu, ogarnij się! Masz Ty Rozum i Godność Człowieka? Link {} był już zapodany przez juzera *{}* na kanale *#{}* raptem *{} min.* temu.".format(url, who, where, minutes))


def append_url(url, ts, user, chan):
    """
        Appends unique url to the database
    """
    conn = sqlite3.connect('groundhog.sqlite')
    cur = conn.cursor()
    cur.execute("INSERT INTO Urls (ts, user, channel, url) VALUES (?, ?, ?, ?)", (ts, user, chan, url))
    conn.commit()
    conn.close()


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

        if event["type"] == "message" and not "subtype" in event:
            user_id, message = parse_direct_mention(event["text"])
            if user_id == starterbot_id:
                handle_command(message, event["channel"])

        if event["type"] == "message" and "subtype" not in event and event["text"] == "Głupi bot":
            slack_client.api_call(
                "reactions.add",
                channel=event["channel"],
                name="rage",
                timestamp=event["ts"])
            slack_client.api_call(
                "chat.postMessage",
                channel=event["channel"],
                username="GroundhogBot",
                text="Sam jesteś głupi!")


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


if __name__ == "__main__":
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
