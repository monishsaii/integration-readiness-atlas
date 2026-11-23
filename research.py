"""Fetch vendor evidence, extract research candidates, and compile the case study."""
import argparse
import concurrent.futures
import csv
import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import random
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
CATEGORIES = ["CRM & Sales", "Support", "Communications", "Marketing", "Ecommerce",
              "Data & SEO", "Developer & Infra", "Productivity", "Finance", "AI & Media"]
AUTH = {"o": "OAuth 2.0", "k": "API key / token", "b": "HTTP Basic", "j": "Signing / JWT",
        "n": "Local, no API auth", "?": "Unconfirmed"}
ACCESS = {"f": "Free / self-hosted", "t": "Trial / developer tenant", "m": "Test path; production gate",
          "r": "Approval required", "p": "Paid / provisioned", "u": "Unconfirmed"}
VERDICT = {"f": "Prototype", "t": "Prototype", "m": "Sandbox first", "p": "Needs customer access",
           "r": "Needs approval", "u": "Investigate"}


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script", "noscript", "svg"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if self.hidden and tag in {"style", "script", "noscript", "svg"}:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(" ".join(data.split()))


PATTERNS = {
    "oauth": r"oauth\s*2(?:\.0)?|oauth2|login with amazon",
    "key_or_token": r"\b(?:api key|personal access token|API token|bot token)\b",
    "basic": r"\b(?:http basic|basic auth(?:entication)?)\b",
    "test": r"\b(?:sandbox|test mode|test account|development store|free trial)\b",
    "gate": r"\b(?:enterprise plan|paid plan|production access|app review|contact sales|admin permissions)\b",
    "mcp": r"\b(?:MCP server|model context protocol)\b",
    "surface": r"\b(?:REST API|GraphQL|webhooks|CLI)\b",
}


def load_apps():
    apps = []
    for number, line in enumerate((ROOT / "apps.psv").read_text().splitlines(), 1):
        name, description, auth, access, surface, host_path, *notes = line.split("|")
        apps.append(dict(id=number, name=name, description=description,
                         category=CATEGORIES[(number-1)//10], auth=auth, access=access,
                         surface=surface, url="https://" + host_path,
                         note=notes[0] if notes else "", mcp="Unconfirmed"))
    if len(apps) != 100 or len({app["name"] for app in apps}) != 100:
        raise ValueError("Expected 100 unique app records in assignment order")
    return apps


def fetch(url):
    result = {"url": url, "status": None, "resolved_url": None, "characters": 0, "signals": {}}
    try:
        request = Request(url, headers={"User-Agent": "IntegrationReadinessResearch/1.0"})
        with urlopen(request, timeout=9) as response:
            result.update(status=response.status, resolved_url=response.url)
            raw = response.read(2_000_000).decode(response.headers.get_content_charset() or "utf-8",
                                                  errors="replace")
        parser = Document()
        parser.feed(raw)
        body = " ".join(parser.parts)
        result["characters"] = len(body)
        for label, pattern in PATTERNS.items():
            match = re.search(pattern, body, re.I)
            if match:
                result["signals"][label] = body[max(0, match.start()-50):match.end()+70]
    except HTTPError as error:
        result.update(status=error.code, resolved_url=error.url)
    except (OSError, ValueError, LookupError) as error:
        result["error"] = type(error).__name__
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cached", action="store_true", help="Render using the committed HTTP evidence")
    args = parser.parse_args()
    apps = load_apps()
    review = json.loads((ROOT / "review.json").read_text())
    supplemental = json.loads((ROOT / "sources.json").read_text())
    evidence_file = DIST / "evidence.json"
    urls = dict.fromkeys(url for app in apps for url in
                        [app["url"], *review.get(str(app["id"]), {}).get("sources", []),
                         supplemental.get(str(app["id"]), {}).get("url")] if url)
    if args.cached:
        run = json.loads(evidence_file.read_text())
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = dict(zip(urls, pool.map(fetch, urls)))
        run = {"observed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "pages": results}
        evidence_file.write_text(json.dumps(run, ensure_ascii=False, indent=2))
    graded = []
    for app in apps:
        correction = review.get(str(app["id"]), {})
        claims = correction.get("claims", {})
        for field, value in claims.items():
            graded.append({"app": app["name"], "field": field, "initial": app[field],
                           "expected": value, "match": app[field] == value})
        app.update(claims)
        for field in ("note", "surface"):
            if field in correction:
                app[field] = correction[field]
        extra = supplemental.get(str(app["id"]), {})
        app["mcp"] = extra.get("mcp", app["mcp"])
        app["sources"] = list(dict.fromkeys(url for url in
                             [*correction.get("sources", []), extra.get("url"), app["url"]] if url))
        app["review"] = correction.get("finding")
        checked = [run["pages"].get(url, {}) for url in app["sources"]]
        app["evidence"] = next((page for page in checked if page.get("status") == 200), checked[0])
        app["signals"] = sorted({signal for page in checked for signal in page.get("signals", {})})
        app["follow_up"] = []
        if not any(page.get("status") == 200 for page in checked):
            app["follow_up"].append("Find a reachable vendor source")
        if app["access"] == "u":
            app["follow_up"].append("Confirm credential entitlement")
        if "mcp" in app["signals"] and app["mcp"] == "Unconfirmed":
            app["follow_up"].append("Check whether the MCP mention is a toolkit surface")
        app["auth_label"] = " + ".join(AUTH[key] for key in app["auth"].split(","))
        app["access_label"] = ACCESS[app["access"]]
        app["verdict"] = correction.get("verdict", VERDICT[app["access"]])
    sampled = {app["name"]: app for app in apps}
    for claim in graded:
        claim["reconciled"] = sampled[claim["app"]][claim["field"]] == claim["expected"]
    rng = random.Random(20261123)
    with (DIST / "human-audit.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["app", "category", "starting_url", "observed_auth", "observed_access",
                         "observed_surface", "observed_mcp", "supporting_urls", "notes"])
        for category in CATEGORIES:
            eligible = [app for app in apps if app["category"] == category and not app["review"]]
            app = rng.choice(eligible)
            writer.writerow([app["name"], category, app["sources"][0]])
    snapshot = {"apps": apps, "claims": graded, "observed_utc": run["observed_utc"],
                "seed_ok": sum(run["pages"].get(app["url"], {}).get("status") == 200 for app in apps)}
    (DIST / "data.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))
    payload = json.dumps(snapshot, ensure_ascii=False).replace("<", "\\u003c")
    template = (ROOT / "page.html").read_text()
    (DIST / "index.html").write_text(template.replace("<!-- DATA -->", payload))
    print(f"{len(apps)} apps; {sum(c['match'] for c in graded)}/{len(graded)} initial sample claims agree")
    print(f"{sum(row['status'] == 200 for row in run['pages'].values())}/{len(run['pages'])} evidence URLs returned HTTP 200")


if __name__ == "__main__":
    main()
