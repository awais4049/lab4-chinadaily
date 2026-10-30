"""Downloads Chrome and the matching ChromeDriver (same version) into /opt."""
import io
import json
import urllib.request
import zipfile

LIST_URL = (
    "https://googlechromelabs.github.io/chrome-for-testing/"
    "last-known-good-versions-with-downloads.json"
)

data = json.load(urllib.request.urlopen(LIST_URL, timeout=60))
downloads = data["channels"]["Stable"]["downloads"]
print("Chrome version:", data["channels"]["Stable"]["version"])

for name in ("chrome", "chromedriver"):
    url = next(d["url"] for d in downloads[name] if d["platform"] == "linux64")
    print("Downloading", url)
    blob = urllib.request.urlopen(url, timeout=300).read()
    zipfile.ZipFile(io.BytesIO(blob)).extractall("/opt")
