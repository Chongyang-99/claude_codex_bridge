# Managed Provider Completion Reliability

Date: 2026-06-12

## Purpose

Make managed provider completion reliable when CCB mailbox delivery succeeds
but the provider runtime has not accepted the turn. This plan currently focuses
on Codex pane-backed prompt delivery binding drift.

## File Map

- [roadmap.md](roadmap.md): active reliability slices and landed state.
- [implementation-status.md](implementation-status.md): current handoff,
  validation evidence, and review gate.
- [open-questions.md](open-questions.md): unresolved follow-up questions.
- [topics/codex-prompt-delivery-binding-drift.md](topics/codex-prompt-delivery-binding-drift.md):
  implementation entrypoint for Codex prompt-delivery binding drift.

## Related Sources

- [../../../managed-provider-completion-reliability-plan.md](../../../managed-provider-completion-reliability-plan.md)
