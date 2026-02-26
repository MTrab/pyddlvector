# AGENTS.md — pyddlvector Python Module

This document defines instructions for AI coding agents working in this repository.

Agents must follow this file strictly.

---

## Scope

`pyddlvector` is the Python communication module used by the Home Assistant Vector integration.

The module must provide a clean, reusable client layer for robot communication and avoid Home Assistant-specific implementation details in core protocol logic.

---

## Reference SDK Policy

Use the following project as a technical reference:

- https://github.com/kercre123/wirepod-vector-python-sdk

Reference means:

- Understand protocol behavior and message flow
- Validate assumptions about robot communication
- Compare implementation strategies when needed

Reference does NOT mean:

- Blindly copying architecture or legacy patterns
- Inheriting technical debt without review
- Sacrificing quality, typing, async correctness, or maintainability

---

## Python and Compatibility Requirements

- Minimum supported Python version: `3.13`
- Target runtime: Python `3.13+`
- The module must remain compatible with Home Assistant usage patterns.
- Public APIs should be stable, typed, and suitable for long-term integration use.

---

## Async-First Requirement

All network and robot communication APIs must be async-first.

The agent must:

- Prefer `async def` APIs for all I/O operations
- Avoid blocking calls in async contexts
- Avoid using synchronous waits (for example `.result()` in event loop paths)
- Define clear timeout and cancellation behavior
- Ensure reconnect and retry logic is bounded and explicit

If a sync wrapper is needed, it must be optional and isolated from the primary async API.

---

## Home Assistant Alignment

The module must support Home Assistant integration needs:

- Predictable error types and actionable exception messages
- Deterministic connection lifecycle behavior
- Safe handling of credentials/certificates/tokens
- No secret leakage in logs
- Reliable behavior under intermittent connectivity

The module should be designed so Home Assistant can consume it without patching internals.

---

## Repository Workflow

All changes must be made in dedicated branches intended for merge.

- Never commit directly to `main`/`master`
- Keep commits small and focused
- Include tests for behavior changes where feasible
- Update docs when public API or configuration changes

---

## Security and Secrets

The agent must NOT:

- Commit credentials, certificates, or tokens
- Log secrets in plaintext
- Bypass TLS/certificate validation for convenience
- Introduce undocumented external endpoints

Any required endpoints and auth assumptions must be documented.

---

## When Information Is Missing

If protocol/API details are unclear, the agent must:

1. Check repository documentation and source code
2. Check the reference SDK behavior
3. Ask for clarification before implementing uncertain behavior

No fabrication of protocol fields, endpoints, or auth flows is allowed.
