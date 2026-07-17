# Context Compiler

The Context Compiler turns the Project Knowledge Graph into a bounded task-specific context pack.

## Inputs

- task text;
- agent role;
- optional target files, symbols, routes, or features;
- token budget;
- current project-state hash.

## Selection

Basalt scores exact targets, task-keyword matches, agent-role relevance, mapped tests, mapped features, and graph-distance relationships. It then selects source snippets until the token budget is reached.

## Output contract

Each context pack contains:

- context ID and project-state hash;
- task classification and agent role;
- selected files with scores, hashes, snippets, and reasons;
- selected symbols and signatures;
- tests, features, routes, schemas, and dependencies;
- operational constraints;
- graph freshness evidence;
- estimated token use and context precision.

## Safety rule

The Context Compiler never treats a stale graph as current. It also does not define code truth through embeddings or summaries. Semantic retrieval may be added later, but deterministic graph state remains authoritative.
