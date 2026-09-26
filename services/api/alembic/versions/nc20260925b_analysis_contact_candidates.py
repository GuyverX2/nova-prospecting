"""Store provenance-carrying contact candidates alongside each analysis.

Revision ID: nc20260925b
Revises: nc20260925a
Create Date: 2026-09-25

The analyser already parsed the page; the contact facts it can see (mailto
links, phone numbers, organisation numbers, social profiles) were thrown away
and the operator had to retype them from memory. They are stored per analysis
so the console can offer them as suggestions with their source.

The column is additive and defaults to an empty list, so existing rows stay
valid and an older application version keeps working against the new schema.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "nc20260925b"
down_revision = "nc20260925a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "website_analyses",
        sa.Column("contact_candidates_json", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("website_analyses", "contact_candidates_json")
