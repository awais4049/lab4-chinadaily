import os
import re
import threading
import time
from collections import Counter
from urllib.parse import quote_plus

from flask import Flask, jsonify, request
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# ---------------------------------------------------------------- settings
REGISTRATION = "FA23-BDS-053"
NEWS_SOURCE = "China Daily"          # 053 -> 53 % 20 + 1 = 14
SEARCH_URL = "https://newssearch.chinadaily.com.cn/en/search"

CHROME_BIN = os.environ.get("CHROME_BIN", "/opt/chrome-linux64/chrome")
CHROMEDRIVER = os.environ.get("CHROMEDRIVER", "/opt/chromedriver-linux64/chromedriver")

# real article links look like: chinadaily.com.cn/a/202610/28/WS64f....html
ARTICLE_RE = re.compile(r"chinadaily\.com\.cn/a/\d{6}/\d{2}/WS[0-9a-zA-Z]+\.html")
GENERIC_RE = re.compile(r"chinadaily\.com\.cn/.+\.html")

BODY_SELECTORS = ["#Content p", "article p", "p"]

app = Flask(__name__)
app.json.sort_keys = False
BROWSER_SLOTS = threading.Semaphore(2)   # max 2 Chrome windows at once (saves memory)


# ----------------------------------------------------------------- browser
def make_driver():
    opts = Options()
    opts.binary_location = CHROME_BIN
    for arg in (
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1400,1000",
        "--lang=en-US",
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    ):
        opts.add_argument(arg)
    driver = webdriver.Chrome(service=Service(executable_path=CHROMEDRIVER), options=opts)
    driver.set_page_load_timeout(40)
    return driver


def safe_get(driver, url):
    """Open a page; if it loads too slowly, stop loading and carry on."""
    try:
        driver.get(url)
    except TimeoutException:
        driver.execute_script("window.stop();")


def find_article_link(driver):
    hrefs = driver.execute_script(
        "return Array.from(document.querySelectorAll('a')).map(a => a.href);"
    )
    for pattern in (ARTICLE_RE,):
        for h in hrefs:
            if not h or "newssearch" in h or "index" in h or h.endswith("/"):
                continue
            if pattern.search(h):
                return h
    return None


def wait_for_link(driver, seconds=20):
    for _ in range(seconds):
        link = find_article_link(driver)
        if link:
            return link
        time.sleep(1)
    return None


def search_first_article(driver, keyword):
    # Try 1: put the keyword straight into the search URL
    safe_get(driver, SEARCH_URL + "?query=" + quote_plus(keyword))
    link = wait_for_link(driver)
    if link:
        return link

    # Try 2: type the keyword into the search box like a person would
    safe_get(driver, SEARCH_URL)
    time.sleep(2)
    for box in driver.find_elements(
        By.CSS_SELECTOR, "input[type='text'], input[type='search'], input:not([type])"
    ):
        if box.is_displayed():
            box.clear()
            box.send_keys(keyword)
            box.send_keys(Keys.ENTER)
            break
    return wait_for_link(driver)


def read_article(driver, url):
    safe_get(driver, url)
    time.sleep(2)
    for sel in BODY_SELECTORS:
        parts = []
        for p in driver.find_elements(By.CSS_SELECTOR, sel):
            text = (p.get_attribute("textContent") or "").strip()
            if len(text) >= 40:
                parts.append(text)
        body = "\n".join(parts)
        if len(body) > 200:
            return body
    return ""


# -------------------------------------------------------------- summarizer
STOP = set(
    """a an the and or but if of to in on at by for with from as is are was were be been being
    it its this that these those he she they we you i his her their our your not no so than then
    there here which who whom what when where why how about into over after before also will would
    can could should may might has have had do does did said says say more most such other""".split()
)


def summarize(text, n_sentences=4):
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.replace("\n", " "))]
    sentences = [s for s in sentences if len(s.split()) >= 6]
    if len(sentences) <= n_sentences:
        return " ".join(sentences)

    freq = Counter(
        w for w in re.findall(r"[a-z']+", text.lower()) if w not in STOP and len(w) > 2
    )
    scored = []
    for i, s in enumerate(sentences):
        words = [w for w in re.findall(r"[a-z']+", s.lower()) if w not in STOP]
        if not words:
            continue
        score = sum(freq[w] for w in words) / (len(words) ** 0.7)
        if i < 3:
            score *= 1.2          # opening sentences matter more in news
        scored.append((score, i))

    best = sorted(sorted(scored, reverse=True)[:n_sentences], key=lambda x: x[1])
    return " ".join(sentences[i] for _, i in best)


# ------------------------------------------------------------------ routes
@app.route("/")
def home():
    return f"""<!doctype html>
<html><head><title>{NEWS_SOURCE} Summarizer</title></head>
<body style="font-family:Arial;max-width:640px;margin:40px auto">
<h1>Registration Number: {REGISTRATION}</h1>
<p>News source: <b>{NEWS_SOURCE}</b></p>
<p>API is running. Try: <code>/get?keyword=climate</code></p>
</body></html>"""


@app.route("/get")
def get_summary():
    keyword = (request.args.get("keyword") or "").strip()
    result = {
        "registration": REGISTRATION,
        "newssource": NEWS_SOURCE,
        "keyword": keyword,
        "url": "",
        "summary": "",
    }
    if not keyword:
        result["error"] = "keyword query parameter is required"
        return jsonify(result), 400

    try:
        with BROWSER_SLOTS:
            driver = make_driver()
            try:
                url = search_first_article(driver, keyword)
                if not url:
                    result["error"] = "no search result found"
                    return jsonify(result), 404
                body = read_article(driver, url)
            finally:
                driver.quit()

        result["url"] = url
        result["summary"] = summarize(body) if body else "Could not read the article text."
        return jsonify(result)
    except Exception as e:  # keep the API alive whatever happens
        result["error"] = f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"[:300]
        return jsonify(result), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=7000, threaded=True)
