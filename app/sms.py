import httpx

from app.config import settings
from app.phone import normalize_phone_number


class SMSProviderUnavailable(Exception):
    pass


def twilio_is_configured() -> bool:
    return bool(
        settings.twilio_account_sid.strip()
        and settings.twilio_auth_token.strip()
        and settings.twilio_from_number.strip()
    )


async def send_recovery_code(phone_number: str, code: str) -> None:
    account_sid = settings.twilio_account_sid.strip()
    auth_token = settings.twilio_auth_token.strip()
    from_number = settings.twilio_from_number.strip()
    if not account_sid or not auth_token or not from_number:
        raise SMSProviderUnavailable("Twilio SMS is not configured.")
    try:
        from_number = normalize_phone_number(from_number)
    except ValueError as error:
        raise SMSProviderUnavailable("Twilio SMS is not configured correctly.") from error

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{account_sid}/Messages.json"
    )
    message = (
        f"Your TrackGuard authenticator recovery code is {code}. "
        "It expires in 5 minutes. If you did not request this, ignore this message."
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                data={"From": from_number, "To": phone_number, "Body": message},
                auth=(account_sid, auth_token),
            )
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise SMSProviderUnavailable("Twilio could not accept the recovery message.") from error


async def send_phone_verification_code(phone_number: str, code: str) -> None:
    account_sid = settings.twilio_account_sid.strip()
    auth_token = settings.twilio_auth_token.strip()
    from_number = settings.twilio_from_number.strip()
    if not account_sid or not auth_token or not from_number:
        raise SMSProviderUnavailable("Twilio SMS is not configured.")
    try:
        from_number = normalize_phone_number(from_number)
    except ValueError as error:
        raise SMSProviderUnavailable("Twilio SMS is not configured correctly.") from error

    url = (
        f"https://api.twilio.com/2010-04-01/Accounts/"
        f"{account_sid}/Messages.json"
    )
    message = (
        f"Your TrackGuard phone verification code is {code}. "
        "It expires in 5 minutes. If you did not request this, ignore this message."
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                url,
                data={"From": from_number, "To": phone_number, "Body": message},
                auth=(account_sid, auth_token),
            )
            response.raise_for_status()
    except httpx.HTTPError as error:
        raise SMSProviderUnavailable("Twilio could not accept the verification message.") from error
