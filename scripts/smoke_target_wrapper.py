"""Sanity: call our SkillOpt target wrapper with nano + web_search."""
import os, sys
os.environ.setdefault("TARGET_AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://trapi.research.microsoft.com/gcr/shared")
os.environ.setdefault("AZURE_OPENAI_AUTH_MODE", "azure_cli")
os.environ.setdefault("AZURE_OPENAI_AD_SCOPE", "api://trapi/.default")

# Tell the router/loader to use openai_chat backend
sys.path.insert(0, ".")
from skillopt.model import backend_config as _bc
from skillopt.model import azure_openai as _az

_bc.set_target_backend("openai_chat")
_az.set_target_deployment("gpt-5.4-nano_2026-03-17")

msg, usage = _az.chat_target_messages(
    messages=[
        {"role": "system", "content": "Answer concisely. Use the web_search tool when you need fresh info."},
        {"role": "user", "content": "What is the YYYY-MM of the latest US Treasury Bulletin? Just the month."},
    ],
    max_completion_tokens=2048,
    retries=2,
    stage="smoke",
    return_message=True,
    tools=[{"type": "web_search"}],
)
print("content:", repr(getattr(msg, "content", None))[:300])
print("usage:", usage)
