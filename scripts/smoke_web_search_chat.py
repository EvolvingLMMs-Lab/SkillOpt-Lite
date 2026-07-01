"""Test whether chat.completions on TRAPI supports the {'type': 'web_search'} built-in tool."""
import os, sys
from openai import AzureOpenAI
from azure.identity import (
    AzureCliCredential, ChainedTokenCredential,
    ManagedIdentityCredential, get_bearer_token_provider,
)

cred = get_bearer_token_provider(
    ChainedTokenCredential(AzureCliCredential(), ManagedIdentityCredential()),
    "api://trapi/.default",
)
deployment = sys.argv[1] if len(sys.argv) > 1 else "gpt-5.4-nano_2026-03-17"
api_version = os.environ.get("TRAPI_API_VERSION", "2025-04-01-preview")

client = AzureOpenAI(
    azure_endpoint="https://trapi.research.microsoft.com/gcr/shared",
    azure_ad_token_provider=cred,
    api_version=api_version,
)
print(f"deployment={deployment}  api_version={api_version}  endpoint=chat.completions")
try:
    resp = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "user", "content": "What month is the latest US Treasury Bulletin? Search the web. Reply with YYYY-MM only."}],
        tools=[{"type": "web_search"}],
        max_completion_tokens=2048,
    )
    msg = resp.choices[0].message
    print("content:", repr(getattr(msg, "content", None))[:300])
    print("tool_calls:", getattr(msg, "tool_calls", None))
    print("OK chat.completions accepted web_search")
except Exception as e:
    print("ERROR:", type(e).__name__, str(e)[:600])
