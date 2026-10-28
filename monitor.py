#!/usr/bin/env python3
"""Conservative Chrome Hearts official category link change monitor (stdlib only)."""
import json, os, re, sys, urllib.request, urllib.parse
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://www.chromehearts.com"
CATEGORIES = ["/baccarat", "/scents", "/boxers-leggings", "/intimates", "/socks"]
STATE = Path("state/products.json")
class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.items = []
        self.buf = []
    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.buf = []
    def handle_data(self, data):
        if self.href is not None:
            self.buf.append(data.strip())
    def handle_endtag(self, tag):
        if tag == "a" and self.href:
            self.items.append((self.href, " ".join(x for x in self.buf if x)))
            self.href = None
            self.buf = []

def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (compatible; CH-drop-observer/0.1; public-change-monitor)", "Accept":"text/html"})
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
        data = response.read(2_000_000)
        if len(data) < 2000:
            raise ValueError("Suspiciously short response")
        return data.decode("utf-8", errors="replace")

def products_from(html):
    parser = Links()
    parser.feed(html)
    found = {}
    for href, label in parser.items:
        url = urllib.parse.urljoin(BASE, href).split("?", 1)[0].split("#", 1)[0]
        parsed = urllib.parse.urlparse(url)
        # Only direct official product detail .html links, never third-party sites or generic pages.
        if parsed.netloc not in ("chromehearts.com", "www.chromehearts.com"):
            continue
        if not re.search(r"/[^/]+/[^/]+/[^/]+\.html$", parsed.path):
            continue
        if len(parsed.path) > 300:
            continue
        found[url] = label[:120] or parsed.path.rsplit("/",1)[-1]
    return found

def alert(message):
    hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not hook:
        print("DISCORD_WEBHOOK_URL not configured; no push notification. Detected:\n" + message)
        return
    if not hook.startswith("https://discord.com/api/webhooks/") and not hook.startswith("https://discordapp.com/api/webhooks/"):
        raise ValueError("Invalid Discord webhook domain")
    payload = json.dumps({"content":message[:1900]}).encode()
    req = urllib.request.Request(hook, data=payload, headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status not in (200, 204):
            raise ValueError(f"Discord returned {resp.status}")

def main():
    all_items = {}
    errors = []
    for path in CATEGORIES:
        try:
            items = products_from(fetch(BASE + path))
            if not items:
                raise ValueError("No product links; page parser requires review")
            all_items.update(items)
            print(f"{path}: {len(items)} product URLs")
        except Exception as exc:
            errors.append(f"{path}: {type(exc).__name__}: {exc}")
    if errors:
        print("SOURCE ERROR; state unchanged; no misleading product notifications:\n" + "\n".join(errors), file=sys.stderr)
        return 2
    old = json.loads(STATE.read_text()) if STATE.exists() else None
    if old is not None:
        new = sorted(set(all_items) - set(old.get("products", {})))
        if new:
            message = "Chrome Hearts official NEW PRODUCT LINK detected (purchase/JP delivery NOT verified):\n" + "\n".join(f"{all_items[u]}: {u}" for u in new[:8])
            alert(message)
    else:
        print("First successful scan: baseline only, no notifications.")
    STATE.parent.mkdir(exist_ok=True, parents=True)
    STATE.write_text(json.dumps({"checked_at_utc":datetime.now(timezone.utc).isoformat(), "products":all_items}, ensure_ascii=False, indent=2) + "\n")
    print(f"Observed {len(all_items)} total links; baseline safely updated.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
