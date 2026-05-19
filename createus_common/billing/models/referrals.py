# filename: createus_common/billing/models/referrals.py

from django.db import models

from createus_common.models import TimeStampedModel
from createus_common.billing.choices import ReferralRewardStatus


class AbstractReferralReward(TimeStampedModel):
    """
    Tracks a reward owed to a referrer when their referee converts.

    Project apps must add:
        referrer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="referral_rewards", ...)
        referee  = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="referred_rewards", ...)
    """

    referral_code = models.CharField(max_length=50, blank=True, default="")
    reward_status = models.IntegerField(
        choices=ReferralRewardStatus.choices, default=ReferralRewardStatus.PENDING
    )
    # "credit", "discount_pct", "discount_fixed", etc. — project-defined
    reward_type = models.CharField(max_length=50)
    reward_value = models.DecimalField(max_digits=12, decimal_places=2)
    rewarded_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    # Links to payment transaction or subscription that triggered the reward
    reference_id = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        abstract = True
