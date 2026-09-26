"""Add the Nova audit table and an explicit delivery timestamp.

``audit_events`` is written by every prospecting mutation but was never part of
the migration chain, so a database created by Alembic alone was missing it and
every write failed. ``website_proposals.delivery_processed_at`` records when a
delivery was accepted, so the tenant daily limit is no longer derived from
``updated_at`` (which any unrelated edit moves).

The upgrade is additive and backfills the new column from existing delivery
state, so no row is lost and re-running it on a populated database is safe.
"""
import sqlalchemy as sa
from alembic import op

revision = "nc20260925a"
down_revision = "nc20260923a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("actor_subject", sa.String(length=255), nullable=False),
        sa.Column("action_type", sa.String(length=160), nullable=False),
        sa.Column("target_type", sa.String(length=120), nullable=False),
        sa.Column("target_id", sa.String(length=120), nullable=False),
        sa.Column("request_id", sa.String(length=200), nullable=True),
        sa.Column("after_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_index("ix_audit_event_tenant_created", "audit_events", ["tenant_id", "created_at"])

    op.add_column("website_proposals", sa.Column("delivery_processed_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_website_proposal_tenant_delivery", "website_proposals", ["tenant_id", "delivery_processed_at"]
    )
    # Existing delivered/queued proposals keep a truthful delivery timestamp.
    op.execute(
        sa.text(
            "UPDATE website_proposals "
            "SET delivery_processed_at = COALESCE(delivered_at, updated_at) "
            "WHERE delivery_status IN ('queued', 'mock_delivered', 'delivered')"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_website_proposal_tenant_delivery", table_name="website_proposals")
    op.drop_column("website_proposals", "delivery_processed_at")
    op.drop_index("ix_audit_event_tenant_created", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_id", table_name="audit_events")
    op.drop_table("audit_events")
