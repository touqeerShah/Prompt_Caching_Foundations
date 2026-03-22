The purpose is not “make the model smarter.”
The purpose is to make prompt structure measurable and reusable so later you can improve cacheability and latency.

OpenAI’s prompt caching guide says cache hits require an exact repeated prefix, and advises putting static content first and variable content later. Anthropic’s prompt caching docs describe prompt caching as resuming from specific prefixes in repeated prompts.

What we will build

We will extend your local lab into 3 prompt strategies:

Version A — bad

Version B — better

Version C — best

And we will measure:

prompt fingerprint

static prefix fingerprint

prefix similarity across calls

TTFT

total latency

For now, this can run fully local with Ollama.
Later, the same structure can be tested on OpenAI or Anthropic for real cached-token behavior. OpenAI also notes prompt caching works automatically for repeated prefixes on sufficiently long prompts, and their cookbook currently documents exact prefix matching and token thresholds for automatic cache
What you should learn in this part
1. Prompt segmentation

You want to explicitly separate:

system instructions

tool schemas

org policy

tenant/user config

retrieved context

current question

2. Canonicalization

You want prompt generation to be deterministic:

fixed whitespace

stable casing where possible

stable JSON serialization

deterministic ordering

no random insertion order

no unnecessary timestamps or request IDs in the reusable prefix

3. Prefix stability

You want to see which parts stay identical across requests and which parts change.
## Part 1 — Prefix and prompt design for token reuse

This is where “token reuse efficiency” starts.

Your main rule is correct:
Put **stable shared instructions first**, and **dynamic user/request-specific content later**. Exact prefix reuse matters because even small changes can reduce cacheability. OpenAI’s caching guide notes exact repeated prefix matching is required for cache hits, and Anthropic’s prompt caching is also prefix-oriented. ([Claude API Docs][3])

### What to learn

* separate prompt into:

  * system instructions
  * tool schemas
  * common org policy
  * user profile / tenant config
  * retrieved context
  * current question
* canonicalization:

  * fixed whitespace
  * fixed casing where possible
  * stable JSON serialization
  * deterministic ordering of tool definitions and retrieved chunks

### What to build

Build 3 prompt versions for the same app:

**Version A — bad**

* random ordering
* extra spaces/newlines
* dynamic data inserted near the top

**Version B — better**

* stable system prompt first
* retrieved docs after instructions
* user question last

**Version C — best**

* exact canonical serialization
* static prefix isolated
* dynamic suffix only

### What to measure

* prefix similarity across calls
* cache hit rate
* average cached tokens
* TTFT

### Local or paid?

* **Local model:** good for testing prompt organization and request structure
* **Paid API:** needed to test true provider-native prompt caching behavior

### Best tools

* local: Ollama, vLLM, llama.cpp
* paid: OpenAI API, Anthropic API

---


Install dependencies with `uv`:

```bash
uv sync
```

If you prefer a manual virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```


uvicorn app:app --port 8001 --reload

Then run benchmark:

python benchmark_prompt_versions.py



Use these against your local FastAPI app running on:

```bash
http://127.0.0.1:8001
```

Start server first:

```bash
uvicorn app:app --reload
```

---

# Experiment 1 — same exact request, A vs B vs C

Goal:
compare

* static prefix hash stability
* TTFT
* total tokens

Run the **same request** three times, only changing `prompt_version`.

## A — bad

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why stable prompt prefixes improve token reuse.",
    "use_retrieval": true,
    "prompt_version": "a",
    "user_id": "user-123",
    "tenant_id": "tenant-001"
  }'
```

