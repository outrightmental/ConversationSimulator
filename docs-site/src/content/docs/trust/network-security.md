---
title: "Network security"
description: "How Conversation Simulator binds all services to 127.0.0.1, rejects wildcard binding, and blocks outbound network calls during play mode."
sidebar:
  order: 3
---

ConversationSimulator is designed as a fully local application.  All services
bind to `127.0.0.1` by default so that no ports are reachable from other
machines on the network.

## Service binding

| Service | Default address | Override env var |
|---------|-----------------|------------------|
| `convsim-ui` (Vite dev server) | `127.0.0.1:7354` | hardcoded (dev only) |
| `convsim-core` (Python/FastAPI) | `127.0.0.1:7355` | `CONVSIM_HOST` / `CONVSIM_PORT` |
| `convsim-api` (TypeScript/Fastify) ¹ | `127.0.0.1:7355` | `API_HOST` / `API_PORT` |
| `convsim-llm` (llama-server sidecar) | `127.0.0.1:7356` | future |
| `convsim-stt` (Whisper sidecar) | `127.0.0.1:7357` | future |
| `convsim-tts` (Kokoro sidecar) | `127.0.0.1:7358` | future |

¹ `convsim-api` (TypeScript) and `convsim-core` (Python) are alternative backends that
both default to port 7355.  They are not run simultaneously — `convsim-api` is an interim
implementation; `convsim-core` is the target architecture (see the
[architecture documentation](/reference/architecture/)).

All dev-server proxy targets point to `127.0.0.1` — see
[`apps/web/vite.config.ts`](https://github.com/outrightmental/ConversationSimulator/blob/main/apps/web/vite.config.ts).

## Wildcard binding is rejected by default

Attempting to bind to `0.0.0.0` (all IPv4 interfaces) is rejected at startup
with a clear error message.

**Python (`convsim-core`):**

```
ValueError: Binding to 0.0.0.0 is not allowed in default mode.
Set CONVSIM_LAN_ACCESS_ENABLED=true to enable LAN access
and specify an explicit LAN IP address.
```

The same error is raised for the IPv6 wildcard `::`.  The host name appears
verbatim in the message, e.g. `Binding to :: is not allowed in default mode.`

**TypeScript (`convsim-api`):**

```
Error: Binding to 0.0.0.0 is not allowed in default mode.
Set API_LAN_ACCESS_ENABLED=true to enable LAN access
and specify an explicit LAN IP address.
```

The same error is raised for the IPv6 wildcard `::`.  The host name appears
verbatim in the message, e.g. `Binding to :: is not allowed in default mode.`

## Outbound network policy (play mode)

During a live conversation session (play mode), the application must not make
automatic outbound calls to the internet.  All inference, transcription, and
synthesis run on local models.

The `convsim_core.network_policy` module enforces this:

```python
import convsim_core.network_policy as policy
from convsim_core.network_policy import NetworkMode

# Before any LLM/STT/TTS call in play mode:
policy.require_network(NetworkMode.PLAY)
```

When `policy.LOCAL_MODE = True` (set explicitly in each test that needs it),
`require_network(NetworkMode.PLAY)` raises `NetworkBlockedError`, catching
any accidental outbound calls early.

**User-initiated downloads** (model files, pack bundles) use a separate mode
that is always permitted:

```python
policy.require_network(NetworkMode.EXPLICIT_DOWNLOAD)
```

Download operations are logged separately from play-mode activity.

## LAN access (future / advanced)

LAN access is **not part of MVP** and is off by default.  It may be added in
a future release to support multi-device setups (e.g., a shared LAN server for
a classroom).

To enable it explicitly when the feature is available:

```bash
# Python service
CONVSIM_HOST=0.0.0.0 CONVSIM_LAN_ACCESS_ENABLED=true convsim-core

# TypeScript API
API_HOST=0.0.0.0 API_LAN_ACCESS_ENABLED=true node dist/index.js
```

> **Warning:** enabling LAN access exposes the service to all devices on your
> local network.  Use a firewall rule or router ACL to restrict access if you
> run this in a shared environment.

## Testing the guard

Set `LOCAL_MODE = True` in any Python test to verify that play-mode calls are
blocked:

```python
import convsim_core.network_policy as policy

policy.LOCAL_MODE = True
policy.require_network(NetworkMode.PLAY)  # raises NetworkBlockedError
```

The test suite in
[`services/convsim-core/tests/test_network_policy.py`](https://github.com/outrightmental/ConversationSimulator/blob/main/services/convsim-core/tests/test_network_policy.py)
covers this smoke test automatically on every CI run.
