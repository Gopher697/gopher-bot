from __future__ import annotations


def get_bot_name() -> str:
    try:
        from world_models import config

        return str(getattr(config, "BOT_NAME", "gopher-bot")).strip() or "gopher-bot"
    except Exception:
        return "gopher-bot"


BOT_NAME = get_bot_name()
