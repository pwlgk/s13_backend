# app/api/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from app.core import security
from app.core.config import settings
from app.db.session import get_db
from app.crud import crud_user
from app.models.user import User
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Notifier")

# Создаем экземпляр HTTPBearer. Он будет искать заголовок Authorization.
bearer_scheme = HTTPBearer()

async def get_current_user(
    db: AsyncSession = Depends(get_db), 
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> User:
    """
    Зависимость для получения текущего пользователя из JWT токена.
    Проверяет, что пользователь существует и не заблокирован.
    """
    if credentials.scheme != "Bearer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication scheme",
        )
    
    token = credentials.credentials
    token_data = security.decode_access_token(token)
    
    user = await crud_user.get_user_by_telegram_id(db, telegram_id=int(token_data.telegram_id))
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    if user.is_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is blocked")
        
    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Зависимость для проверки прав администратора.
    Получает текущего пользователя и проверяет его ID по списку ADMIN_TELEGRAM_IDS.
    """
    try:
        # Преобразуем строку из .env в список целых чисел
        admin_ids_str = settings.ADMIN_TELEGRAM_IDS.split(',')
        admin_ids = [int(admin_id.strip()) for admin_id in admin_ids_str]
    except (ValueError, AttributeError):
        # Если переменная в .env некорректна, логируем и запрещаем доступ
        # В реальном приложении здесь должен быть логгер
        logger.error("ERROR: ADMIN_TELEGRAM_IDS is not configured correctly in .env file.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin configuration error."
        )

    if current_user.telegram_id not in admin_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user


async def get_current_user_allow_blocked(
    db: AsyncSession = Depends(get_db), 
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)
) -> User:
    """
    "Мягкая" зависимость для эндпоинта профиля.
    """    
   
    if credentials.scheme != "Bearer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authentication scheme",
        )
    
    token = credentials.credentials
    try:
        token_data = security.decode_access_token(token)
    except HTTPException as e:
        raise e # Пробрасываем ошибку дальше

    user = await crud_user.get_user_by_telegram_id(db, telegram_id=int(token_data.telegram_id))
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    

    return user