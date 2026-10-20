from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import CSRF_COOKIE, SESSION_COOKIE, get_current_user, rate_limit
from app.core.errors import error_responses
from app.core.ratelimit import login_limiter, register_limiter, waitlist_limiter
from app.core.security import new_csrf_token
from app.db.session import get_db
from app.models import User, WaitlistSignup
from app.schemas.auth import Credentials, Registration, UserOut, WaitlistIn
from app.services import auth as auth_service

router = APIRouter(tags=["auth"])


def _set_auth_cookies(response: Response, session_token: str) -> None:
    settings = get_settings()
    common = {
        "domain": settings.cookie_domain,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "path": "/",
        "max_age": settings.session_ttl_hours * 3600,
    }
    response.set_cookie(SESSION_COOKIE, session_token, httponly=True, **common)  # type: ignore[arg-type]
    # Double-submit CSRF token: readable by the frontend, echoed in X-CSRF-Token.
    response.set_cookie(CSRF_COOKIE, new_csrf_token(), httponly=False, **common)  # type: ignore[arg-type]


def _clear_auth_cookies(response: Response) -> None:
    domain = get_settings().cookie_domain
    response.delete_cookie(SESSION_COOKIE, path="/", domain=domain)
    response.delete_cookie(CSRF_COOKIE, path="/", domain=domain)


@router.post(
    "/auth/register",
    response_model=UserOut,
    status_code=201,
    responses=error_responses(409, 422, 429),
)
def register(
    body: Registration, request: Request, response: Response, db: Session = Depends(get_db)
) -> User:
    rate_limit(register_limiter, request)
    user = auth_service.register(db, body.email, body.password)
    token = auth_service.start_session(db, user)
    db.commit()
    _set_auth_cookies(response, token)
    return user


@router.post("/auth/login", response_model=UserOut, responses=error_responses(401, 422, 429))
def login(
    body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)
) -> User:
    rate_limit(login_limiter, request, body.email)
    user = auth_service.authenticate(db, body.email, body.password)
    token = auth_service.start_session(db, user)
    db.commit()
    _set_auth_cookies(response, token)
    return user


@router.post("/auth/logout", status_code=204, response_class=Response)
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    # Logout works without a valid CSRF token: it only ever reduces privileges.
    auth_service.end_session(db, request.cookies.get(SESSION_COOKIE))
    db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_auth_cookies(response)
    return response


@router.get("/auth/me", response_model=UserOut, responses=error_responses(401))
def me(request: Request, response: Response, user: User = Depends(get_current_user)) -> User:
    if not request.cookies.get(CSRF_COOKIE):
        settings = get_settings()
        response.set_cookie(
            CSRF_COOKIE,
            new_csrf_token(),
            httponly=False,
            secure=settings.cookie_secure,
            samesite="lax",
            domain=settings.cookie_domain,
            path="/",
            max_age=settings.session_ttl_hours * 3600,
        )
    return user


@router.post(
    "/waitlist",
    status_code=202,
    response_class=Response,
    tags=["waitlist"],
    responses=error_responses(422, 429),
)
def join_waitlist(body: WaitlistIn, request: Request, db: Session = Depends(get_db)) -> Response:
    """Phase 0 validation sign-up. Always 202, so it cannot reveal who already signed up."""
    rate_limit(waitlist_limiter, request)
    db.execute(
        pg_insert(WaitlistSignup)
        .values(email=body.email, source=body.source, note=body.note)
        .on_conflict_do_nothing(index_elements=["email"])
    )
    db.commit()
    return Response(status_code=202)
