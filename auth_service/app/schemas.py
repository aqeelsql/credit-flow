from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    account_name: str | None = Field(default=None, max_length=180)
    invite_code: str | None = Field(default=None, min_length=16)


class SignupResponse(BaseModel):
    status: str
    user_id: str
    account_id: str | None = None
    message: str
    access_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    role: str | None = None
    jti: str | None = None


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=16)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    account_id: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user_id: str
    account_id: str
    role: str
    jti: str


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class SwitchAccountRequest(BaseModel):
    account_id: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=4, max_length=12)
    password: str = Field(min_length=8, max_length=128)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class RevokeSessionRequest(BaseModel):
    jti: str


class SessionRow(BaseModel):
    jti: str
    user_id: str
    account_id: str
    role: str
    expires_at: str
    status: str


class Principal(BaseModel):
    user_id: str
    account_id: str | None = None
    role: str
    jti: str
    email: str | None = None




