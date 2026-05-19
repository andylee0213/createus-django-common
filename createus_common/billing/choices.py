# filename: createus_common/billing/choices.py

from django.db import models


class BillingCurrency(models.IntegerChoices):
    KRW = 1, "Korean Won"
    USD = 2, "US Dollar"
    EUR = 3, "Euro"
    JPY = 4, "Japanese Yen"
    GBP = 5, "British Pound"


class SubscriptionStatus(models.IntegerChoices):
    TRIALING = 1, "Trialing"
    ACTIVE = 2, "Active"
    PAST_DUE = 3, "Past Due"
    PAUSED = 4, "Paused"
    CANCELLED = 5, "Cancelled"
    EXPIRED = 6, "Expired"


class PaymentStatus(models.IntegerChoices):
    PENDING = 1, "Pending"
    DONE = 2, "Done"
    CANCELLED = 3, "Cancelled"
    PARTIAL_CANCELLED = 4, "Partial Cancelled"
    FAILED = 5, "Failed"
    ABORTED = 6, "Aborted"
    EXPIRED = 7, "Expired"


class PaymentProvider(models.IntegerChoices):
    TOSS_PAYMENTS = 1, "Toss Payments"
    STRIPE = 2, "Stripe"
    PAYPAL = 3, "PayPal"


class PaymentMethodType(models.IntegerChoices):
    CARD = 1, "Card"
    VIRTUAL_ACCOUNT = 2, "Virtual Account"
    BANK_TRANSFER = 3, "Bank Transfer"
    MOBILE_PHONE = 4, "Mobile Phone"
    GIFT_CERTIFICATE = 5, "Gift Certificate"
    FOREIGN_EASY_PAY = 6, "Foreign Easy Pay"


class SubscriptionInterval(models.IntegerChoices):
    MONTHLY = 1, "Monthly"
    QUARTERLY = 3, "Quarterly"
    YEARLY = 12, "Yearly"


class CreditTransactionType(models.IntegerChoices):
    GRANT = 1, "Grant"
    DEDUCT = 2, "Deduct"
    REFUND = 3, "Refund"
    EXPIRE = 4, "Expire"


class CreditSourceType(models.IntegerChoices):
    SUBSCRIPTION = 1, "Subscription"
    REFERRAL = 2, "Referral"
    PROMOTION = 3, "Promotion"
    PURCHASE = 4, "Purchase"
    MANUAL = 5, "Manual Adjustment"


class ReferralRewardStatus(models.IntegerChoices):
    PENDING = 1, "Pending"
    CONFIRMED = 2, "Confirmed"
    PAID = 3, "Paid"
    EXPIRED = 4, "Expired"
    REJECTED = 5, "Rejected"
