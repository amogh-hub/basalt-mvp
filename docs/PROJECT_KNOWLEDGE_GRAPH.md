# Project Knowledge Graph

Basalt Phase 2 replaces the earlier graph preview with a persistent AST-anchored code-truth system.

## Invariant

LLM summaries may explain code. Deterministic parsers define code truth.

## Stored entities

- files, languages, hashes, sizes, and test classification;
- functions, async functions, classes, components, interfaces, types, API routes, database tables, and views;
- imports, calls, inheritance, route handlers, schema references, test mappings, and feature mappings;
- explicit product features from `basalt.features.json` and deterministic inferred features.

## Persistence

The local alpha uses SQLite at `.basalt/knowledge-graph.sqlite3`. Tables include metadata, files, symbols, edges, features, feature-file relationships, test mappings, and a complete graph snapshot.

This follows the technical architecture's lightweight prototype strategy. Production can later move the same contracts to PostgreSQL and a dedicated graph database without changing Phase 2 semantics.

## Freshness

Every discovered source file receives a SHA-256 hash. The sorted file-hash set produces a project state hash. `basalt graph status` compares the stored snapshot to current files and reports changed, new, and removed paths.

The Context Compiler will not silently use stale state. It refreshes automatically when configured, or fails closed when refresh is disabled.

## Feature mapping

Explicit mappings are preferred. Heuristic mappings are labelled `inferred` with lower confidence. Basalt never presents heuristic feature associations as equal to confirmed product truth.
