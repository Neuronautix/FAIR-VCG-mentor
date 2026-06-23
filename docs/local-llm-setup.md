# Running FAIR-VCG Mentor with a local LLM

FAIR-VCG Mentor can run its LLM-assisted features entirely on-device against an
OpenAI-compatible local server (LM Studio serving Gemma or APERTUS). No data
leaves your machine and no cloud API key is required.

## 1. Install LM Studio and a model

1. Install [LM Studio](https://lmstudio.ai/).
2. In the **Discover** tab, download a chat model. Recommended:
   - **Gemma 3** — e.g. `google/gemma-3-27b-it` (or a smaller `gemma-3-4b-it`
     on modest hardware).
   - **APERTUS** — e.g. `swiss-ai/apertus-8b-instruct`.

## 2. Start the local server (OpenAI-compatible, port 1234)

In LM Studio open the **Developer / Local Server** tab, load your model, and
**Start Server**. It listens on `http://localhost:1234/v1` by default and speaks
the OpenAI chat-completions API. Note the exact **model id** shown in the server
panel — you will use it as `LLM_MODEL`.

## 3. Configure the backend env

Copy the local-LLM env template and adjust `LLM_MODEL` to match the id served:

```bash
cp backend/.env.local-llm.example backend/.env
# edit backend/.env: set LLM_MODEL to your served model id
```

Key values (see the file for the rest):

| Var | Value |
|-----|-------|
| `LLM_PROVIDER` | `openai` |
| `LLM_BASE_URL` | `http://localhost:1234/v1` (host) |
| `LLM_MODEL` | the model id from LM Studio |
| `LLM_API_KEY` | `lm-studio` (ignored by LM Studio, but required by the client) |
| `ENABLE_ONLINE_ENRICHMENT` | `false` (fully local) |

## 4. Smoke-test the endpoint

With the LM Studio server running, confirm connectivity from the repo root:

```bash
python backend/scripts/llm_smoke.py
```

It prints the active provider config, makes one real `echo_check` call, and
exits `0` on success. If it exits non-zero, check that the server is running,
the port matches `LLM_BASE_URL`, and `LLM_MODEL` matches the served id.

## 5. Run the app

Native (backend reads `backend/.env`):

```bash
docker compose up        # or run backend + frontend manually
```

Docker, pointing the backend at the host's LM Studio (handles Linux
`host.docker.internal` automatically):

```bash
docker compose -f docker-compose.yml -f docker-compose.local-llm.yml up
```

The override sets the backend to `LLM_PROVIDER=openai`,
`LLM_BASE_URL=http://host.docker.internal:1234/v1`, and a default
`LLM_MODEL=google/gemma-3-27b-it`. Override any of these from your shell, e.g.
`LLM_MODEL=swiss-ai/apertus-8b-instruct docker compose -f ... up`.

## 6. Run the eval scorecard

Once the validation harness is merged, score the local model against the
golden set:

```bash
python -m eval.run_eval --predictor llm
```

(The `eval/` harness lives on a separate branch; run this after it lands.)

## Alternative: Ollama

[Ollama](https://ollama.com/) also exposes an OpenAI-compatible API, at
`http://localhost:11434/v1`. Pull a model (`ollama pull gemma3`), then point the
backend at it:

```bash
LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL=gemma3 \
  docker compose -f docker-compose.yml -f docker-compose.local-llm.yml up
```

(For native runs, set the same `LLM_BASE_URL` / `LLM_MODEL` in `backend/.env`.)