Respone: 
{
   "request_id":"9ddbe92e-021e-41fd-b1a6-f6227779274c",
   "model":"qwen2.5-coder:7b",
   "prompt_version":"a",
   "answer":"Stable prompt prefixes improve token reuse because they allow the model to recognize and leverage patterns in the input. By keeping the prefix consistent across calls, the model can more efficiently identify the structure of the request, leading to better performance and faster response times. This consistency helps in caching the outputs associated with these prefixes, reducing the need for reprocessing similar requests, thus optimizing resource usage and improving overall efficiency.",
   "prompt_preview":"[SYSTEM]
   
   You are a helpful assistant.
   Answer clearly and briefly.
   Use provided context when relevant.
   If context is insufficient, say what is missing.
   
   
   
   
   [TOOLS]
   [
     {
       \"name\": \"search_docs\",
       \"description\": \"Search internal documents\",
       \"parameters\": {
         \"type\": \"object\",
         \"properties\": {
           \"query\": {
             \"type\": \"string\"
           },
           \"top_k\": {
             \"type\": \"integer\"
           }
         },
         \"required\": [
           \"query\"
         ]
       }
     },
     {
       \"name\": \"lookup_user_profile\",
       \"description\": \"Look up the user's profile configuration\",
       \"parameters\": {
         \"type\": \"object\",
         \"properties\": {
           \"user_id\": {
             \"type\": \"string\"
           }
         },
         \"required\": [
           \"user_id\"
         ]
       }
     }
   ]
   
   
   
   [USER_MESSAGE]
   
   Explain why stable prompt prefixes improve token reuse.
   
   
   
   [CONTEXT]
   - doc-3: Prompt structure matters: stable instructions should stay fixed, while user-specific data should stay dynamic.
   - doc-4: Prompt caching works best when the repeated prefix remains identical across calls.
   
   
   
   [TENANT]
   {
     \"tenant_id\": \"tenant-001\",
     \"user_id\": \"user-123\",
     \"language\": \"en\",
     \"persona\": \"support_assistant\",
     \"region\": \"eu\"
   }
   
   
   
   [ORG_POLICY]
   {
     \"tone\": \"professional\",
     \"citation_policy\": \"cite context when available\",
     \"privacy_policy\": \"do not reveal secrets\"
   }
   
   
   [ASSISTANT]
   ",
   "prompt_stats":{
      "prompt_version":"a",
      "total_tokens":342,
      "static_prefix_tokens":0,
      "tokenizer_name":"Qwen/Qwen2.5-7B-Instruct",
      "count_method":"real_tokenizer",
      "has_retrieval_context":true,
      "full_prompt_sha256":"20a4ff69698a274b5ed66328838505a4f79a97fc6f207642ea888348c29738fc",
      "static_prefix_sha256":null,
      "full_prompt_chars":1379,
      "static_prefix_chars":0
   },
   "timings":{
      "retrieval_ms":0.07,
      "prompt_assembly_ms":0.4,
      "ttft_ms":8272.82,
      "model_total_ms":11404.9,
      "total_ms":11405.86
   },
   "retrieved_docs":[
      {
         "id":"doc-3",
         "text":"Prompt structure matters: stable instructions should stay fixed, while user-specific data should stay dynamic."
      },
      {
         "id":"doc-4",
         "text":"Prompt caching works best when the repeated prefix remains identical across calls."
      }
   ]
},

## B — better

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why stable prompt prefixes improve token reuse.",
    "use_retrieval": true,
    "prompt_version": "b",
    "user_id": "user-123",
    "tenant_id": "tenant-001"
  }'
