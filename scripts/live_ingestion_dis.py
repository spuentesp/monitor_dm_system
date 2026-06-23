#!/usr/bin/env python3
"""Run ingestion on the real Death In Space book."""

import requests
import time
import os
import sys
from pathlib import Path

DEFAULT_API_URL = os.environ.get("MONITOR_API_URL", "http://localhost:8001/api")

def _api(http, method, base, path):
    url = f"{base}{path}"
    resp = http.request(method, url)
    resp.raise_for_status()
    return resp.json()

def main():
    api_url = DEFAULT_API_URL
    http = requests.Session()
    
    # Path to DiS
    pdf_path = Path("./.local_storage/monitor/uploads/5f5b7414-3010-41d4-bd38-13ca7f7ce896/20260405_180523_Death_in_Space_Core_Rules.pdf")
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        return 1

    title = f"DiS Observe {int(time.time())}"
    print(f"Uploading {pdf_path} as '{title}'...")
    with open(pdf_path, "rb") as f:
        resp = http.post(
            f"{api_url}/ingest/sources/upload",
            files={"file": ("Death_in_Space.pdf", f, "application/pdf")},
            data={
                "scan_type": "full",
                "analysis_layers": ["entities", "lore", "axioms"],
                "ingest_now": "true",
                "title": title,
            },
            timeout=120,
        )
        resp.raise_for_status()
    
    print("Upload complete. Waiting for job to finish...")
    t0 = time.time()
    
    while True:
        jobs = _api(http, "GET", api_url, "/ingest/jobs")
        match = [j for j in jobs if j.get("source_title") == title]
        if match:
            job = match[0]
            status = job.get("status")
            print(f"Status: {status} ({int(time.time() - t0)}s elapsed)")
            if status in ("completed", "failed", "error", "cancelled"):
                print("Job finished!")
                print("Errors:", job.get("errors"))
                break
        time.sleep(10)
        if time.time() - t0 > 14400: # 4 hours max
            print("Timeout!")
            break

if __name__ == "__main__":
    sys.exit(main())
