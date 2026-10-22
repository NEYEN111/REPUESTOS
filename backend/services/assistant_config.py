"""Read backend environment settings without exposing secrets in logs."""
import os

from backend.db import ROOT


def env_value(name):
    value = os.getenv(name, "").strip()
    if value:
        return value.strip("\"'")
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
            key, separator, item = line.partition("=")
            if separator and key.strip() == name:
                return item.strip().strip("\"'")
    except OSError:
        pass
    return ""
