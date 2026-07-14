from pydantic import BaseModel, Field


class Principal(BaseModel):
    user_id: str
    account_id: str | None = None
    role: str
    email: str | None = None


class BalanceResponse(BaseModel):
    account_id: str
    balance: int
    low_balance_threshold: int
    is_low_balance: bool


class LedgerEntryResponse(BaseModel):
    id: str
    account_id: str
    amount: int
    reason: str
    source_event_id: str | None = None
    related_account_id: str | None = None
    listing_id: str | None = None
    metadata: dict
    created_at: str


class CreateListingRequest(BaseModel):
    credits: int = Field(gt=0)
    price_cents: int = Field(gt=0)
    currency: str | None = Field(default=None, max_length=8)


class MarketplaceListingResponse(BaseModel):
    id: str
    seller_account_id: str
    credits: int
    price_cents: int
    currency: str
    status: str
    buyer_account_id: str | None = None
    created_by_user_id: str | None = None
    created_at: str
    updated_at: str
    sold_at: str | None = None


class BuyListingRequest(BaseModel):
    payment_intent_id: str | None = Field(default=None, max_length=160)


class ConsumeCreditsRequest(BaseModel):
    amount: int = Field(gt=0)
    event_id: str = Field(min_length=1, max_length=160)
    reason: str = Field(default="consumption", max_length=64)
    metadata: dict = Field(default_factory=dict)


class CreditAccountRequest(BaseModel):
    account_id: str = Field(min_length=1, max_length=128)
    amount: int = Field(gt=0)
    event_id: str = Field(min_length=1, max_length=160)
    reason: str = Field(default="adjustment", max_length=64)
    metadata: dict = Field(default_factory=dict)
