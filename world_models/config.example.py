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
# AVAILABLE_MODELS — declare what models you have (Option B)
#
# The tier system will automatically select the best model for each role
# from this list based on the capability annotation. If a per-field override
# (e.g. TIER_LOCAL_REASON_MODEL) is also set, the per-field override wins.
#
# Required fields per entry:
#   name       — exact model identifier string used in API calls
#   provider   — one of: "anthropic", "openai", "deepseek", "lm_studio"
#   capability — one of: "capable", "standard", "fast", "local", "local-fast"
#
# Leave as an empty list [] to rely entirely on per-field overrides or defaults.
# ---------------------------------------------------------------------------
AVAILABLE_MODELS: list[dict] = [
    # Examples — uncomment and edit to match your setup:
    # {"name": "claude-opus-4-6",          "provider": "anthropic",  "capability": "capable"},
    # {"name": "claude-sonnet-4-6",         "provider": "anthropic",  "capability": "standard"},
    # {"name": "claude-haiku-4-5-20251001", "provider": "anthropic",  "capability": "fast"},
    # {"name": "qwen3.5",                   "provider": "lm_studio",  "capability": "local"},
    # {"name": "qwen2.5-3b-instruct",       "provider": "lm_studio",  "capability": "local-fast"},
]

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

# ---------------------------------------------------------------------------
# Archivist model (LM Studio local call for claim extraction)
# ---------------------------------------------------------------------------
# Default: "qwen2.5-3b-instruct"
ARCHIVIST_MODEL: str | None = None

# ---------------------------------------------------------------------------
# Speech-to-Text (OpenAI Whisper API)
# ---------------------------------------------------------------------------
# Default: "whisper-1"
STT_MODEL: str | None = None

# ---------------------------------------------------------------------------
# Text-to-Speech (OpenAI TTS API)
# ---------------------------------------------------------------------------
# Default model: "tts-1"
TTS_MODEL: str | None = None
# Default voice: "fable"  — OpenAI options: alloy, echo, fable, onyx, nova, shimmer
TTS_VOICE: str | None = None

# ---------------------------------------------------------------------------
# Embedding model (LM Studio local call for vector memory)
# ---------------------------------------------------------------------------
# Default: "text-embedding-nomic-embed-text-v1.5@q8_0"
#
# WARNING: This determines the vector dimensions stored in Neo4j.
# Set this ONCE at initial setup, before storing any data.
# Changing it after vectors are stored will silently break memory retrieval.
# If you change it, you must re-index: delete all Observation nodes and
# re-run the migration to rebuild the vector index with the new dimensions.
EMBEDDING_MODEL: str | None = None
