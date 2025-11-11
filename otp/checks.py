from django.core.checks import Error, register

from . import conf


@register()
def otp_conf_check(app_configs, **kwargs):
    errors = []

    if conf.TOKEN_LENGTH < 4:
        errors.append(Error(
            "TOKEN_LENGTH should be at least 4 for security reasons.",
            id="verification.E001",
        ))

    if conf.TOKEN_LIFETIME_SECONDS <= 0:
        errors.append(Error(
            "TOKEN_LIFETIME_SECONDS must be positive.",
            id="verification.E002",
        ))

    if conf.REQUEST_COOLDOWN_SECONDS < 0:
        errors.append(Error(
            "REQUEST_COOLDOWN_SECONDS must be non-negative.",
            id="verification.E003",
        ))

    if conf.REQUEST_COOLDOWN_SECONDS > conf.TOKEN_LIFETIME_SECONDS:
        errors.append(Error(
            "REQUEST_COOLDOWN_SECONDS should not exceed TOKEN_LIFETIME_SECONDS.",
            id="verification.E004",
        ))

    if conf.MAX_ATTEMPTS < 1:
        errors.append(Error(
            "MAX_ATTEMPTS should be positive.",
            id="verification.E005",
        ))

    if conf.THROTTLE_SECONDS <= 0:
        errors.append(Error(
            "THROTTLE_SECONDS must be positive.",
            id="verification.E006",
        ))

    if conf.THROTTLE_SECONDS < conf.REQUEST_COOLDOWN_SECONDS:
        errors.append(Error(
            "THROTTLE_SECONDS should not be less than REQUEST_COOLDOWN_SECONDS.",
            id="verification.E007",
        ))

    if conf.TEMPORARY_PERMISSIONS_LIFETIME_SECONDS <= 0:
        errors.append(
            Error(
                "TEMPORARY_PERMISSIONS_LIFETIME_SECONDS must be a positive integer.",
                id="verifications.E008",
            )
        )

    return errors
