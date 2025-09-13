# app/api/v1/endpoints/auth.py
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.ext.asyncio import AsyncSession
# --- НОВЫЙ ИМПОРТ ---
from sqlalchemy.exc import IntegrityError

from app.core import security
from app.core.config import settings
from app.db.session import get_db
from app.schemas.token import Token
from app.schemas.user import UserCreate
from app.crud import crud_user

router = APIRouter()

@router.post("/login", response_model=Token)
async def login_for_access_token(
    db: AsyncSession = Depends(get_db),
    init_data: str = Body(..., embed=True)
):
    validated_data = security.validate_init_data(init_data, settings.TELEGRAM_BOT_TOKEN)
    if not validated_data:
        raise HTTPException(status_code=401, detail="Invalid Telegram InitData")
    
    user_data = validated_data.get("user")
    telegram_id = user_data.get("id")

    user = await crud_user.get_user_by_telegram_id(db, telegram_id=telegram_id)
    
    if not user:
        # --- НАЧАЛО ИЗМЕНЕНИЙ: ОБРАБОТКА RACE CONDITION ---
        user_in = UserCreate(
            telegram_id=telegram_id,
            first_name=user_data.get("first_name"),
            last_name=user_data.get("last_name"),
            username=user_data.get("username")
        )
        try:
            user = await crud_user.create_user(db, user_in=user_in)
        except IntegrityError:
            # Если произошла ошибка уникальности, значит, другой запрос нас опередил.
            # Откатываем транзакцию и просто снова загружаем пользователя.
            await db.rollback()
            user = await crud_user.get_user_by_telegram_id(db, telegram_id=telegram_id)
            if not user:
                # Очень редкий случай, но на всякий случай
                raise HTTPException(status_code=500, detail="Could not create or find user after race condition.")
        # --- КОНЕЦ ИЗМЕНЕНИЙ ---

    # --- ДОПОЛНИТЕЛЬНОЕ УЛУЧШЕНИЕ: ОБНОВЛЕНИЕ ДАННЫХ ---
    # Пользователь мог сменить имя или username в Telegram, обновим их при входе
    if (user.username != user_data.get("username") or
        user.first_name != user_data.get("first_name") or
        user.last_name != user_data.get("last_name")):
        
        user.username = user_data.get("username")
        user.first_name = user_data.get("first_name")
        user.last_name = user_data.get("last_name")
        await db.commit()
        await db.refresh(user)

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": str(user.telegram_id)}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}