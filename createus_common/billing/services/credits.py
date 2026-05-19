# filename: createus_common/billing/services/credits.py

from __future__ import annotations

from typing import Any

from django.db import transaction

from createus_common.billing.choices import CreditTransactionType
from createus_common.billing.exceptions import InsufficientCreditsException


class AbstractCreditService:
    """
    Base service for usage-credit management.

    Project apps subclass this and provide ``get_balance_instance(user)``
    and ``create_history_entry(...)`` backed by their concrete models.
    """

    def get_balance_instance(self, user: Any):
        raise NotImplementedError

    def create_history_entry(
        self,
        user: Any,
        transaction_type: int,
        source_type: int,
        amount: int,
        balance_after: int,
        description: str = "",
        reference_id: str = "",
    ):
        raise NotImplementedError

    @transaction.atomic
    def grant(
        self,
        user: Any,
        amount: int,
        source_type: int,
        description: str = "",
        reference_id: str = "",
    ) -> Any:
        balance_obj = self.get_balance_instance(user)
        balance_obj.balance += amount
        balance_obj.save(update_fields=["balance", "updated_at"])
        self.create_history_entry(
            user=user,
            transaction_type=CreditTransactionType.GRANT,
            source_type=source_type,
            amount=amount,
            balance_after=balance_obj.balance,
            description=description,
            reference_id=reference_id,
        )
        return balance_obj

    @transaction.atomic
    def deduct(
        self,
        user: Any,
        amount: int,
        source_type: int,
        description: str = "",
        reference_id: str = "",
    ) -> Any:
        balance_obj = self.get_balance_instance(user)
        if balance_obj.balance < amount:
            raise InsufficientCreditsException(
                f"Cannot deduct {amount} credits; balance is {balance_obj.balance}."
            )
        balance_obj.balance -= amount
        balance_obj.save(update_fields=["balance", "updated_at"])
        self.create_history_entry(
            user=user,
            transaction_type=CreditTransactionType.DEDUCT,
            source_type=source_type,
            amount=-amount,
            balance_after=balance_obj.balance,
            description=description,
            reference_id=reference_id,
        )
        return balance_obj
