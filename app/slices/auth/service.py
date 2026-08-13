from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.core.security import verify_password, create_access_token
from .models import User
from .schemas import LoginRequest


def loginService(request: LoginRequest, db: Session):
    """
    Service function to handle user login.

    Args:
        request (LoginRequest): The login request containing username and password.
        db (Session): The database session.

    Returns:
        dict: A dictionary containing the access token and token type.

    Raises:
        HTTPException: If the username or password is incorrect.
    """
    user = db.query(User).filter(User.username == request.username).first()
    
    # Check if user exists and password matches
    if not user or not verify_password(request.password, str(user.hashed_password)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    
    # Generate JWT Token
    access_token = create_access_token(data={"sub": str(user.username)})
    return {"access_token": access_token, "token_type": "bearer"}