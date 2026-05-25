from __future__ import annotations

# The name this bot identifies itself as at runtime.
# Change this to personalise your instance.
BOT_NAME = "gopher-bot"
# Rename to config.py and fill in all values before running.

NEO4J_URI = "neo4j://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your-neo4j-password-here"
NEO4J_DATABASE = "neo4j"
MEDIA_ROOT = r"C:\path\to\your\media-folder"
ANTHROPIC_API_KEY = "your-anthropic-key-here"
OPENAI_API_KEY = "your-openai-key-here"
LM_STUDIO_API_KEY = "your-lm-studio-key-here"  # optional — only needed if using LM Studio

# ---------------------------------------------------------------------------
# Optional model overrides
# Set any of these to a model name string to override the tier default.
# Leave as None to use the built-in default.
# ---------------------------------------------------------------------------

# TIER_LOCAL defaults: reason="qwen3.5", sensory="qwen2.5-3b-instruct"
TIER_LOCAL_REASON_MODEL: str | None = None
TIER_LOCAL_SENSORY_MODEL: str | None = None

# TIER_STANDARD defaults: reason="claude-sonnet-4-6", sensory="claude-haiku-4-5-20251001"
TIER_STANDARD_REASON_MODEL: str | None = None
TIER_STANDARD_SENSORY_MODEL: str | None = None

# TIER_ENHANCED defaults: reason="claude-opus-4-6", sensory="claude-haiku-4-5-20251001"
TIER_ENHANCED_REASON_MODEL: str | None = None
TIER_ENHANCED_SENSORY_MODEL: str | None = None
