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


class CreateAccountRequest(BaseModel):
    type: AccountType = AccountType.INDIVIDUAL
    name: str = Field(min_length=1, max_length=180)


class InternalCreateIndividualRequest(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, max_length=180)
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


class InternalValidateInviteRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=16)


class InternalAcceptInviteRequest(BaseModel):
    user_id: str
    name: str | None = Field(default=None, max_length=180)
    email: EmailStr
    code: str = Field(min_length=16)


class TeamMemberResponse(BaseModel):
    id: str
    user_id: str | None = None
    name: str | None = None
    email: EmailStr
    role: AccountRole
    status: str


class UpdateMemberRoleRequest(BaseModel):
    role: AccountRole


class AdminAccountListItem(BaseModel):
    id: str
    name: str
    type: AccountType
    plan: str
    credits: int
    team_size: int
    owner_name: str | None = None
    owner_email: EmailStr | None = None
    created_at: str
    updated_at: str


class AdminAccountListResponse(BaseModel):
    items: list[AdminAccountListItem]
