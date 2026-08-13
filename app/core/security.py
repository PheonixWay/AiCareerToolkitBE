import bcrypt
import jwt
from datetime import datetime, timedelta
from app.core.config import settings

def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Bcrypt requires bytes, so we encode the strings to utf-8 bytes
    password_bytes = plain_password.encode('utf-8')
    hashed_password_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_bytes, hashed_password_bytes)

def get_password_hash(password: str) -> str:
    # Convert password to bytes, generate a salt, and hash it
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    # Decode back to string so it can be saved in PostgreSQL easily
    return hashed_password.decode('utf-8')

def create_access_token(data: dict):
    to_encode = data.copy()
    # Token expires in 24 hours
    expire = datetime.utcnow() + timedelta(hours=int(settings.TOKEN_EXPIRY))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt