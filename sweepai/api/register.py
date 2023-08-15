from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

router = APIRouter()

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class User(BaseModel):
    email: EmailStr
    password: str

    @validator('password')
    def validate_password(cls, password):
        if len(password) < 8:
            raise ValueError('Password must be at least 8 characters')
        return password

users = {}

@router.post("/register")
def register(user: User):
    if user.email in users:
        raise HTTPException(status_code=400, detail="Email already registered")
    users[user.email] = pwd_context.hash(user.password)
    return

