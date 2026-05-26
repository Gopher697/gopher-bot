from __future__ import annotations

# Optional config field: USER_TIMEZONE (IANA timezone name) defaults to "UTC".
# Orientation imports it defensively so older config.py files keep working.


def get_bot_name() -> str:
    try:
        from world_models import config

        return str(getattr(config, "BOT_NAME", "gopher-bot")).strip() or "gopher-bot"
    except Exception:
        return "gopher-bot"


BOT_NAME = get_bot_name()
