# Product Brain

The Product Brain converts a user prompt into structured product truth before implementation begins.

## Input

- product intent
- product name
- template
- target users
- constraints

## Output

The generated Product Blueprint contains features, requirement IDs, user flows, non-functional requirements, risks, explicit assumptions, success criteria, constraints, and architecture hints.

Blueprint IDs and content hashes are deterministic for equivalent intent. Creation timestamps are deliberately excluded from the content hash.

## Alpha behavior

Phase 5 uses deterministic intent classification and known feature families. It does not claim open-ended product understanding. Unsupported ambiguity is preserved as an assumption instead of silently becoming code truth.
