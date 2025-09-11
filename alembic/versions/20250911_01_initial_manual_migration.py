"""Initial manual migration capturing current schema.

Revision ID: 20250911_01_initial_manual_migration
Revises: 
Create Date: 2025-09-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250911_01_initial_manual_migration'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Users
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('email', sa.String(length=191), nullable=False, unique=True, index=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('1'), nullable=False),
    )
    # Refresh tokens
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False, index=True),
        sa.Column('token', sa.String(length=191), nullable=False, unique=True, index=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
    )
    # Password reset tokens
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False, index=True),
        sa.Column('token', sa.String(length=191), nullable=False, unique=True, index=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    # Games
    op.create_table(
        'games',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('date', sa.Date(), index=True),
        sa.Column('game_pk', sa.Integer(), unique=True, index=True),
        sa.Column('home_team', sa.String(length=64)),
        sa.Column('away_team', sa.String(length=64)),
        sa.Column('home_runs', sa.Integer(), server_default='0'),
        sa.Column('away_runs', sa.Integer(), server_default='0'),
        sa.Column('home_hits', sa.Integer(), server_default='0'),
        sa.Column('away_hits', sa.Integer(), server_default='0'),
        sa.Column('home_errors', sa.Integer(), server_default='0'),
        sa.Column('away_errors', sa.Integer(), server_default='0'),
        sa.Column('home_homers', sa.Integer(), server_default='0'),
        sa.Column('away_homers', sa.Integer(), server_default='0'),
    )
    # Batter stats
    op.create_table(
        'batter_stats',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('game_id', sa.Integer(), nullable=True),
        sa.Column('date', sa.Date(), index=True),
        sa.Column('team', sa.String(length=64), index=True),
        sa.Column('name', sa.String(length=191)),
        sa.Column('position', sa.String(length=16)),
        sa.Column('ab', sa.Integer()),
        sa.Column('r', sa.Integer()),
        sa.Column('h', sa.Integer()),
        sa.Column('hr', sa.Integer(), server_default='0'),
        sa.Column('errors', sa.Integer(), server_default='0'),
        sa.Column('rbi', sa.Integer()),
        sa.Column('bb', sa.Integer()),
        sa.Column('so', sa.Integer()),
        sa.Column('lob', sa.Integer()),
    )
    # Pitcher stats
    op.create_table(
        'pitcher_stats',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('game_id', sa.Integer(), nullable=True),
        sa.Column('date', sa.Date(), index=True),
        sa.Column('team', sa.String(length=64), index=True),
        sa.Column('name', sa.String(length=191)),
        sa.Column('ip', sa.String(length=16)),
        sa.Column('so', sa.Integer(), server_default='0'),
        sa.Column('bb', sa.Integer(), server_default='0'),
        sa.Column('h', sa.Integer(), server_default='0'),
        sa.Column('hr', sa.Integer(), server_default='0'),
        sa.Column('r', sa.Integer(), server_default='0'),
        sa.Column('er', sa.Integer(), server_default='0'),
        sa.Column('wp', sa.Integer(), server_default='0'),
        sa.Column('bk', sa.Integer(), server_default='0'),
        sa.Column('baa_num', sa.Integer(), server_default='0'),
        sa.Column('baa_den', sa.Integer(), server_default='0'),
    )
    # Caches
    for tbl in ('boxscore_cache','linescore_cache','status_cache'):
        op.create_table(
            tbl,
            sa.Column('game_pk', sa.Integer(), primary_key=True),
            sa.Column('json', sa.Text(), nullable=False),
            sa.Column('hash', sa.String(length=64), nullable=True),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        )


def downgrade():
    for tbl in ('status_cache','linescore_cache','boxscore_cache'):
        op.drop_table(tbl)
    op.drop_table('pitcher_stats')
    op.drop_table('batter_stats')
    op.drop_table('games')
    op.drop_table('password_reset_tokens')
    op.drop_table('refresh_tokens')
    op.drop_table('users')
