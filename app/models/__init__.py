# Import all models here so that:
# 1. Alembic autogenerate discovers them via Base.metadata
# 2. SQLAlchemy resolves all relationship string references correctly
#
# The import order matters: models with no FK dependencies come first.

from app.models.user import RefreshToken, User
from app.models.group import Group, GroupMember
from app.models.expense import Expense, ExpenseSplit
from app.models.settlement import Settlement

__all__ = [
    "User",
    "RefreshToken",
    "Group",
    "GroupMember",
    "Expense",
    "ExpenseSplit",
    "Settlement",
]
