# Model Provider Integrations

Phase 6 adds a secret-safe provider registry and a minimal OpenAI-compatible chat-completions adapter.

## Built-in profiles

- Basalt Deterministic Runtime
- Basalt Template Codegen

Both work without network access and support local/private routing.

## Optional compatible provider

Configure deliberately through environment variables:

```text
BASALT_OPENAI_BASE_URL
BASALT_OPENAI_MODEL
BASALT_OPENAI_API_KEY
```

The provider is considered configured only when endpoint, model, and credential are present. Inventory snapshots expose the credential variable name and a boolean configuration state, not the value.

## Safety rules

- private/local tasks never fall through to an unconfigured remote provider
- requests use explicit timeout and bounded output settings
- provider errors fail closed
- response structure is validated
- no provider is advertised as available unless its configuration is complete

Phase 6 does not hard-code any commercial provider and does not claim that remote models were used during local deterministic validation.
