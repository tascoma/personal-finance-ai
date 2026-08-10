"""add_token_version_to_users

Revision ID: a3e1f2c8d501
Revises: 7fceefecdbfb
Create Date: 2026-05-06 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3e1f2c8d501"
down_revision: str | Sequence[str] | None = "7fceefecdbfb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
