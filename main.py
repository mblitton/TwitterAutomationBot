import os
import datetime
from datetime import timezone
import time
import pytwitter
from pytwitter import Api
import tweepy
import random
import psycopg2
import logging
from random import randint

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Function to read the Like list accounts
def read_like_accounts(api):
    return get_like_accounts(api)

# Function to read the Embed list accounts
def read_embed_accounts(api):
    return get_embed_accounts(api)

# Function to read the RT list accounts
def read_rt_accounts(api):
    return get_rt_accounts(api)

# Set up a connection to the PostgreSQL database
DATABASE_URL = os.environ['DATABASE_URL']
conn = psycopg2.connect(DATABASE_URL, sslmode='require')

# Create a table to store tweeted URLs if it doesn't exist
with conn.cursor() as cur:
    cur.execute("CREATE TABLE IF NOT EXISTS tweeted_urls (url TEXT PRIMARY KEY)")
    conn.commit()

# Function to retry an operation with exponential backoff on failure
def retry_with_backoff(max_retries, func, *args, **kwargs):
    retries = 0
    while retries <= max_retries:
        try:
            return func(*args, **kwargs)
        except (tweepy.TweepError, pytwitter.PyTwitterError) as e:
            if retries < max_retries:
                sleep_time = 2 ** retries + randint(1, 5)  # Exponential backoff with jitter
                print(f"Error occurred: {e}. Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
                retries += 1
            else:
                print(f"Error occurred: {e}. Max retries reached. Skipping this operation.")
                break

# Function to get recent tweets from a user
def get_recent_tweets(api, username, count=15):
    response = api.get_timelines(user_id=username, max_results=count, expansions="attachments.media_keys", tweet_fields="created_at,text,attachments,referenced_tweets", media_fields="url")
    tweets = []
    for tweet in response.data:
        is_retweet = False
        if tweet.referenced_tweets:  # Check if the tweet has referenced tweets
            for ref_tweet in tweet.referenced_tweets:
                if ref_tweet.type == "retweeted":  # Check if the tweet is a retweet
                    is_retweet = True
                    break

        if not is_retweet:
            tweets.append({"id": tweet.id, "created_at": tweet.created_at, "text": tweet.text, "media_keys": tweet.attachments.media_keys if tweet.attachments else None})
    return tweets

# Function to get tweet URLs containing videos
def get_tweet_urls_with_videos(api, user_id, media_count):
    tweet_data = []
    for tweet in tweepy.Cursor(api.user_timeline, user_id=user_id, tweet_mode="extended").items(media_count):
        if not hasattr(tweet, 'retweeted_status'):  # Check if the tweet is not a retweet
            if "media" in tweet.entities:
                for media in tweet.extended_entities["media"]:
                    if media["type"] == "video":
                        tweet_url = f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id}"
                        tweet_data.append({"url": tweet_url, "username": tweet.user.screen_name})
                        break
    return tweet_data

# Function to tweet video links
def tweet_video_links(api, tweet_data):
    tweet_texts = ["Check out this video\n"]
    for data in tweet_data:
        video_url = f"{data['url']}/video/1"
        with conn.cursor() as cur:
            cur.execute("SELECT url FROM tweeted_urls WHERE url = %s", (video_url,))
            existing_url = cur.fetchone()

        if existing_url is None:
            #add more text options to `tweet_texts` to generate different tweets for each embed post
            text = random.choice(tweet_texts)
            #remove @{data['username'] if you don't want the username mentioned in the tweet
            tweet_status = f"{text} @{data['username']}\n.\n.\n.\nF{video_url}"
            api.update_status(status=tweet_status)
            #add video url to table to avoid tweeting twice
            with conn.cursor() as cur:
                cur.execute("INSERT INTO tweeted_urls (url) VALUES (%s)", (video_url,))
                conn.commit()
        else:
            print(f"Skipping duplicate URL: {video_url}")

# Function to get accounts in the Embed list
def get_embed_accounts(api):
    """
    Retrieve a list of Twitter accounts from the "Embed" list.
    Args:
        api (tweepy.API): The authenticated Tweepy API object.
    Returns:
        list: A list of tweepy.models.User objects representing the VIP accounts.
    """
    vip_accounts = []
    lists = api.get_lists()
    vip_list = None
    for lst in lists:
        if lst.name == "Embed":
            vip_list = lst
            break

    if vip_list is not None:
        members = api.get_list_members(list_id=vip_list.id)
        for member in members:
            vip_accounts.append(member.screen_name)
    else:
        print("No 'Embed' list found.")

    return vip_accounts

