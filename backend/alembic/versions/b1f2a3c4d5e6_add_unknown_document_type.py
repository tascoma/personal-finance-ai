"""add 'unknown' to document_type check constraint

Revision ID: b1f2a3c4d5e6
Revises: a3e1f2c8d501
Create Date: 2026-05-16 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1f2a3c4d5e6"
down_revision: str | Sequence[str] | None = "a3e1f2c8d501"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_TYPES = (
    "'paystub', 'bank_statement', 'credit_card', 'investment', "
    "'mortgage_statement', 'manual', 'opening_balances', 'unknown'"
)
OLD_TYPES = (
    "'paystub', 'bank_statement', 'credit_card', 'investment', "
    "'mortgage_statement', 'manual', 'opening_balances'"
)


def upgrade() -> None:
    op.drop_constraint("ck_document_type", "documents", type_="check")
    op.create_check_constraint(
        "ck_document_type",
        "documents",
        f"document_type IN ({NEW_TYPES})",
    )


def downgrade() -> None:
    op.drop_constraint("ck_document_type", "documents", type_="check")
    op.create_check_constraint(
        "ck_document_type",
        "documents",
        f"document_type IN ({OLD_TYPES})",
    )
