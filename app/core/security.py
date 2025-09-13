import hmac
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from urllib.parse import unquote, parse_qsl

from fastapi import HTTPException
from app.schemas.token import TokenData

from jose import JWTError, jwt
from pydantic import BaseModel, Field

from app.core.config import settings

class InitDataUser(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    language_code: str

class InitData(BaseModel):
    query_id: Optional[str] = None
    user: InitDataUser
    auth_date: int
    hash: str

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def validate_init_data(init_data: str, bot_token: str, expiration_hours: int = 1) -> Optional[Dict]:
    try:
        parsed_data = dict(parse_qsl(init_data))
    except ValueError:
        return None

    if "hash" not in parsed_data:
        return None

    init_data_hash = parsed_data.pop("hash")

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(parsed_data.items())
    )

    secret_key = hmac.new(
        key="WebAppData".encode(), msg=bot_token.encode(), digestmod=hashlib.sha256
    ).digest()

    calculated_hash = hmac.new(
        key=secret_key, msg=data_check_string.encode(), digestmod=hashlib.sha256
    ).hexdigest()

    if calculated_hash != init_data_hash:
        return None

    auth_date = datetime.fromtimestamp(int(parsed_data["auth_date"]), tz=timezone.utc)
    if datetime.now(timezone.utc) - auth_date > timedelta(hours=expiration_hours):
        return None
    
    # Декодируем поле user, если оно в формате JSON-строки
    if 'user' in parsed_data and isinstance(parsed_data['user'], str):
        parsed_data['user'] = json.loads(unquote(parsed_data['user']))

    return parsed_data

def decode_access_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        telegram_id: str = payload.get("sub")
        if telegram_id is None:
            raise HTTPException(status_code=401, detail="Could not validate credentials")
        token_data = TokenData(telegram_id=telegram_id)
    except JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return token_data