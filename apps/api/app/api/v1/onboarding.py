"""Public (unauthenticated) client signup + business onboarding, and the
authenticated account-status check the post-signup pages poll. No
Collection/Disbursement/payment-provider surface lives here — see
app/services/onboarding.py's module docstring.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.envelope import ApiResponse
from app.schemas.onboarding import (
    AccountStatusRead,
    OnboardingRegisterRequest,
    OnboardingRegisterResponse,
    ResendVerificationRequest,
    ResendVerificationResponse,
    TenantVerificationRead,
)
from app.services.onboarding import OnboardingService

router = APIRouter()


@router.post("/register", response_model=ApiResponse[OnboardingRegisterResponse], status_code=201)
async def register(
    payload: OnboardingRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[OnboardingRegisterResponse]:
    result = await OnboardingService(db).register(payload)

    return ApiResponse(
        data=OnboardingRegisterResponse(
            tenant_id=result.tenant_id,
            status="submitted",
            message=(
                "Account created. Please check your email to verify your Infinity Radius "
                "account. Your business details have also been submitted for platform review."
            ),
        )
    )


@router.post(
    "/resend-verification-email", response_model=ApiResponse[ResendVerificationResponse]
)
async def resend_verification_email(
    payload: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ResendVerificationResponse]:
    """Rate-limited by the global per-IP RateLimitMiddleware (see
    app.main) — deliberately returns the same response whether or not the
    email exists, so this can't be used to enumerate accounts."""
    await OnboardingService(db).resend_verification_by_email(email=payload.email)
    return ApiResponse(
        data=ResendVerificationResponse(
            sent=True,
            message="If an account exists for that email, a verification link has been sent.",
        )
    )


@router.get("/account-status", response_model=ApiResponse[AccountStatusRead])
async def get_account_status(
    user: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AccountStatusRead]:
    """Powers /account/verify-email, /account/pending-review, and friends.
    Deliberately uses AuthContext (any authenticated user), not
    TenantContext — a pending/rejected/suspended tenant is exactly who
    needs to reach this endpoint, and TenantContext would 403 them."""
    if user.tenant_id is None:
        return ApiResponse(
            data=AccountStatusRead(tenant_status="", email_verified=False, verification=None)
        )

    tenant_status, email_verified, verification = await OnboardingService(
        db
    ).get_account_status(tenant_id=user.tenant_id, owner_id=user.id)

    return ApiResponse(
        data=AccountStatusRead(
            tenant_status=tenant_status,
            email_verified=email_verified,
            verification=(
                TenantVerificationRead.model_validate(verification)
                if verification is not None
                else None
            ),
        )
    )
