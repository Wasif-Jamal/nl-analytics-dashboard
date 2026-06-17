# Prepare PR for: $ARGUMENTS

Steps:

1. Run:

    ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run pytest
   (Fix any failures before proceeding)
   ```

2. Run: git diff main --stat
3. Read: openspec/archive/$ARGUMENTS/proposal.md
4. Generate commit (Conventional Commits — see CLAUDE.md §5):
   feat(scope): description
   - bullet 1
   - bullet 2

   Relates to \<ticket>   # optional\
   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
5. Ask: "Run git add . && git commit? [y/n]"
6. Generate PR description:

   ## What

   ## FRS Requirements Covered

   ## Spec Artifacts

   ## Checklist

   ## Test Coverage

7. Ask: "Run git push? [y/n]"

Format: /pr AB-1042-user-registration
