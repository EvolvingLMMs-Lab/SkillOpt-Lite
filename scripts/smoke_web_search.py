"""Smoke test: does our TRAPI deployment support the built-in web_search tool via Responses API?"""
from __future__ import annotations

import os
import sys

from openai import AzureOpenAI
from azure.identity import (
    AzureCliCredential,
    ChainedTokenCredential,
    ManagedIdentityCredential,
    get_bearer_token_provider,
)

scope = "api://trapi/.default"
credential = get_bearer_token_provider(
    ChainedTokenCredential(AzureCliCredential(), ManagedIdentityCredential()),
    scope,
)

# Use a Responses-API model. gpt-5.4-pro is in our _RESPONSES_API_MODELS set.
# Allow CLI override: python smoke_web_search.py <deployment>
deployment = sys.argv[1] if len(sys.argv) > 1 else "gpt-5.4-pro_2026-03-05"
api_version = os.environ.get("TRAPI_API_VERSION", "2025-04-01-preview")
instance = "gcr/shared"
endpoint = f"https://trapi.research.microsoft.com/{instance}"

client = AzureOpenAI(
    azure_endpoint=endpoint,
    azure_ad_token_provider=credential,
    api_version=api_version,
)

print(f"deployment={deployment}  api_version={api_version}")
try:
    resp = client.responses.create(
        model=deployment,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "What is the current US Treasury Bulletin date? Search the web and respond with just the YYYY-MM.",
                    }
                ],
            }
        ],
        tools=[{"type": "web_search"}],
        max_output_tokens=2048,
    )
    print("STATUS:", getattr(resp, "status", "?"))
    for item in getattr(resp, "output", []) or []:
        kind = getattr(item, "type", type(item).__name__)
        print("-- output item:", kind)
        # message-type items have content blocks
        if kind == "message":
            for blk in getattr(item, "content", []) or []:
                t = getattr(blk, "type", "?")
                txt = getattr(blk, "text", None)
                print("   block", t, repr(txt)[:300] if txt else "")
        elif "search" in kind.lower():
            print("   ", repr(item)[:400])
    print("OK")
except Exception as e:  # noqa: BLE001
    print("ERROR:", type(e).__name__, str(e)[:600])
