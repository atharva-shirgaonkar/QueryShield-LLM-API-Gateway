"""API key management routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import generate_api_key, hash_api_key
from app.dependencies import get_current_user
from app.models import APIKey, User
from app.schemas.api_key import APIKeyCreate, APIKeyCreateResponse, APIKeyResponse


router = APIRouter()


@router.post(
    "",
    response_model=APIKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_api_key(
    payload: APIKeyCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIKeyCreateResponse:
    raw_key = generate_api_key()
    api_key = APIKey(
        user_id=current_user.id,
        key_hash=hash_api_key(raw_key),
        key_prefix=raw_key[:8],
        name=payload.name,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return APIKeyCreateResponse(
        id=api_key.id,
        key_prefix=api_key.key_prefix,
        name=api_key.name,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        key=raw_key,
    )


@router.get("", response_model=list[APIKeyResponse])
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[APIKey]:
    result = await db.scalars(
        select(APIKey)
        .where(APIKey.user_id == current_user.id)
        .order_by(APIKey.created_at.desc())
    )
    return list(result)


@router.delete("/{key_id}", response_model=APIKeyResponse)
async def delete_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> APIKey:
    api_key = await db.scalar(
        select(APIKey).where(
            APIKey.id == key_id,
            APIKey.user_id == current_user.id,
        )
    )
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )

    api_key.is_active = False
    await db.commit()
    await db.refresh(api_key)
    return api_key
