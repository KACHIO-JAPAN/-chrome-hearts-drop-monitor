#!/usr/bin/env python3
"""Conservative Chrome Hearts official category link change monitor (stdlib only)."""
import json, os, re, sys, urllib.request, urllib.parse
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://www.chromehearts.com"
CATEGORIES = ["/baccarat", "/scents", "/boxers-leggings", "/intimates", "/socks"]
EXCLUDED = {"baccarat", "scents", "boxers-leggings", "intimates", "socks", "underwear"}
# Previously observed category baseline is stored alongside products. A category is
# an event when newly visible or after it disappeared; old product history does not matter.
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


def category_candidates(html):
    """Find same-domain top-level category routes and routes of product links."""
    parser = Links()
    parser.feed(html)
    candidates = set()
    for href, _label in parser.items:
        url = urllib.parse.urljoin(BASE, href)
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc not in ("chromehearts.com", "www.chromehearts.com"):
            continue
        parts = [p.lower() for p in parsed.path.strip("/").split("/") if p]
        if not parts:
            continue
        key = parts[0]
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,70}", key) or key in EXCLUDED:
            continue
        # Single-segment links can be categories; product detail links reveal their category.
        # A candidate must still yield official product links when verified below.
        if len(parts) == 1 or (len(parts) >= 3 and parts[-1].endswith(".html")):
            candidates.add(key)
    return candidates

def category_name(path):
    return path.upper().replace("-", " ")

def alert(message):
    hook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not hook:
        print("DISCORD_WEBHOOK_URL not configured; no push notification. Detected:\n" + message)
        return
    if not hook.startswith("https://discord.com/api/webhooks/") and not hook.startswith("https://discordapp.com/api/webhooks/"):
        raise ValueError("Invalid Discord webhook domain")
    payload = json.dumps({"content":message[:1900]}).encode()
    req = urllib.request.Request(hook, data=payload, headers={"Content-Type":"application/json", "User-Agent":"ChromeHeartsMonitor/1.0 (+https://github.com/KACHIO-JAPAN/-chrome-hearts-drop-monitor)"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status not in (200, 204):
            raise ValueError(f"Discord returned {resp.status}")

def main():
    all_items = {}
    errors = []
    category_keys = set()
    # Scan the navigation and all previously known category pages; discover categories
    # from product links even when their navigation entries are not top-level.
    try:
        homepage = fetch(BASE + "/")
        category_keys.update(category_candidates(homepage))
    except Exception as exc:
        errors.append(f"/: {type(exc).__name__}: {exc}")
    pages_to_scan = set(p.strip("/") for p in CATEGORIES) | {"scarf", "slippers"}
    old = json.loads(STATE.read_text()) if STATE.exists() else None
    if old:
        pages_to_scan.update(old.get("categories", []))
    pages_to_scan.update(category_keys)
    verified_categories = set()
    for key in sorted(pages_to_scan):
        try:
            html = fetch(BASE + "/" + key)
            items = products_from(html)
            if not items:
                if key in (p.strip("/") for p in CATEGORIES):
                    raise ValueError("No product links; page parser requires review")
                continue
            all_items.update(items)
            verified_categories.add(key)
            category_keys.update(category_candidates(html))
            print(f"/{key}: {len(items)} product URLs")
        except Exception as exc:
            if key in (p.strip("/") for p in CATEGORIES) or (old and key in old.get("categories", [])):
                errors.append(f"/{key}: {type(exc).__name__}: {exc}")
            else:
                print(f"Unverified candidate /{key}: {type(exc).__name__}")
    # Scan freshly discovered routes from the verified category pages, too.
    for key in sorted(category_keys - verified_categories - pages_to_scan - EXCLUDED):
        try:
            items = products_from(fetch(BASE + "/" + key))
            if items:
                all_items.update(items)
                verified_categories.add(key)
        except Exception as exc:
            print(f"Unverified candidate /{key}: {type(exc).__name__}")
    if errors:
        print("SOURCE ERROR; state unchanged; no misleading notifications:\\n" + "\\n".join(errors), file=sys.stderr)
        return 2
    active_categories = sorted(verified_categories - EXCLUDED)
    old_categories = set(old.get("categories", [])) if old is not None else set()
    # Existing legacy state has no category baseline: send a one-time initial alert.
    new_categories = sorted(set(active_categories) - old_categories)
    new_products = sorted(set(all_items) - set(old.get("products", {}))) if old is not None else []
    if new_categories:
        for key in new_categories:
            examples = [(url, label) for url, label in all_items.items()
                        if urllib.parse.urlparse(url).path.startswith("/" + key + "/")]
            lines = [f"🔔 Chrome Hearts OFFICIAL CATEGORY detected: {category_name(key)}",
                     f"Official category: {BASE}/{key}",
                     f"Checked JST: {datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('Asia/Tokyo')).strftime('%Y-%m-%d %H:%M')}",
                     "Previously sold / known products are INCLUDED. Purchase and Japan delivery: UNKNOWN."]
            for url, label in examples[:3]:
                lines.append(f"{label}: {url}")
            alert("\\n".join(lines))
    if new_products:
        # Alert product links separately from the new-category event.
        for offset in range(0, min(len(new_products), 24), 6):
            group = new_products[offset:offset + 6]
            alert("Chrome Hearts NEW PRODUCT LINK (purchase/JP delivery UNKNOWN):\\n"
                  + "\\n".join(f"{all_items[u]}: {u}" for u in group))
    STATE.parent.mkdir(exist_ok=True, parents=True)
    STATE.write_text(json.dumps({
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "categories": active_categories,
        "products": all_items
    }, ensure_ascii=False, indent=2) + "\\n")
    print(f"Observed {len(all_items)} links; active monitored categories: {active_categories}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
