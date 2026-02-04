"""events idempotency indexes

Revision ID: 20260204_0001
Revises: f5c3cd383f5b
Create Date: 2026-02-04

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260204_0001"
down_revision: str | Sequence[str] | None = "f5c3cd383f5b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `events` is shared inbox table. Ensure idempotency-friendly indexes exist.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_source_external_id ON events (source, external_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_events_payload_hash ON events (payload_hash)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_events_payload_hash")
    op.execute("DROP INDEX IF EXISTS idx_events_source_external_id")