```
Response: 

{
   "request_id":"7f825e6b-2cd5-48c7-8222-b37fd50bed67",
   "model":"qwen2.5-coder:7b",
   "prompt_version":"b",
   "answer":"Stable prompt prefixes allow for better token reuse because they ensure that the model recognizes and reuses previously generated tokens. This is particularly useful in scenarios where the same instructions or prompts are repeated, as it can lead to more efficient processing and potentially reduced computation time.",
   "prompt_preview":"[SYSTEM]
   You are a helpful assistant.
   Answer clearly and briefly.
   Use provided context when relevant.
   If context is insufficient, say what is missing.
   
   [ORG_POLICY]
   {
     \"tone\": \"professional\",
     \"citation_policy\": \"cite context when available\",
     \"privacy_policy\": \"do not reveal secrets\"
   }
   
   [TOOLS]
   [
     {
       \"name\": \"search_docs\",
       \"description\": \"Search internal documents\",
       \"parameters\": {
         \"type\": \"object\",
         \"properties\": {
           \"query\": {
             \"type\": \"string\"
           },
           \"top_k\": {
             \"type\": \"integer\"
           }
         },
         \"required\": [
           \"query\"
         ]
       }
     },
     {
       \"name\": \"lookup_user_profile\",
       \"description\": \"Look up the user's profile configuration\",
       \"parameters\": {
         \"type\": \"object\",
         \"properties\": {
           \"user_id\": {
             \"type\": \"string\"
           }
         },
         \"required\": [
           \"user_id\"
         ]
       }
     }
   ]
   
   [TENANT]
   {
     \"tenant_id\": \"tenant-001\",
     \"user_id\": \"user-123\",
     \"language\": \"en\",
     \"persona\": \"support_assistant\",
     \"region\": \"eu\"
   }
   
   [CONTEXT]
   - doc-3: Prompt structure matters: stable instructions should stay fixed, while user-specific data should stay dynamic.
   - doc-4: Prompt caching works best when the repeated prefix remains identical across calls.
   
   [USER]
   Explain why stable prompt prefixes improve token reuse.
   
   [ASSISTANT]
   ",
   "prompt_stats":{
      "prompt_version":"b",
      "total_tokens":341,
      "static_prefix_tokens":279,
      "tokenizer_name":"Qwen/Qwen2.5-7B-Instruct",
      "count_method":"real_tokenizer",
      "has_retrieval_context":true,
      "full_prompt_sha256":"32789292eda49a59ec79ac54996c5004fe619a0a4239f68a3918a4243ef676cb",
      "static_prefix_sha256":"a9b3402f224eafe23d5df537875dbe94cb442a9ef212dc352f2573088b0e0e8e",
      "full_prompt_chars":1357,
      "static_prefix_chars":1057
   },
   "timings":{
      "retrieval_ms":0.05,
      "prompt_assembly_ms":0.28,
      "ttft_ms":3451.39,
      "model_total_ms":5407.7,
      "total_ms":5408.07
   },
   "retrieved_docs":[
      {
         "id":"doc-3",
         "text":"Prompt structure matters: stable instructions should stay fixed, while user-specific data should stay dynamic."
      },
      {
         "id":"doc-4",
         "text":"Prompt caching works best when the repeated prefix remains identical across calls."
      }
   ]
}

## C — best

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why stable prompt prefixes improve token reuse.",
    "use_retrieval": true,
    "prompt_version": "c",
    "user_id": "user-123",
    "tenant_id": "tenant-001"
  }'
```

