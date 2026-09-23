"""Create the initial standalone Nova prospecting schema.

This revision intentionally contains only Nova-owned tables.  It does not
declare foreign keys to SalesOS tenant or user tables: Gate C maps platform
identifiers to opaque tenant and subject strings during import.
"""
from alembic import op

from app.db.session import Base
from app.prospecting import models  # noqa: F401 -- registers the fixed Gate C schema


revision = "nc20260923a"
down_revision = None
branch_labels = None
depends_on = None

NOVA_TABLES = (
    "prospecting_campaigns",
    "website_prospects",
    "website_analyses",
    "website_proposals",
    "prospecting_policies",
    "prospect_suppressions",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in NOVA_TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(NOVA_TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=False)
