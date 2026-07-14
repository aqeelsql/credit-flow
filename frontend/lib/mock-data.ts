import type {
  Account,
  ActiveSession,
  AdminAccount,
  AuditRow,
  CreditListing,
  DraftContent,
  Invoice,
  ScheduledPost,
  SessionPayload,
  TeamMember
} from "@/lib/types";

export const demoAccounts: Account[] = [
  {
    id: "acct_individual_101",
    name: "Raja's Studio",
    type: "individual",
    role: "Owner",
    plan: "Pro",
    credits: 18420,
    teamSize: 1
  },
  {
    id: "acct_team_204",
    name: "Northstar Media",
    type: "team",
    role: "TenantAdmin",
    plan: "Scale",
    credits: 64200,
    teamSize: 8
  },
  {
    id: "acct_team_309",
    name: "Atlas Growth",
    type: "team",
    role: "Member",
    plan: "Starter",
    credits: 6200,
    teamSize: 4
  }
];

export const platformAccount: Account = {
  id: "platform",
  name: "CreditFlow Platform",
  type: "platform",
  role: "SuperAdmin",
  plan: "Platform",
  credits: 0,
  teamSize: 0
};

export const dashboardSummary = {
  creditBalance: 18420,
  creditsUsed: 1580,
  contentGenerated: 216,
  teamSize: 1,
  currentPlan: "Pro",
  usagePercent: 62
};

export const teamMembers: TeamMember[] = [
  {
    id: "mem_1",
    name: "Raja Ahmed",
    email: "raja@example.com",
    role: "Owner",
    status: "Active"
  },
  {
    id: "mem_2",
    name: "Maya Singh",
    email: "maya@example.com",
    role: "TenantAdmin",
    status: "Active"
  },
  {
    id: "mem_3",
    name: "Noah Reed",
    email: "noah@example.com",
    role: "Member",
    status: "Invited"
  }
];

export const invoices: Invoice[] = [
  { id: "INV-1042", date: "2026-07-01", amount: "$149.00", status: "Paid" },
  { id: "INV-1018", date: "2026-06-01", amount: "$149.00", status: "Paid" },
  { id: "INV-997", date: "2026-05-01", amount: "$99.00", status: "Paid" }
];

export const marketplaceListings: CreditListing[] = [
  { id: "cr_1", seller: "Northstar Media", credits: 10000, price: "$86.00", status: "Available" },
  { id: "cr_2", seller: "Atlas Growth", credits: 5000, price: "$48.00", status: "Available" },
  { id: "cr_3", seller: "Brightline AI", credits: 25000, price: "$210.00", status: "Available" }
];

export const ownListings: CreditListing[] = [
  { id: "own_1", seller: "Raja's Studio", credits: 2000, price: "$21.00", status: "Listed" }
];

export const drafts: DraftContent[] = [
  {
    id: "draft_1",
    title: "Founder perspective post",
    body: "A practical thread on reducing content review cycles with AI-assisted drafts."
  },
  {
    id: "draft_2",
    title: "Q3 product launch teaser",
    body: "A LinkedIn announcement draft with a short product narrative and call to action.",
    hasImage: true
  },
  {
    id: "draft_3",
    title: "Credit marketplace explainer",
    body: "A plain-language explainer for teams buying and selling surplus credits."
  }
];

export const scheduledPosts: ScheduledPost[] = [
  {
    id: "post_1",
    title: "Founder perspective post",
    date: "2026-07-13T10:00:00",
    status: "Scheduled",
    recurring: "None"
  },
  {
    id: "post_2",
    title: "Q3 product launch teaser",
    date: "2026-07-16T14:30:00",
    status: "Scheduled",
    recurring: "Weekly"
  }
];

