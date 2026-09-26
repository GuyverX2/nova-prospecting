"""Create the initial standalone Nova prospecting schema.

This revision intentionally contains only Nova-owned tables.  It does not
declare foreign keys to SalesOS tenant or user tables: Gate C maps platform
identifiers to opaque tenant and subject strings during import.

The DDL is written out explicitly rather than derived from ``Base.metadata``.
A historical migration must describe the schema as it was released; deriving it
from live models would silently rewrite deployed history whenever a model
changes.
"""
import sqlalchemy as sa
from alembic import op

revision = "nc20260923a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prospecting_campaigns",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("industry", sa.String(length=160), nullable=True),
        sa.Column("region", sa.String(length=160), nullable=True),
        sa.Column("employee_band", sa.String(length=64), nullable=True),
        sa.Column("min_score", sa.Integer(), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=False),
        sa.Column("criteria_json", sa.Text(), nullable=False),
        sa.Column("source_provider", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prospecting_campaigns_tenant_id", "prospecting_campaigns", ["tenant_id"])
    op.create_index(
        "ix_prospecting_campaign_tenant_created", "prospecting_campaigns", ["tenant_id", "created_at"]
    )
    op.create_index("ix_prospecting_campaign_status", "prospecting_campaigns", ["tenant_id", "status"])

    op.create_table(
        "website_prospects",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("campaign_id", sa.String(length=32), nullable=True),
        sa.Column("assigned_subject", sa.String(length=255), nullable=True),
        sa.Column("company_name", sa.String(length=240), nullable=False),
        sa.Column("organization_number", sa.String(length=64), nullable=True),
        sa.Column("website_url", sa.String(length=2048), nullable=False),
        sa.Column("normalized_domain", sa.String(length=255), nullable=False),
        sa.Column("industry", sa.String(length=160), nullable=True),
        sa.Column("city", sa.String(length=120), nullable=True),
        sa.Column("employee_band", sa.String(length=64), nullable=True),
        sa.Column("turnover_label", sa.String(length=64), nullable=True),
        sa.Column("qualification_score", sa.Integer(), nullable=False),
        sa.Column("estimated_value_sek", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("contact_name", sa.String(length=180), nullable=True),
        sa.Column("contact_role", sa.String(length=120), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("contact_verified", sa.Boolean(), nullable=False),
        sa.Column("contact_verified_at", sa.DateTime(), nullable=True),
        sa.Column("contact_verification_source", sa.String(length=512), nullable=True),
        sa.Column("legal_basis", sa.String(length=64), nullable=False),
        sa.Column("legitimate_interest_note", sa.Text(), nullable=True),
        sa.Column("do_not_contact", sa.Boolean(), nullable=False),
        sa.Column("retention_until", sa.DateTime(), nullable=True),
        sa.Column("source_provider", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("source_checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["prospecting_campaigns.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "normalized_domain", name="uq_website_prospect_tenant_domain"),
    )
    op.create_index("ix_website_prospects_tenant_id", "website_prospects", ["tenant_id"])
    op.create_index("ix_website_prospects_campaign_id", "website_prospects", ["campaign_id"])
    op.create_index("ix_website_prospect_tenant_status", "website_prospects", ["tenant_id", "status"])
    op.create_index(
        "ix_website_prospect_tenant_score", "website_prospects", ["tenant_id", "qualification_score"]
    )

    op.create_table(
        "website_analyses",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("prospect_id", sa.String(length=32), nullable=False),
        sa.Column("requested_by_subject", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("analyzer_version", sa.String(length=32), nullable=False),
        sa.Column("analyzed_url", sa.String(length=2048), nullable=False),
        sa.Column("final_url", sa.String(length=2048), nullable=True),
        sa.Column("improvement_score", sa.Integer(), nullable=False),
        sa.Column("performance_score", sa.Integer(), nullable=False),
        sa.Column("seo_score", sa.Integer(), nullable=False),
        sa.Column("accessibility_score", sa.Integer(), nullable=False),
        sa.Column("mobile_score", sa.Integer(), nullable=False),
        sa.Column("findings_json", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.Text(), nullable=False),
        sa.Column("technical_json", sa.Text(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=True),
        sa.Column("fetch_duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["prospect_id"], ["website_prospects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_website_analyses_tenant_id", "website_analyses", ["tenant_id"])
    op.create_index("ix_website_analyses_prospect_id", "website_analyses", ["prospect_id"])
    op.create_index(
        "ix_website_analysis_prospect_created", "website_analyses", ["prospect_id", "created_at"]
    )
    op.create_index("ix_website_analysis_tenant_status", "website_analyses", ["tenant_id", "status"])

    op.create_table(
        "website_proposals",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("prospect_id", sa.String(length=32), nullable=False),
        sa.Column("analysis_id", sa.String(length=32), nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("headline", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sitemap_json", sa.Text(), nullable=False),
        sa.Column("benefits_json", sa.Text(), nullable=False),
        sa.Column("packages_json", sa.Text(), nullable=False),
        sa.Column("timeline_json", sa.Text(), nullable=False),
        sa.Column("email_subject", sa.String(length=300), nullable=False),
        sa.Column("email_body", sa.Text(), nullable=False),
        sa.Column("review_json", sa.Text(), nullable=False),
        sa.Column("approved_by_subject", sa.String(length=255), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("share_token_hash", sa.String(length=64), nullable=True),
        sa.Column("share_expires_at", sa.DateTime(), nullable=True),
        sa.Column("delivery_status", sa.String(length=32), nullable=False),
        sa.Column("delivery_provider", sa.String(length=64), nullable=True),
        sa.Column("delivery_id", sa.String(length=255), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["website_analyses.id"]),
        sa.ForeignKeyConstraint(["prospect_id"], ["website_prospects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prospect_id", "version", name="uq_website_proposal_prospect_version"),
    )
    op.create_index("ix_website_proposals_tenant_id", "website_proposals", ["tenant_id"])
    op.create_index("ix_website_proposals_prospect_id", "website_proposals", ["prospect_id"])
    op.create_index("ix_website_proposal_tenant_status", "website_proposals", ["tenant_id", "status"])
    op.create_index("ix_website_proposal_share_hash", "website_proposals", ["share_token_hash"])

    op.create_table(
        "prospecting_policies",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("auto_analyze", sa.Boolean(), nullable=False),
        sa.Column("auto_generate_proposal", sa.Boolean(), nullable=False),
        sa.Column("auto_queue_after_approval", sa.Boolean(), nullable=False),
        sa.Column("minimum_score", sa.Integer(), nullable=False),
        sa.Column("daily_delivery_limit", sa.Integer(), nullable=False),
        sa.Column("updated_by_subject", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_prospecting_policy_tenant"),
    )
    op.create_index("ix_prospecting_policies_tenant_id", "prospecting_policies", ["tenant_id"])

    op.create_table(
        "prospect_suppressions",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("tenant_id", sa.String(length=255), nullable=False),
        sa.Column("prospect_id", sa.String(length=32), nullable=True),
        sa.Column("normalized_email", sa.String(length=320), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_by_subject", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["prospect_id"], ["website_prospects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "normalized_email", name="uq_prospect_suppression_tenant_email"),
    )
    op.create_index("ix_prospect_suppressions_tenant_id", "prospect_suppressions", ["tenant_id"])
    op.create_index(
        "ix_prospect_suppression_tenant_created", "prospect_suppressions", ["tenant_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("prospect_suppressions")
    op.drop_table("prospecting_policies")
    op.drop_table("website_proposals")
    op.drop_table("website_analyses")
    op.drop_table("website_prospects")
    op.drop_table("prospecting_campaigns")
