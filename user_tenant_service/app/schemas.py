from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

from app.models import AccountRole, AccountType, MemberStatus


class Principal(BaseModel):
    user_id: str
    account_id: str | None = None
    role: str
    email: str | None = None


class AccountResponse(BaseModel):
    id: str
    name: str
    type: AccountType
    role: AccountRole
    plan: str
    credits: int
    teamSize: int


class AccountSummaryResponse(BaseModel):
    id: str
    name: str
    type: AccountType
    plan: str
    credits: int
    teamSize: int


class MembershipResponse(BaseModel):
    id: str
    account_id: str
    account_name: str
    account_type: AccountType
    role: AccountRole
    status: MemberStatus
    plan: str
    credits: int
    team_size: int


class MembershipListResponse(BaseModel):
    memberships: list[MembershipResponse]



class PlatformAccountResponse(BaseModel):
    id: str
    name: str
    type: AccountType
    plan: str
    credits: int
    owner_user_id: str | None = None
    owner_email: EmailStr | None = None
    team_size: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

class CreateAccountRequest(BaseModel):
    type: AccountType = AccountType.INDIVIDUAL
    name: str = Field(min_length=1, max_length=180)


class InternalCreateIndividualRequest(BaseModel):
    email: EmailStr
    account_name: str | None = Field(default=None, max_length=180)


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: AccountRole = AccountRole.MEMBER


class InviteMemberResponse(BaseModel):
    invite_id: str
    account_id: str
    email: EmailStr
    role: AccountRole
    code: str
    expires_at: str


class AcceptInviteRequest(BaseModel):
    code: str = Field(min_length=16)


class InternalAcceptInviteRequest(BaseModel):
    code: str = Field(min_length=16)
    user_id: str = Field(min_length=1)
    email: EmailStr


class TeamMemberResponse(BaseModel):
    id: str
    user_id: str | None = None
    name: str
    email: EmailStr
    role: AccountRole
    status: str
    joined_at: datetime | None = None
    invite_id: str | None = None
    invited_by_user_id: str | None = None
    invite_accepted_at: datetime | None = None
    joined_via_invite: bool = False


class UpdateMemberRoleRequest(BaseModel):
    role: AccountRole



