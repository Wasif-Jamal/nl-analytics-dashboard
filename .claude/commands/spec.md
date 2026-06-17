# Run OpenSpec proposal creation for: $ARGUMENTS

Steps:

1. Run: openspec change list
2. Read: openspec/specs/ (current system state)
3. Read: docs/FRS.md → find relevant requirements for this ticket
4. Read: docs/SDS.md → find relevant design decisions for this ticket
5. Read: AGENTS.md (constraints)
6. Ask clarifying questions — minimum 3, maximum 8
7. Run: openspec new change $ARGUMENTS
8. Show generated proposal.md and spec delta
9. Do NOT proceed to implementation

Format: /spec AB-1042-user-registration
