import time
import random
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import threading

SUBREDDITS = [
    "AskReddit", "funny", "gaming", "pics", "aww", "todayilearned",
    "worldnews", "science", "movies", "technology", "news", "interestingasfuck",
    "nottheonion", "dataisbeautiful", "askscience", "explainlikeimfive"
]

CHECK_INTERVAL = 1  # seconds between new-post checks
DELETION_CHECK_INTERVAL = 60  # check for deletions every 1 minute
tracked_posts = {}
tracked_posts_lock = threading.Lock()

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0 Safari/537.36"),
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_new_posts(subreddit):
    url = f"https://old.reddit.com/r/{subreddit}/new/"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        posts = soup.find_all("div", class_="thing")
        new_posts = []

        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=2)

        for post in posts:
            if "promoted" in post.get("class", []):
                continue

            post_id = post.get("data-fullname")
            if not post_id or post_id in tracked_posts:
                continue

            time_tag = post.find("time")
            if time_tag and time_tag.has_attr("datetime"):
                post_time = datetime.strptime(time_tag["datetime"], "%Y-%m-%dT%H:%M:%S+00:00")
                if post_time < cutoff:
                    continue

            title_tag = post.find("a", class_="title")
            if not title_tag:
                continue

            title = title_tag.text.strip()
            link = "https://reddit.com" + post.get("data-permalink")

            # ✅ Fetch full post body from permalink page
            try:
                post_resp = requests.get(link, headers=HEADERS, timeout=10)
                post_soup = BeautifulSoup(post_resp.text, "html.parser")
                full_body = post_soup.find("div", class_="usertext-body")
                content = full_body.get_text(strip=True) if full_body else ""
            except:
                content = ""

            post_data = {
                "post_id": post_id,
                "subreddit": subreddit,
                "title": title,
                "link": link,
                "content": content,
                "scraped_at": datetime.utcnow().isoformat()
            }
            new_posts.append(post_data)

        return new_posts

    except Exception as e:
        print(f"[ERROR] r/{subreddit}: {e}")
        return []


def new_posts_loop():
    while True:
        for sub in SUBREDDITS:
            posts = fetch_new_posts(sub)
            if posts:
                with tracked_posts_lock:
                    for post in posts:
                        tracked_posts[post["post_id"]] = post
        time.sleep(CHECK_INTERVAL + random.uniform(0, 0.5))


def is_post_deleted(post):
    try:
        r = requests.get(post["link"], headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return True

        soup = BeautifulSoup(r.text, "html.parser")

        # Check title
        title_tag = soup.find("a", class_="title")
        if not title_tag or title_tag.text.strip().lower() in ["[deleted]", "[removed]"]:
            return True

        # Check post body
        body = soup.find("div", class_="usertext-body")
        if body:
            text = body.get_text(strip=True).lower()
            if text in ["[deleted]", "[removed]", ""]:
                return True

        return False
    except Exception as e:
        print(f"[ERROR] Checking {post['post_id']}: {e}")
        return False


def check_deleted_posts_loop():
    while True:
        time.sleep(DELETION_CHECK_INTERVAL)
        with tracked_posts_lock:
            for post_id in list(tracked_posts.keys()):
                post = tracked_posts[post_id]
                if is_post_deleted(post):
                    with open("deleted_log.txt", "a", encoding="utf-8") as f:
                        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - r/{post['subreddit']} - {post['title']}\n")
                        f.write(f"Link: {post['link']}\n")
                        f.write(f"Content: {post['content']}\n\n")
                    print(f"[DELETED] r/{post['subreddit']} - {post['title']}")
                    del tracked_posts[post_id]


def main():
    new_thread = threading.Thread(target=new_posts_loop, daemon=True)
    check_thread = threading.Thread(target=check_deleted_posts_loop, daemon=True)
    new_thread.start()
    check_thread.start()
    new_thread.join()
    check_thread.join()


if __name__ == "__main__":
    main()
