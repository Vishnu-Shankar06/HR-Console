import urllib.request
import urllib.error
import json

base_url = "http://16.113.145.53:8088"

paths = [
    "",
    "/docs",
    "/openapi.json",
    "/swagger",
    "/swagger.json",
    "/api",
    "/api/v1",
    "/api/v1/docs",
    "/redoc",
    "/health",
    "/login",
    "/api/login",
    "/api/v1/login",
    "/api/v1/auth/login",
    "/token",
    "/api/v1/token",
    "/rag",
    "/builder",
    "/rag-builder",
]

for p in paths:
    url = f"{base_url}{p}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as res:
            ct = res.headers.get("Content-Type", "")
            server = res.headers.get("Server", "")
            data = res.read(250).decode("utf-8", errors="ignore")
            print(f"[SUCCESS {res.status}] {p} (Type: {ct}, Server: {server}): {data[:120]}")
    except urllib.error.HTTPError as e:
        server = e.headers.get("Server", "")
        ct = e.headers.get("Content-Type", "")
        body = e.read(250).decode("utf-8", errors="ignore")
        print(f"[{e.code}] {p} (Server: {server}, Type: {ct}): {body.strip()[:100]}")
    except Exception as e:
        print(f"[ERR] {p}: {e}")
