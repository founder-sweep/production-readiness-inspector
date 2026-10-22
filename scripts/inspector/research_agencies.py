#!/usr/bin/env python3
"""Read official prospect pages into private research, never contact a prospect."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.links = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        encoded = values.get("data-cfemail")
        if encoded:
            try:
                key = int(encoded[:2], 16)
                self.text.append("".join(chr(int(encoded[i:i + 2], 16) ^ key) for i in range(2, len(encoded), 2)))
            except ValueError:
                pass
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.text.append(" ".join(data.split()))


def read(url):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; Inspector public-page research)"})
    with urlopen(request, timeout=18) as response:
        raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError("page_too_large")
        final = response.url
    page = Page()
    page.feed(raw.decode("utf-8", errors="replace"))
    text = "\n".join(page.text)
    emails = sorted(set(re.findall(r"[A-Za-z0-9_.+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text + " " + " ".join(page.links))))
    contacts = sorted({urljoin(final, value) for value in page.links if re.search(r"/(?:en/)?(?:contact|contacts|contact-us|connect)(?:[/?#]|$)|#contact", value, re.IGNORECASE) and value.startswith(("/", "http")) and urlparse(urljoin(final, value)).netloc == urlparse(final).netloc})
    evidence = [line[:450] for line in page.text if re.search(r"fast.?api|python|django|hand.?over|maintenance|ongoing|support", line, re.IGNORECASE)][:18]
    return {"url": final, "sha256": hashlib.sha256(raw).hexdigest(), "emails": emails, "contact_links": contacts[:6], "evidence": evidence, "text": text}


def main():
    root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    runtime = root / ".mcp-products/inspector/marketing"
    seeds = json.loads((runtime / "prospect-seeds.private.json").read_text())
    output = runtime / "research"
    output.mkdir(exist_ok=True, mode=0o700)

    def one(item):
        index, (name, url) = item
        path = output / f"{index:02}.private.json"
        if path.exists():
            prior = json.loads(path.read_text())
            if prior.get("url_requested") == url and not prior.get("error") and prior.get("parser_version") == 2:
                return prior
        record = {"id": f"I{index:02}", "company": name, "url_requested": url, "checked_on": "2026-10-22", "parser_version": 2}
        try:
            record["service"] = read(url)
            links = record["service"]["contact_links"]
            if links:
                try:
                    record["contact"] = read(links[0])
                except Exception as exc:  # noqa: BLE001 - keep failed prospects explicit
                    record["contact_error"] = type(exc).__name__
        except Exception as exc:  # noqa: BLE001
            record["error"] = type(exc).__name__
        path.write_text(json.dumps(record, indent=2))
        path.chmod(0o600)
        return record

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for record in pool.map(one, enumerate(seeds, 1)):
            service = record.get("service", {})
            contact = record.get("contact", {})
            print(json.dumps({"id": record["id"], "company": record["company"], "error": record.get("error"), "emails": sorted(set(service.get("emails", []) + contact.get("emails", []))), "contact": contact.get("url", service.get("contact_links", [])), "evidence": service.get("evidence", [])[:4]}), flush=True)


if __name__ == "__main__":
    main()
