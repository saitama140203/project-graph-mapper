---
trigger: always_on
---

# Workspace Rules - Project Graph Mapper

## Project Goal

This project aims to build a semantic project mapping system that transforms source code into a structured knowledge graph and generates reusable project context.

The primary objective is to reduce repeated codebase analysis by producing compact, high-value context artifacts that AI agents can reuse across sessions.

Always optimize for:

* Context quality
* Semantic accuracy
* Maintainability
* Reusability
* Token efficiency

## Architecture Principles

* Prefer modular and extensible architecture.
* Keep parsing, graph generation, storage, and context generation separated.
* Avoid tightly coupled components.
* Favor clear interfaces between modules.

## Python Standards

* Use Python 3.12+
* Use type hints.
* Prefer pathlib over os.path.
* Use dataclasses or Pydantic models where appropriate.
* Avoid global mutable state.
* Use logging instead of print().

## Code Quality

* Prioritize readability and maintainability.
* Prefer simple implementations over complex abstractions.
* Keep functions focused on a single responsibility.
* Avoid premature optimization.

## Graph Modeling

* Preserve semantic relationships whenever possible.

* Prefer explicit graph relationships over inferred assumptions.

* Clearly distinguish:

  * File relationships
  * Module relationships
  * Class relationships
  * Function relationships
  * Dependency relationships

* Document relationship types consistently.

## Parsing & Analysis

* Prefer deterministic analysis over heuristic assumptions.
* Preserve source-of-truth information.
* Clearly mark inferred information.
* Avoid generating relationships without evidence.

## Context Generation

* Prioritize information density.
* Remove redundant information.
* Generate context that is useful for AI agents.
* Optimize generated artifacts for token efficiency.
* Preserve important architectural relationships.

## Documentation Strategy

* Maintain a single primary project documentation whenever possible.
* Update existing documentation instead of creating new files.
* Do not create:

  * fix-*.md
  * feature-*.md
  * update-*.md
  * task-*.md

unless explicitly requested.

* Prefer updating:

  * README.md
  * ARCHITECTURE.md
  * CONTEXT.md

* Ask for approval before creating additional documentation files.

## Testing

* Add tests for parsing logic.
* Add tests for graph generation logic.
* Validate generated context outputs.
* Consider edge cases in large codebases.

## AI-Agent Optimization

* Always consider token efficiency.
* Prefer reusable context artifacts.
* Minimize redundant processing.
* Design outputs for long-term AI consumption.

## Decision Making

When multiple implementations exist:

1. Compare alternatives.
2. Explain trade-offs.
3. Recommend the most maintainable solution.
4. Prioritize semantic correctness over implementation convenience.