{
   "request_id":"7b829990-175f-4f20-92bd-34e01eb5131d",
   "model":"qwen2.5-coder:7b",
   "prompt_version":"c",
   "answer":"Stable prompt prefixes improve token reuse because they allow for efficient caching of generated tokens. When the initial part of a prompt remains constant, language models can cache the tokens produced during that prefix. This reduces the amount of work needed to generate responses on subsequent calls with similar prompts, as the model can simply retrieve and append cached tokens rather than re-generating them from scratch.",
   "prompt_preview":"[SYSTEM]\nYou are a helpful assistant.\nAnswer clearly and briefly.\nUse provided context when relevant.\nIf context is insufficient, say what is missing.\n\n[ORG_POLICY]\n{\"citation_policy\":\"cite context when available\",\"privacy_policy\":\"do not reveal secrets\",\"tone\":\"professional\"}\n\n[TOOLS]\n[{\"description\":\"Look up the user's profile configuration\",\"name\":\"lookup_user_profile\",\"parameters\":{\"properties\":{\"user_id\":{\"type\":\"string\"}},\"required\":[\"user_id\"],\"type\":\"object\"}},{\"description\":\"Search internal documents\",\"name\":\"search_docs\",\"parameters\":{\"properties\":{\"query\":{\"type\":\"string\"},\"top_k\":{\"type\":\"integer\"}},\"required\":[\"query\"],\"type\":\"object\"}}]\n\n[TENANT]\n{\"language\":\"en\",\"persona\":\"support_assistant\",\"region\":\"eu\",\"tenant_id\":\"tenant-001\",\"user_id\":\"user-123\"}\n\n[CONTEXT]\n- (doc-3) Prompt structure matters: stable instructions should stay fixed, while user-specific data should stay dynamic.\n- (doc-4) Prompt caching works best when the repeated prefix remains identical across calls.\n\n[USER]\nExplain why stable prompt prefixes improve token reuse.\n\n[ASSISTANT]\n",
   "prompt_stats":{
      "prompt_version":"c",
      "total_tokens":237,
      "static_prefix_tokens":173,
      "tokenizer_name":"Qwen/Qwen2.5-7B-Instruct",
      "count_method":"real_tokenizer",
      "has_retrieval_context":true,
      "full_prompt_sha256":"1fb3ab4cc91223010ad7777e9b414d6244d05317d725e94a1751d41aef3a140d",
      "static_prefix_sha256":"2d99bcb8b2aa932e3be985ca31555237a1466b2cd44213130ffc897038565093",
      "full_prompt_chars":1079,
      "static_prefix_chars":777
   },
   "timings":{
      "retrieval_ms":0.04,
      "prompt_assembly_ms":0.21,
      "ttft_ms":2812.69,
      "model_total_ms":5685.14,
      "total_ms":5686.43
   },
   "retrieved_docs":[
      {
         "id":"doc-3",
         "text":"Prompt structure matters: stable instructions should stay fixed, while user-specific data should stay dynamic."
      },
      {
         "id":"doc-4",
         "text":"Prompt caching works best when the repeated prefix remains identical across calls."
      }
   ]
}
## Repeat them once more

Run the same three again.

Then compare in the JSON response:

* `prompt_stats.static_prefix_sha256`
* `prompt_stats.total_tokens`
* `timings.ttft_ms`

Expected:

* A may change more often
* B should be more stable
* C should be most stable

---

# Experiment 2 — same prefix, different user question

Use **Version C only**.

Goal:
confirm

* same static prefix hash
* different full prompt hash

## Request 1

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why stable prompt prefixes improve token reuse.",
    "use_retrieval": true,
    "prompt_version": "c",
    "user_id": "user-123",
    "tenant_id": "tenant-001"
  }'
```

## Request 2

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Why does putting the user question at the end help caching?",
    "use_retrieval": true,
    "prompt_version": "c",
    "user_id": "user-123",
    "tenant_id": "tenant-001"
  }'
```

Compare:

* `prompt_stats.static_prefix_sha256` → should stay the same
* `prompt_stats.full_prompt_sha256` → should change

---

# Experiment 3 — same question, change retrieval order

This needs a small app change first, because curl alone cannot reorder retrieved docs unless your API exposes that control.

Add this to your request model in `app.py`:

```python
shuffle_retrieval_order: bool = False
```

Then after retrieval, add:

```python
import random

if req.shuffle_retrieval_order:
    random.shuffle(retrieved_docs)
```

After that, use these curl calls.

## Version A with shuffled retrieval

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why stable prompt prefixes improve token reuse.",
    "use_retrieval": true,
    "shuffle_retrieval_order": true,
    "prompt_version": "a",
    "user_id": "user-123",
    "tenant_id": "tenant-001"
  }'
```

## Version B with shuffled retrieval

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why stable prompt prefixes improve token reuse.",
    "use_retrieval": true,
    "shuffle_retrieval_order": true,
    "prompt_version": "b",
    "user_id": "user-123",
    "tenant_id": "tenant-001"
  }'
```

## Version C with shuffled retrieval

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why stable prompt prefixes improve token reuse.",
    "use_retrieval": true,
    "shuffle_retrieval_order": true,
    "prompt_version": "c",
    "user_id": "user-123",
    "tenant_id": "tenant-001"
  }'
