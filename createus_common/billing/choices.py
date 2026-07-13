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
    GRACE_PERIOD = 7, "Grace Period"
    REVOKED = 8, "Revoked"


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
    APP_STORE = 4, "Apple App Store"
    GOOGLE_PLAY = 5, "Google Play"


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


# ── App Store / Google Play in-app-purchase choices ─────────────────────────
#
# These mirror the vocabularies used by Apple's App Store Server API /
# Notifications V2 and are written to be equally sensible for a future
# Google Play Real-time Developer Notifications integration.  Values that
# are provider-defined small closed enums (offer type, revocation reason,
# expiration intent, auto-renew status) are modeled as IntegerChoices for
# admin/readability; values that are open-ended, provider-controlled strings
# (transaction type, ownership type, transaction reason) are left as plain
# CharFields on the models rather than enums here, so a new value Apple adds
# tomorrow does not require a migration to store it.


class StoreEnvironment(models.TextChoices):
    SANDBOX = "sandbox", "Sandbox"
    PRODUCTION = "production", "Production"


class SubscriptionOfferType(models.IntegerChoices):
    INTRODUCTORY = 1, "Introductory Offer"
    PROMOTIONAL = 2, "Promotional Offer"
    OFFER_CODE = 3, "Offer Code"
    WIN_BACK = 4, "Win-Back Offer"


class ExpirationIntent(models.IntegerChoices):
    CUSTOMER_CANCELLED = 1, "Customer Cancelled"
    BILLING_ERROR = 2, "Billing Error"
    PRICE_INCREASE_NOT_CONSENTED = 3, "Price Increase Not Consented To"
    PRODUCT_NOT_AVAILABLE = 4, "Product Not Available"
    OTHER = 5, "Other"


class RevocationReason(models.IntegerChoices):
    REFUNDED_FOR_OTHER_REASON = 0, "Refunded for Other Reason"
    REFUNDED_DUE_TO_ISSUE = 1, "Refunded Due to Issue"


class NotificationProcessingStatus(models.IntegerChoices):
    PENDING = 1, "Pending"
    PROCESSED = 2, "Processed"
    FAILED = 3, "Failed"
    IGNORED = 4, "Ignored"
