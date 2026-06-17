# Break down into tasks for: $ARGUMENTS

Steps:

1. Read: openspec/changes/$ARGUMENTS/proposal.md
2. Read: openspec/changes/$ARGUMENTS/plan.md
3. Generate sequenced task checklist:
   - Phase 1: Foundation (shared Pydantic schemas, SQLAlchemy models / DB init)
   - Phase 2: Core implementation [mark PARALLEL tasks]
   - Phase 3: Integration
   - Phase 4: Tests (one pytest test per spec scenario)
   - Checkpoint after each phase (no build step — Streamlit):

     ```bash
     uv run ruff check .          # lint
     uv run ruff format --check . # formatting
     uv run pytest                # all green
     ```

4. Save to: openspec/changes/$ARGUMENTS/tasks.md
5. Wait for approval

Format: /tasks AB-1042-user-registration
