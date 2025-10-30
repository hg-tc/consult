#!/usr/bin/env python3
import os
import sys
import json
import urllib.parse
import urllib.request


def main():
    if len(sys.argv) < 2:
        print("用法: test_searxng_search.py <查询词> [endpoint]", file=sys.stderr)
        print("示例: test_searxng_search.py OpenAI http://127.0.0.1:8088", file=sys.stderr)
        sys.exit(1)

    query = sys.argv[1]
    endpoint = (
        sys.argv[2]
        if len(sys.argv) >= 3
        else os.environ.get("SEARXNG_ENDPOINT", "http://127.0.0.1:8088")
    ).rstrip("/")

    params = {
        "q": query,
        "format": "json",
        "language": "zh-CN",
        "safesearch": "1",
        "categories": "general",
    }
    url = f"{endpoint}/search?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Referer": endpoint + "/",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
            payload = json.loads(data.decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"请求失败: {e}", file=sys.stderr)
        sys.exit(2)

    results = payload.get("results", [])
    print(f"共返回 {len(results)} 条结果 (endpoint={endpoint})\n")
    for i, r in enumerate(results[:10], start=1):
        title = r.get("title") or r.get("url") or "(无标题)"
        url_item = r.get("url", "")
        snippet = r.get("content") or r.get("pretty_url") or ""
        print(f"[{i}] {title}\n    {url_item}\n    {snippet[:160]}\n")


if __name__ == "__main__":
    main()


