"""
This file is responsible for collecting the tweets from twitter for a certain hashtag
"""
import csv
import re
import time
import json
import argparse

import logger
from store_db import *
import create_db
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from tweet import Tweet
import os
from api import get_user_info, connect_to_api
from selenium.webdriver.firefox.options import Options
from pyvirtualdisplay import Display


def get_tweets(log, user_browser, query: str, user: str = None, password: str = None, idle: int = 5, scrolls: int = 5):
    """
    This function extract tweets from the given url and return the html content as text
    :param log: log object
    :param user_browser: user browser type
    :param query: string to search hash tags on twitter
    :param user: user name for log in
    :param password: password for log in
    :param idle: idle time for requests
    :param scrolls: number of scrolls we wish to simulate
    :return: tweets
    """
    log.info(f"Collecting tweets for query: {query}, with user: {user}")

    if user_browser == 'firefox':
       
        # opts.headless = True
        profile = webdriver.FirefoxProfile()
        profile.set_preference("general.useragent.override",
                               "Mozilla/5.0 (X11; Linux x86_64; rv:38.0) Gecko/20100101 Firefox/38.0")
        profile.set_preference("javascript.enabled", True)
        options = Options()
        options.headless = True
        browser = webdriver.Firefox(firefox_profile=profile,options=options)
        
    #elif user_browser == 'chrome':
     #   chrome_options = webdriver.ChromeOptions()
      #  chrome_options.add_argument("--no-sandbox")
       # chrome_options.add_argument("--disable-dev-shm-usage")
        #chrome_options.add_argument("--headless")
        #browser = webdriver.Chrome(chrome_options=chrome_options)
    else:
        log.warning(f"Selected browser {user_browser} is not valid")

    try:
        with open('config.json', 'r') as file:
            config = json.load(file)
    except FileNotFoundError as e:
        log.exception(f"configuration config_file is missing, error: {e}")

    if user != 'anonymous' and password != 'anonymous':
        browser.implicitly_wait(idle)
        browser.get(config['MAIN_URL'])
        time.sleep(1)
        browser.find_element_by_name("session[username_or_email]").send_keys(user)
        browser.implicitly_wait(1)
        browser.find_element_by_name("session[password]").send_keys(password)
        browser.implicitly_wait(1)
    browser.get(config['QUERY_URL'] + query)

    browser.implicitly_wait(idle)
    body = browser.find_element_by_tag_name('body')
    log.info(f"body: {body.text}")
    for _ in range(scrolls):
        body.send_keys(Keys.PAGE_DOWN)
        time.sleep(0.2)

    time.sleep(2)
    soup = BeautifulSoup(browser.page_source, 'lxml')
    log.info(f"Soup: {soup.text}")
    tweets = soup.find_all("div", attrs={"data-testid": "tweet"})
    log.info(f"tweets: {tweets}")

    return tweets


def create_tweets_obj(tweets, log):
    """
    This function creates tweets dictionary out of tweets
    :param tweets: soup object of tweets
    :param log log object
    :return: tweets dictionary
    """
    tweets_dict = {}
    replies_regex = re.compile('([0-9]+) [(replies)(reply)]')
    retweets_regex = re.compile('.* ([0-9]+) [(Retweets)(Retweet)]')
    likes_regex = re.compile('.* ([0-9]+) [(likes)(like)]')
    hashtag_regex = re.compile('/hashtag/([^\s]+)\?src=hashtag_click')
    username_regex = re.compile("/([^\s/]+)/?")
    print("Found {} tweets".format(len(tweets)))
    log.info("Found {} tweets".format(len(tweets)))
    for idx, tweet in enumerate(tweets):
        labels = [item for item in tweet.find_all("div", {"role": "group"}) if "aria-label" in item.attrs]
        replies = 0
        retweets = 0
        likes = 0
        if len(labels) == 1:
            label = labels[0]["aria-label"]
            if replies_regex.match(label):
                replies = int(replies_regex.match(label).group(1))

            if retweets_regex.match(label):
                retweets = int(retweets_regex.match(label).group(1))

            if likes_regex.match(label):
                likes = int(likes_regex.match(label).group(1))

        hashtags = [hashtag_regex.match(item["href"]).group(1)
                    for item in tweet.find_all("a") if "href" in item.attrs and hashtag_regex.match(item["href"])]
        tweet_user = [item['href']
                      for item in tweet.find_all("a", {"aria-haspopup": 'false', "role": "link"})
                      if "href" in item.attrs][0]
        tweet_user = username_regex.match(tweet_user).group(1)

        user_id = [item.span.text for item in tweet.find_all("div", {"dir": "auto"}) if item.find('span')][0]
        tweet_text = tweet.findAll("div", {"lang": "en", "dir": "auto"})[0].text

        api = connect_to_api()
        user_info = get_user_info(tweet_user, api=api)
        tweet_obj = Tweet(user=tweet_user, replies=replies, retweets=retweets, hashtags=hashtags, likes=likes,
                          text=tweet_text, statuses=user_info['statuses'], followers=user_info['followers'],
                          location=user_info['location'], user_id=user_id)
        tweets_dict[tweet_user] = tweet_obj

    return tweets_dict


def save_to_csv(file_path, tweets_dict):
    """
    This function saves the tweets dict to csv file
    :param file_path: csv file path
    :param tweets_dict: tweets dictionary
    """
    try:
        with open(file_path, 'w', newline='') as myfile:
            wr = csv.writer(myfile, quoting=csv.QUOTE_ALL)
            header = ['User', 'Replies', 'Retweets', 'Hashtags', 'text' '\n']
            wr.writerow(header)
            for key in tweets_dict:
                wr.writerow(
                    [tweets_dict[key].user, tweets_dict[key].replies, tweets_dict[key].retweets,
                     tweets_dict[key].hashtags, tweets_dict[key].text, '\n'])
    except FileExistsError:
        print('File Already exists')
        exit(1)


def get_args():
    """
    This function extracts the user input from cli
    :return: query, sql_password, user, password
    """
    parser = argparse.ArgumentParser(description='Query MySql_password User(optional) Password(optional)')
    parser.add_argument('query', type=str, help='Search query on tweeter')
    parser.add_argument('sql_password', type=str, help='MySql Server password')
    parser.add_argument('-u', '--username', default='anonymous', help='Tweeter Username')
    parser.add_argument('-p', '--password', default='anonymous', help='Tweeter Password')
    parser.add_argument('-b', '--browser', default='firefox', help='Browser: firefox or chrome')

    args = parser.parse_args()

    return args.query, args.sql_password, args.username, args.password, args.browser


def main():

    query, sql_password, user, password, selected_browser = get_args()
    os.environ['sql_password'] = sql_password
    # drop_database()

    log = logger.create_log()
    log.info('Starting to collect data')
    print('Starting to collect data')

    create_db.main()
    soup_tweets = get_tweets(log=log, query=query, user=user, password=password, user_browser=selected_browser)
    tweets_dict = create_tweets_obj(tweets=soup_tweets, log=log)
    store_tweets_dict(tweets_dict, query, user, log)

    log.info('Finished running')
    print('Finished running')


if __name__ == "__main__":
    main()
