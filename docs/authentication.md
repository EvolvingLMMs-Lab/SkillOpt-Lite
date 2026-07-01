# Authentication

SkillOpt_Lite talks to LLMs through the OpenAI Python SDK. Three auth modes are
supported; you pick one via `SKILLOPT_AUTH_MODE` in `.env`.

## Mode 1 — `azure_cli`  (default)

Azure OpenAI + AAD token via `az login`. **No key needed.**

**Prereqs:**

- `az` CLI installed and `az login` completed
- your account has `Cognitive Services OpenAI User` (or higher) role on the
  Azure OpenAI resource

**`.env`:**

```dotenv
SKILLOPT_AUTH_MODE=azure_cli
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
```

**Verify:**

```bash
source ./env.sh                        # should print [env.sh] mode=azure_cli
az account get-access-token --resource https://cognitiveservices.azure.com >/dev/null && echo OK
```

Behind the scenes: the backend obtains a bearer token via
`azure-identity`'s `AzureCliCredential` (or a subprocess fallback around
`az account get-access-token`) and passes it to `openai.AzureOpenAI` via
`azure_ad_token_provider`.

If you use a custom AAD scope (e.g. an internal gateway), override with
`AZURE_OPENAI_AD_SCOPE=...` before sourcing.

## Mode 2 — `azure_key`

Azure OpenAI + resource api key. Simplest for shared / headless setups.

**`.env`:**

```dotenv
SKILLOPT_AUTH_MODE=azure_key
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
AZURE_OPENAI_API_KEY=<your-key-from-azure-portal>
```

**Verify:**

```bash
source ./env.sh
curl -s "${AZURE_OPENAI_ENDPOINT%/}/openai/deployments?api-version=${AZURE_OPENAI_API_VERSION}" \
     -H "api-key: ${AZURE_OPENAI_API_KEY}" | head -c 200
```

## Mode 3 — `openai`

Official OpenAI *or* any OpenAI-compatible server (vLLM, ollama, together.ai,
groq, deepinfra, …). Uses the plain `openai.OpenAI(base_url=, api_key=)`
client, no Azure gymnastics.

**`.env` (official OpenAI):**

```dotenv
SKILLOPT_AUTH_MODE=openai
OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL defaults to https://api.openai.com/v1 — omit to use official
```

**`.env` (local vLLM example):**

```dotenv
SKILLOPT_AUTH_MODE=openai
OPENAI_API_KEY=EMPTY
OPENAI_BASE_URL=http://localhost:8000/v1
```

**Verify:**

```bash
source ./env.sh
curl -s "${OPENAI_BASE_URL}/models" -H "Authorization: Bearer ${OPENAI_API_KEY}" | head -c 200
```

**Note on model names:** in this mode the value you pass to
`--target_model` on `run.sh` must be a valid model id at your endpoint
(`gpt-4o`, `gpt-4o-mini`, `o3-mini`, `meta-llama/Meta-Llama-3-8B-Instruct`,
…). For Azure modes it must match your **deployment name** (which may or
may not equal the model name).

## Optimizer vs target overrides

SkillOpt_Lite supports separate endpoints for the **optimizer** (proposes skill
patches) and the **target** (rolls out the agent). Prefix a var with
`OPTIMIZER_` or `TARGET_` and it overrides the shared value:

```dotenv
# Target = cheap local model; optimizer = frontier
SKILLOPT_AUTH_MODE=openai
OPENAI_API_KEY=sk-...
TARGET_AZURE_OPENAI_ENDPOINT=http://localhost:8000/v1
TARGET_AZURE_OPENAI_AUTH_MODE=openai_compatible
OPTIMIZER_AZURE_OPENAI_ENDPOINT=https://api.openai.com/v1
OPTIMIZER_AZURE_OPENAI_AUTH_MODE=openai_compatible
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Unauthorized. Invalid or expired token.` | `az login` expired; or wrong `AZURE_OPENAI_AD_SCOPE`. Re-run `az login` and re-`source env.sh`. |
| `401` in openai mode | Wrong `OPENAI_API_KEY` — regenerate on platform.openai.com. |
| `404 Deployment not found` (Azure) | `--target_model` must equal the *deployment name* in the Azure portal, not the model id. |
| `Endpoint is not configured` | You didn't `source ./env.sh` in this shell. |
