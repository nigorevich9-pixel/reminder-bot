"""denormalize events fields

Revision ID: f5c3cd383f5b
Revises: 2eb47063a061
Create Date: 2026-02-01 21:52:56.938334

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5c3cd383f5b'
down_revision: Union[str, Sequence[str], None] = '2eb47063a061'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("events", sa.Column("event_type", sa.String(length=64), nullable=True))
    op.add_column("events", sa.Column("tg_id", sa.BigInteger(), nullable=True))
    op.add_column("events", sa.Column("chat_id", sa.BigInteger(), nullable=True))
    op.add_column("events", sa.Column("request_kind", sa.String(length=32), nullable=True))

    op.execute(
        """
        UPDATE events
        SET
          event_type = payload->>'event_type',
          tg_id = (payload #>> '{tg,tg_id}')::bigint,
          chat_id = (payload #>> '{tg,chat_id}')::bigint,
          request_kind = payload #>> '{request,kind}'
        WHERE
          event_type IS NULL
          OR tg_id IS NULL
          OR chat_id IS NULL
          OR request_kind IS NULL
        """
    )

    op.create_index("ix_events_event_type_created_at", "events", ["event_type", "created_at"])
    op.create_index("ix_events_tg_id_created_at", "events", ["tg_id", "created_at"])
    op.create_index("ix_events_chat_id_created_at", "events", ["chat_id", "created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_events_chat_id_created_at", table_name="events")
    op.drop_index("ix_events_tg_id_created_at", table_name="events")
    op.drop_index("ix_events_event_type_created_at", table_name="events")

    op.drop_column("events", "request_kind")
    op.drop_column("events", "chat_id")
    op.drop_column("events", "tg_id")
    op.drop_column("events", "event_type")
