from decimal import Decimal, ROUND_HALF_UP

from app.config import get_settings


def split_agreed_amount(agreed: float) -> tuple[float, float, float]:
    """Return (agreed_amount, platform_fee, freelancer_amount) rounded to cents."""
    rate = Decimal(str(get_settings().platform_fee_rate))
    agreed_amount = Decimal(str(agreed)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    platform_fee = (agreed_amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    freelancer_amount = (agreed_amount - platform_fee).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(agreed_amount), float(platform_fee), float(freelancer_amount)
