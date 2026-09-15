"""router provisioning (Add Router Wizard)

Revision ID: 5b30bbd257fc
Revises: eafef8056e3d
Create Date: 2026-09-14 10:00:00.000000

Adds the columns the Add Router Wizard writes as it walks a router through
network config -> WireGuard -> RADIUS -> hotspot setup. RADIUS secret and
WireGuard private key are stored encrypted at rest (app.core.crypto) —
this migration only adds the columns, it never writes a value into them.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b30bbd257fc"
down_revision: str | None = "eafef8056e3d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "routers",
        sa.Column(
            "provisioning_status", sa.Text(), nullable=False, server_default="in_progress"
        ),
    )
    op.add_column("routers", sa.Column("hotspot_network_cidr", sa.Text(), nullable=True))
    op.add_column("routers", sa.Column("hotspot_gateway_ip", sa.Text(), nullable=True))
    op.add_column("routers", sa.Column("hotspot_dns_servers", sa.Text(), nullable=True))
    op.add_column("routers", sa.Column("wireguard_public_key", sa.Text(), nullable=True))
    op.add_column("routers", sa.Column("wireguard_tunnel_ip", sa.Text(), nullable=True))
    op.create_unique_constraint(
        "uq_routers_wireguard_tunnel_ip", "routers", ["wireguard_tunnel_ip"]
    )
    op.add_column(
        "routers", sa.Column("wireguard_private_key_encrypted", sa.Text(), nullable=True)
    )
    op.add_column("routers", sa.Column("radius_secret_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("routers", "radius_secret_encrypted")
    op.drop_column("routers", "wireguard_private_key_encrypted")
    op.drop_constraint("uq_routers_wireguard_tunnel_ip", "routers", type_="unique")
    op.drop_column("routers", "wireguard_tunnel_ip")
    op.drop_column("routers", "wireguard_public_key")
    op.drop_column("routers", "hotspot_dns_servers")
    op.drop_column("routers", "hotspot_gateway_ip")
    op.drop_column("routers", "hotspot_network_cidr")
    op.drop_column("routers", "provisioning_status")
