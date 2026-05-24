"""
Discord bridge for Gopher-bot.

Receives messages from a Discord channel and routes them through Awareness.
Modelled on the GopherVault discord_vault_bridge.py structure.

Setup
-----
1. Create a Discord application + bot at https://discord.com/developers/applications
2. Enable "Message Content Intent" under Bot → Privileged Gateway Intents
3. Add  DISCORD_BOT_TOKEN = "<your token>"  to world_models/config.py
4. Optionally add  DISCORD_CHANNEL = "your-channel-name"  (default: "gopher")
5. Invite the bot to your server with scopes: bot, permissions: Send Messages / Read Message History
6. Run:  python interface/discord_bot.py

The bridge also starts automatically from server.py if a token is configured
and the module is importable (no extra step needed when running the full stack).
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import discord
except ModuleNotFoundError:
    print("Missing package: discord.py")
    print("Install with:  pip install discord.py")
    raise SystemExit(1)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from interface import bot  # noqa: E402


# ── Config helpers ─────────────────────────────────────────────────────────


def _config_str(attr: str, env_var: str, default: str = "") -> str:
    """Read a string setting from world_models/config.py, then env, then default."""
    import os

    try:
        from world_models import config

        value = str(getattr(config, attr, "")).strip()
        if value:
            return value
    except Exception:
        pass
    return os.environ.get(env_var, default).strip()


DISCORD_TOKEN: str = _config_str("DISCORD_BOT_TOKEN", "GOPHER_DISCORD_TOKEN")
DISCORD_CHANNEL: str = _config_str("DISCORD_CHANNEL", "GOPHER_DISCORD_CHANNEL", "gopher")

MAX_REPLY_CHARS = 1900          # Discord hard limit is 2000; leave headroom
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
RATE_LIMIT_MAX_MESSAGES = 30
RATE_LIMIT_WINDOW_SECONDS = 60
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".bmp"}


# ── Internal state ─────────────────────────────────────────────────────────

_rate_state: dict[str, dict] = {}
_process_lock: asyncio.Lock | None = None   # created inside the event loop


def _get_process_lock() -> asyncio.Lock:
    global _process_lock
    if _process_lock is None:
        _process_lock = asyncio.Lock()
    return _process_lock


# ── Utilities ──────────────────────────────────────────────────────────────


def _check_rate_limit(user_id: int, now: datetime) -> tuple[bool, bool]:
    """Return (allowed, should_warn)."""
    key = str(user_id)
    state = _rate_state.get(key)
    if state is None or (now - state["window_start"]).total_seconds() >= RATE_LIMIT_WINDOW_SECONDS:
        _rate_state[key] = {"window_start": now, "count": 1, "warned": False}
        return True, False
    state["count"] += 1
    if state["count"] <= RATE_LIMIT_MAX_MESSAGES:
        return True, False
    if not state["warned"]:
        state["warned"] = True
        return False, True
    return False, False


def _split_reply(text: str) -> list[str]:
    """Split a long reply into Discord-sized chunks, preferring newline boundaries."""
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    while len(text) > MAX_REPLY_CHARS:
        split_at = text.rfind("\n", 0, MAX_REPLY_CHARS)
        if split_at < 500:
            split_at = MAX_REPLY_CHARS
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks


async def _read_text_attachments(message: discord.Message) -> str:
    """Read any .txt file attachments and return their combined content."""
    parts: list[str] = []
    for attachment in message.attachments:
        if not (attachment.filename or "").lower().endswith(".txt"):
            continue
        if attachment.size and attachment.size > MAX_ATTACHMENT_BYTES:
            print(f"Skipping oversized attachment: {attachment.filename}")
            continue
        try:
            data = await attachment.read()
            parts.append(data.decode("utf-8", errors="replace"))
        except Exception as exc:
            print(f"Failed to read attachment {attachment.filename}: {exc}")
    return "\n\n".join(parts)


async def _download_image_attachments(message: discord.Message) -> list[dict]:
    """
    Download image attachments and return them as a list of
    {"filename": str, "data": bytes} dicts for the Sensory coordinator.
    Skips files over MAX_ATTACHMENT_BYTES.
    """
    result = []
    for attachment in message.attachments:
        suffix = Path(attachment.filename or "").suffix.lower()
        if suffix not in IMAGE_EXTENSIONS:
            continue
        if attachment.size and attachment.size > MAX_ATTACHMENT_BYTES:
            print(f"[discord] Skipping oversized image: {attachment.filename}")
            continue
        try:
            data = await attachment.read()
            result.append({"filename": attachment.filename, "data": data})
        except Exception as exc:
            print(f"[discord] Failed to download {attachment.filename}: {exc}")
    return result


# ── Discord client ─────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready() -> None:
    print(f"[discord] Gopher-bot bridge online as {client.user}")
    print(f"[discord] Listening on channel: #{DISCORD_CHANNEL}")


@client.event
async def on_message(message: discord.Message) -> None:
    # Ignore bots (including ourselves)
    if message.author.bot:
        return

    # Only respond in the configured channel
    if getattr(message.channel, "name", "") != DISCORD_CHANNEL:
        return

    now = datetime.now(tz=timezone.utc)
    allowed, warn = _check_rate_limit(message.author.id, now)
    if not allowed:
        if warn:
            await message.reply("Slow down — too many messages.", mention_author=False)
        return

    async with _get_process_lock():
        try:
            # Combine message text with any .txt file attachments
            content = (message.content or "").strip()
            attachment_text = await _read_text_attachments(message)
            if attachment_text:
                content = f"{content}\n\n{attachment_text}".strip() if content else attachment_text

            image_attachments = await _download_image_attachments(message)

            if not content.strip():
                return

            # Route through Awareness (blocking call - run in thread pool)
            async with message.channel.typing():
                packet = await asyncio.to_thread(
                    bot.awareness.synchronous_run,
                    content,
                    image_attachments=image_attachments,
                )

            reply = bot.response_from_packet(packet)

            # Send reply in chunks if needed
            for index, chunk in enumerate(_split_reply(reply)):
                if index == 0:
                    await message.reply(chunk, mention_author=False)
                else:
                    await message.channel.send(chunk)

        except Exception as exc:
            print(f"[discord] Error processing message {message.id}: {exc}")
            await message.reply(
                "Hit an error processing that. Check the bot window for details.",
                mention_author=False,
            )


# ── Entry point ────────────────────────────────────────────────────────────


def main() -> None:
    if not DISCORD_TOKEN:
        print(
            "\n[discord] No token found.\n"
            "Add this line to world_models/config.py:\n\n"
            "    DISCORD_BOT_TOKEN = '<your bot token>'\n\n"
            "Or set the environment variable GOPHER_DISCORD_TOKEN."
        )
        raise SystemExit(1)

    print(f"[discord] Starting bridge (channel: #{DISCORD_CHANNEL})")
    client.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