```

Run each more than once.

Expected:

* C should remain stable if your Version C sorts docs canonically
* B may drift
* A will drift more often

Check:

* `prompt_stats.static_prefix_sha256`
* `prompt_stats.full_prompt_sha256`

---

# Experiment 4 — add noisy whitespace

This also needs a small API flag first.

Add to request model:

```python
inject_whitespace_noise: bool = False
```

Then before prompt building, mutate the incoming message when enabled:

```python
def add_whitespace_noise(text: str) -> str:
    return f"  \n\n{text}\n   \n"

message_for_prompt = req.message
if req.inject_whitespace_noise:
    message_for_prompt = add_whitespace_noise(req.message)
```

Then pass `message_for_prompt` into the prompt builder instead of `req.message`.

Now use these requests.

## Version A with noisy whitespace

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why stable prompt prefixes improve token reuse.",
    "use_retrieval": true,
    "inject_whitespace_noise": true,
    "prompt_version": "a",
    "user_id": "user-123",
    "tenant_id": "tenant-001"
  }'
```

## Version C with noisy whitespace

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why stable prompt prefixes improve token reuse.",
    "use_retrieval": true,
    "inject_whitespace_noise": true,
    "prompt_version": "c",
    "user_id": "user-123",
    "tenant_id": "tenant-001"
  }'
```

Expected:

* A should reflect the noise more directly
* C should normalize it better if your canonicalization is working

Check:

* `prompt_stats.full_prompt_sha256`
* `prompt_stats.total_tokens`
* `prompt_preview`

---

# Helpful jq filters

These make comparison much easier in terminal.

## Show only the key metrics

```bash
curl -s -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why stable prompt prefixes improve token reuse.",
    "use_retrieval": true,
    "prompt_version": "c",
    "user_id": "user-123",
    "tenant_id": "tenant-001"
  }' | jq '{
    prompt_version,
    static_prefix_sha256: .prompt_stats.static_prefix_sha256,
    full_prompt_sha256: .prompt_stats.full_prompt_sha256,
    total_tokens: .prompt_stats.total_tokens,
    static_prefix_tokens: .prompt_stats.static_prefix_tokens,
    ttft_ms: .timings.ttft_ms,
    total_ms: .timings.total_ms
  }'
```

## Show prompt preview too

```bash
curl -s -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Why does putting the user question at the end help caching?",
    "use_retrieval": true,
    "prompt_version": "c",
    "user_id": "user-123",
    "tenant_id": "tenant-001"
  }' | jq '{
    prompt_version,
    prompt_preview,
    static_prefix_sha256: .prompt_stats.static_prefix_sha256,
    full_prompt_sha256: .prompt_stats.full_prompt_sha256
  }'
```

---

# Fast repeat loop from shell

This is useful for checking stability over repeated runs.

## Run Version C five times

```bash
for i in 1 2 3 4 5; do
  echo "Run $i"
  curl -s -X POST "http://127.0.0.1:8001/chat" \
    -H "Content-Type: application/json" \
    -d '{
      "message": "Explain why stable prompt prefixes improve token reuse.",
      "use_retrieval": true,
      "prompt_version": "c",
      "user_id": "user-123",
      "tenant_id": "tenant-001"
    }' | jq '{
      static_prefix_sha256: .prompt_stats.static_prefix_sha256,
      full_prompt_sha256: .prompt_stats.full_prompt_sha256,
      ttft_ms: .timings.ttft_ms,
      total_tokens: .prompt_stats.total_tokens
    }'
done
```

---

# Small note on Experiment 3 and 4

Those two need API support flags because curl can only send inputs; it cannot directly force internal retrieval order changes or whitespace mutation unless your server exposes those controls.

The clean request model becomes:

```python
class ChatRequest(BaseModel):
    message: str
    use_retrieval: bool = True
    prompt_version: str = "c"
    user_id: str = "user-123"
    tenant_id: str = "tenant-001"
    shuffle_retrieval_order: bool = False
    inject_whitespace_noise: bool = False
```

If you want, I’ll give you the exact `app.py` patch for those two flags so all four experiments work immediately.
