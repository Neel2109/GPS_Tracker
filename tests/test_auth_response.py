from datetime import datetime

from app.schemas import UserResponse


def test_local_user_response_accepts_reserved_internal_email():
    user = UserResponse(
        id="local-user",
        name="TrackGuard Owner",
        email="owner@trackguard.local",
        created_at=datetime.utcnow(),
    )

    assert user.email == "owner@trackguard.local"
