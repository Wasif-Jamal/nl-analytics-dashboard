# Review implementation for: $ARGUMENTS

Read-only mode — do NOT modify any files.

Steps:

1. Read: openspec/changes/archive/$ARGUMENTS/
2. Read: docs/FRS.md (original requirements)
3. Compare implementation against spec scenarios AND FRS criteria
4. Output:

    ```bash
    ✅ Implemented: [scenario]
    ❌ Missing: [scenario]
    ⚠️ Drifted: [scenario — spec says X, code does Y]
    🔒 Security: [concern]
    📋 FRS gap: [requirement not addressed]
    ```

5. No style feedback — compliance only

Format: /review AB-1042-user-registration
