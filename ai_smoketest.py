import json
import os
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def run():
    key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "gpt-5.6-luna").strip() or "gpt-5.6-luna"
    if not key:
        print("AI self-test: FAIL missing key", flush=True)
        return False
    payload = {
        "model": model,
        "input": "فقط عبارت تست موفق را بنویس.",
        "max_output_tokens": 40,
        "store": False,
    }
    req = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
    )
    try:
        with urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            msg = json.loads(detail).get("error", {}).get("message", "")
        except Exception:
            msg = detail
        print(f"AI self-test: FAIL HTTP {e.code} {msg[:240]}", flush=True)
        return False
    except Exception as e:
        print(f"AI self-test: FAIL {type(e).__name__}: {str(e)[:200]}", flush=True)
        return False

    texts = []
    for item in data.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for c in item.get("content", []) or []:
            if c.get("type") == "output_text" and c.get("text"):
                texts.append(c["text"])
    ok = bool(data.get("id")) and bool(texts)
    print(f"AI self-test: {'PASS' if ok else 'FAIL no output'} model={model}", flush=True)
    return ok
