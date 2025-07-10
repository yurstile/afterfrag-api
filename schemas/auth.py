from pydantic import BaseModel

class UserCreate(BaseModel):
    username: str
    password: str
    turnstile_token: str

class LoginRequest(BaseModel):
    username: str
    password: str
    turnstile_token: str

class Token(BaseModel):
    access_token: str
    token_type: str
    onboarding_completed: bool

class UserResponse(BaseModel):
    user_id: int
    username: str
    email: str
    display_name: str
    profile_picture_url: str | None
    is_approved: bool
    role: str 