export const linkedinPosts = [
  {
    id: "li_1",
    title: "Founder perspective post",
    status: "Scheduled",
    lastPublish: "Queued for Jul 13, 2026 10:00"
  },
  {
    id: "li_2",
    title: "Credit marketplace explainer",
    status: "Published",
    lastPublish: "Published Jul 7, 2026 09:15"
  },
  {
    id: "li_3",
    title: "Q3 product launch teaser",
    status: "Failed",
    lastPublish: "Failed Jul 8, 2026 11:02"
  }
];

export const adminAccounts: AdminAccount[] = [
  {
    id: "acct_individual_101",
    name: "Raja's Studio",
    owner: "raja@example.com",
    type: "individual",
    plan: "Pro",
    credits: 18420,
    usage: 1580
  },
  {
    id: "acct_team_204",
    name: "Northstar Media",
    owner: "maya@example.com",
    type: "team",
    plan: "Scale",
    credits: 64200,
    usage: 18100
  },
  {
    id: "acct_team_309",
    name: "Atlas Growth",
    owner: "ops@atlas.example",
    type: "team",
    plan: "Starter",
    credits: 6200,
    usage: 4300
  }
];

export const activeSessions: ActiveSession[] = [
  {
    id: "jti_8f31",
    account: "Raja's Studio",
    user: "raja@example.com",
    role: "Owner",
    startedAt: "2026-07-09 08:12",
    lastSeen: "2026-07-09 12:51",
    status: "Active"
  },
  {
    id: "jti_9a77",
    account: "Northstar Media",
    user: "maya@example.com",
    role: "TenantAdmin",
    startedAt: "2026-07-09 06:20",
    lastSeen: "2026-07-09 12:49",
    status: "Active"
  },
  {
    id: "jti_2c14",
    account: "Atlas Growth",
    user: "ops@atlas.example",
    role: "Member",
    startedAt: "2026-07-08 18:02",
    lastSeen: "2026-07-09 10:23",
    status: "Active"
  }
];

export const auditRows: AuditRow[] = [
  {
    id: "aud_1",
    account: "Raja's Studio",
    actor: "raja@example.com",
    event: "Listed 2,000 credits for marketplace sale",
    timestamp: "2026-07-09 12:40"
  },
  {
    id: "aud_2",
    account: "Northstar Media",
    actor: "maya@example.com",
    event: "Invited noah@example.com as Member",
    timestamp: "2026-07-09 11:18"
  },
  {
    id: "aud_3",
    account: "Atlas Growth",
    actor: "ops@atlas.example",
    event: "Canceled scheduled LinkedIn post post_991",
    timestamp: "2026-07-08 17:34"
  },
  {
    id: "aud_4",
    account: "Raja's Studio",
    actor: "system",
    event: "Refresh token rotated after silent refresh",
    timestamp: "2026-07-08 15:12"
  }
];

export function makeMockJwt(account: Account, email = "raja@example.com"): string {
  const payload: SessionPayload = {
    user_id: account.role === "SuperAdmin" ? "usr_superadmin" : "usr_demo_001",
    account_id: account.id,
    role: account.role,
    jti: `jti_${Math.random().toString(16).slice(2, 10)}`,
    email,
    exp: Math.floor(Date.now() / 1000) + 15 * 60
  };

  return [encodeBase64Url({ alg: "HS256", typ: "JWT" }), encodeBase64Url(payload), "mock-signature"].join(".");
}

export function decodeJwtPayload(token: string): SessionPayload | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) {
      return null;
    }

    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
    const json =
      typeof window === "undefined"
        ? Buffer.from(padded, "base64").toString("utf8")
        : decodeURIComponent(
            Array.from(atob(padded))
              .map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, "0")}`)
              .join("")
          );
    return JSON.parse(json) as SessionPayload;
  } catch {
    return null;
  }
}

function encodeBase64Url(value: unknown): string {
  const json = JSON.stringify(value);
  const base64 =
    typeof window === "undefined"
      ? Buffer.from(json).toString("base64")
      : btoa(unescape(encodeURIComponent(json)));

  return base64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

