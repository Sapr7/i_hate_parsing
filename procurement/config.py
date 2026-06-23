# -*- coding: utf-8 -*-
import os
from pathlib import Path


def load_dotenv(path=".env"):
    for candidate in (path, "bothub.local", ".env.example"):
        p = Path(candidate)
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip().replace("\x00", "")
            v = v.strip().replace("\x00", "")
            if k:
                os.environ.setdefault(k, v)
        break


def bothub_config():
    load_dotenv()
    return {
        "endpoint": os.environ.get("BOTHUB_ENDPOINT", "https://bothub.chat/api/v2/openai/v1").rstrip("/"),
        "api_key": os.environ.get("BOTHUB_API_KEY", ""),
        "model": os.environ.get("BOTHUB_MODEL", "gpt-4o-mini"),
    }
