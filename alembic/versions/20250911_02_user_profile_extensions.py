"""
Add favorite_teams and user_steps tables

Revision ID: 20250911_02_user_profile_extensions
Revises: 20250911_01_initial_manual_migration
Create Date: 2025-09-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250911_02_user_profile_extensions'
down_revision = '20250911_01_initial_manual_migration'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'favorite_teams',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False, index=True),
        sa.Column('team', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_unique_constraint('uq_user_team', 'favorite_teams', ['user_id', 'team'])

    op.create_table(
        'user_steps',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), nullable=False, index=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('steps', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), onupdate=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
    )
    op.create_unique_constraint('uq_user_date', 'user_steps', ['user_id', 'date'])


def downgrade():
    op.drop_constraint('uq_user_date', 'user_steps', type_='unique')
    op.drop_table('user_steps')
    op.drop_constraint('uq_user_team', 'favorite_teams', type_='unique')
    op.drop_table('favorite_teams')
