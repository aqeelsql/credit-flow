export type AccountRole = "Owner" | "TenantAdmin" | "Member" | "SuperAdmin";

export type AccountType = "individual" | "team" | "platform";

export type Account = {
  id: string;
  name: string;
  type: AccountType;
  role: AccountRole;
  plan: string;
  credits: number;
  teamSize: number;
};

export type SessionPayload = {
  user_id: string;
  account_id: string;
  role: AccountRole;
  jti: string;
  email?: string;
  exp: number;
};

export type TeamMember = {
  id: string;
  name: string;
  email: string;
  role: AccountRole;
  status: "Active" | "Invited";
};

export type Invoice = {
  id: string;
  date: string;
  amount: string;
  status: "Paid" | "Open" | "Failed";
};

export type CreditListing = {
  id: string;
  seller: string;
  credits: number;
  price: string;
  status: "Listed" | "Available";
};

export type DraftContent = {
  id: string;
  title: string;
  body: string;
  hasImage?: boolean;
};

export type ScheduledPost = {
  id: string;
  title: string;
  date: string;
  status: "Scheduled" | "Published" | "Canceled";
  recurring?: "None" | "Weekly";
};

export type AdminAccount = {
  id: string;
  name: string;
  owner: string;
  type: AccountType;
  plan: string;
  credits: number;
  usage: number;
};

export type ActiveSession = {
  id: string;
  account: string;
  user: string;
  role: AccountRole;
  startedAt: string;
  lastSeen: string;
  status: "Active" | "Revoked";
};

export type AuditRow = {
  id: string;
  account: string;
  actor: string;
  event: string;
  timestamp: string;
};