# Function to get accounts in the Like list
def get_like_accounts(api):
    """
    Retrieve a list of Twitter accounts from the "Like" list.
    Args:
        api (tweepy.API): The authenticated Tweepy API object.
    Returns:
        list: A list of tweepy.models.User objects representing the VIP accounts.
    """
    like_accounts = []
    lists = api.get_lists()
    like_list = None
    for lst in lists:
        if lst.name == "Like":
            like_list = lst
            break
    if like_list is not None:
        members = api.get_list_members(list_id=like_list.id)
        for member in members:
            like_accounts.append(member.screen_name)
    else:
        print("No 'Like' list found.")
    return like_accounts

# Function to get accounts in the RT list
def get_rt_accounts(api):
    """
    Retrieve a list of Twitter accounts from the "RT" list.
    Args:
        api (tweepy.API): The authenticated Tweepy API object.
    Returns:
        list: A list of tweepy.models.User objects representing the VIP accounts.
    """
    rt_accounts = []
    lists = api.get_lists()
    rt_list = None
    for lst in lists:
        if lst.name == "RT":
            rt_list = lst
            break
    if rt_list is not None:
        members = api.get_list_members(list_id=rt_list.id)
        for member in members:
            rt_accounts.append(member.screen_name)
    else:
        print("No 'RT' list found.")
    return rt_accounts

# Main function to run the script
def main():
    # Load API keys and access tokens from environment variables
    consumer_key = os.environ['API_KEY']
    consumer_secret = os.environ['API_KEY_SECRET']
    access_token = os.environ['ACCESS_TOKEN']
    access_token_secret = os.environ['ACCESS_TOKEN_SECRET']
    check_interval = int(os.environ['CHECK_INTERVAL'])

    # Initialize PyTwitter API
    api = Api(consumer_key=consumer_key, consumer_secret=consumer_secret, access_token=access_token, access_secret=access_token_secret)

    # Initialize Tweepy API for embed_accounts
    tweepy_auth = tweepy.OAuth1UserHandler(consumer_key, consumer_secret, access_token, access_token_secret)
    tweepy_api = tweepy.API(tweepy_auth)
 
    # Set last_checked to 2 hours ago
    last_checked = datetime.datetime.now(timezone.utc) - datetime.timedelta(hours=2)

    # Main loop
    while True:
        # Read account lists
        embed_accounts = read_embed_accounts(tweepy_api)
        like_accounts = read_like_accounts(tweepy_api)
        rt_accounts = read_rt_accounts(tweepy_api)

        # Process like_accounts
        for account in like_accounts:
            try:
                user = api.get_user(username=account)
                recent_tweets = get_recent_tweets(api, user.data.id)

                for tweet in recent_tweets:
                    tweet_created_at = datetime.datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00"))

                    if tweet_created_at > last_checked:
                        tweet_id = tweet["id"]
                        retry_with_backoff(3, api.like_tweet, user_id=api.auth_user_id, tweet_id=tweet_id)
                        time.sleep(1)
            except Exception as e:
                logger.error(f"Error with account {account}: {e}")

        # Process embed_accounts
        for embed_account in embed_accounts:
            try:
                vip_user = retry_with_backoff(3, tweepy_api.get_user, screen_name=embed_account)
                user_id = vip_user.id_str
                media_count = 2
                tweet_urls = get_tweet_urls_with_videos(tweepy_api, user_id, media_count)
                retry_with_backoff(3, tweet_video_links, tweepy_api, tweet_urls)
            except Exception as e:
                logger.error(f"Error with account {account}: {e}")
            time.sleep(3)

        # Process rt_accounts
        for account in rt_accounts:
            try:
                user = api.get_user(username=account)
                recent_tweets = get_recent_tweets(api, user.data.id)

                for tweet in recent_tweets:
                    tweet_created_at = datetime.datetime.fromisoformat(tweet["created_at"].replace("Z", "+00:00"))

                    if tweet_created_at > last_checked:
                        tweet_id = tweet["id"]
                        if tweet["media_keys"]:
                            retry_with_backoff(3, api.retweet_tweet, user_id=api.auth_user_id, tweet_id=tweet_id)
                        time.sleep(2)
            except Exception as e:
                logger.error(f"Error with account {account}: {e}")

        # Update last_checked timestamp
        last_checked = datetime.datetime.now(timezone.utc)
        time.sleep(check_interval)

# Run the script
if __name__ == "__main__":
    main()

