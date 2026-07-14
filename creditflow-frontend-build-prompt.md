# Prompt: Build the CreditFlow AI Platform Frontend

Copy everything below into your coding tool (e.g. Claude Code) as the task prompt.

---

## Task

Build the frontend application for **CreditFlow**, a multi-tenant, credit-based SaaS platform for AI-assisted content generation and social publishing. This is the frontend ONLY — it consumes REST and SSE APIs from a backend API Gateway that already exists (or is being built separately). Do not build backend services.

### Tech constraints (must follow exactly)
- **Framework:** Next.js (App Router)
- **Styling:** Plain CSS only — no Tailwind, no CSS-in-JS libraries, no UI component libraries. Use CSS Modules or global stylesheets.
- **Calendar UI:** FullCalendar or React Big Calendar (either is acceptable) for the scheduling calendar view.
- **All project files must live inside a single root folder named `frontend/`** — e.g. `frontend/app`, `frontend/components`, `frontend/styles`, `frontend/lib`, etc. Do not scatter files outside this folder.
- Communication with the backend is **REST** for standard calls and **SSE (EventSource)** for streaming AI generation output.

---

## Multi-Tenancy & Roles (must be modeled correctly across every page)

- All domain data is scoped by `account_id`, not `user_id`.
- An **individual signup** is an Account of type `individual` with exactly one member (the Owner).
- A **team** is an Account of type `team` with multiple members and roles.
- Roles: **Owner, Admin, Member** — plus a platform-level **SuperAdmin** role that is not account-scoped.
- A single logged-in user may belong to **multiple accounts**. The UI must support switching between them.
- The JWT issued by the backend carries `user_id`, `account_id`, `role`, and `jti`. The frontend should read the role/account out of the token (or a decoded session object) to drive UI gating — but treat this purely as a UX convenience. The real security boundary is server-side; the frontend just hides/redirects appropriately.

---

## Pages & Routes to Build

### Public / Unauthenticated Pages
1. **Home / Marketing Page** — professional landing page with a hero section, feature highlights, pricing tiers, and a sign-up call to action.
2. **Sign Up** — email + password form. On submit, tells the user a verification email has been sent (does not log them in immediately).
3. **Log In** — email + password form, with a "Forgot password" link.
4. **Forgot Password (OTP flow)** — three-step flow:
   - Step 1: request a one-time code by email.
   - Step 2: enter the OTP.
   - Step 3: set a new password.
   - Make clear in the UI that the OTP is short-lived and single-use (e.g. show a countdown or expiry note).
5. **Email Verification Landing** — a page that consumes a token from the verification link's query string, calls the backend to activate the account, and shows success/failure state.

### Onboarding (post-login, pre-dashboard)
6. **Create or Join Account** — new user chooses to: create an Individual account, create a Team account, or accept a pending team invite.
7. **Account Switcher** — a persistent UI component (e.g. in the top nav/header) present on every authenticated page, listing every account the user belongs to. Selecting a different account should trigger fetching a new account-scoped session/JWT and refresh the app's data context.

### Owner-Only Pages
8. **Owner Dashboard** — account-wide summary: usage, credit balance, team size, and current plan tier.
9. **Team Management** — invite members (by email), assign/change member roles, remove members.
10. **Billing & Invoices** — current subscription plan, upgrade/downgrade controls, invoice history list, payment method display.
11. **Credits & Marketplace** — buy credits (Stripe Checkout redirect), list your own surplus credits for sale, browse and buy credits listed by other accounts.

### Owner + Member Pages (visible to both roles)
12. **Content Studio** — prompt input box, streaming AI text output rendered **token-by-token via SSE** (do not wait for the full response before rendering), an optional "Generate image" bonus action, and a "Save as draft" action.
13. **Calendar / Scheduler** — month/week calendar view (via FullCalendar or React Big Calendar) showing scheduled content. Supports placing drafted content on a publish date/time, rescheduling, and canceling a scheduled post.
14. **LinkedIn Connections** — OAuth connect/disconnect flow for LinkedIn, connection status indicator, and last-publish status shown per post.

### Platform Admin Console (SuperAdmin Only)
15. **Cross-account directory** — search and browse all accounts on the platform.
16. **Active sessions viewer** — list active JWT sessions per account (sourced live from Redis on the backend) with the ability to revoke a session.
17. **Usage & credits overview** — per-account usage and credit balance, pulled from the Usage and Credits services.
18. **Audit log** — a searchable timeline of domain events per account, sourced from the Admin Service's `audit_log`.

---

## Cross-Cutting Frontend Requirements (apply platform-wide)

- **JWT handling:** store the access token in memory (e.g. in-memory app state/context — never localStorage), and expect the refresh token to live in an httpOnly cookie set by the backend. Implement silent refresh on access-token expiry (detect a 401, call the refresh endpoint, retry the original request).
- **Route guarding by role:** Owner / Member / SuperAdmin routes must be protected with a graceful redirect (e.g. to login or to an "unauthorized" page) — not just a hidden nav link. Implement this as route middleware/guards, not just conditional rendering.
- **SSE for AI generation:** the Content Studio must consume Server-Sent Events and render tokens as they arrive, not buffer and wait for completion.
- **Confirmation steps for destructive actions:** revoking a session, removing a team member, and canceling a scheduled post must all show a confirmation dialog before executing.
- **Account-level data scoping:** every list/detail view (content, credits, billing, usage) must reflect the currently active account from the Account Switcher, not the raw logged-in user.

## Bonus / Stretch Features (nice to have, implement if time allows)
- **AI Image Generation** in the Content Studio: an optional "generate an accompanying image" action attached to the content record.
- **Recurring schedules:** allow a scheduled post in the Calendar/Scheduler UI to repeat on a cadence (e.g. weekly) instead of a single one-off time.
- Image attached to a post should visibly indicate it will be published as a text+image post rather than text-only.

---

## Visual Design System (colors & typography)

Use this design system throughout — don't default to generic Tailwind-gray or a beige/terracotta SaaS template. The direction is **vibrant, cool-toned, and professional**: a fintech-grade dashboard with an electric, tech-forward accent, not a soft consumer app.

### Color palette
| Token | Hex | Use |
|---|---|---|
| `--color-bg` | `#F4F6FB` | App background, page canvas (cool off-white, not cream) |
| `--color-surface` | `#FFFFFF` | Cards, panels, modals |
| `--color-ink` | `#0F1730` | Primary text, headings (deep navy-black, not pure black) |
| `--color-ink-muted` | `#5B6478` | Secondary text, captions, labels |
| `--color-primary` | `#3B3FE0` | Primary actions, links, active nav state (electric indigo) |
| `--color-primary-hover` | `#2C2FB8` | Hover/active state for primary |
| `--color-accent` | `#12D6C4` | Secondary accent — highlights, streaming/live indicators, credit-positive states (vivid teal-cyan) |
| `--color-accent-soft` | `#E4FBF8` | Accent background tint (badges, subtle highlights) |
| `--color-success` | `#1FAE7A` | Success states, published posts, credited transactions |
| `--color-warning` | `#F2A93B` | Low balance, pending, dunning/grace-period states |
| `--color-danger` | `#F0435E` | Destructive actions, failed publishes, errors |
| `--color-border` | `#E3E7F0` | Hairline borders, dividers, table rules |

Use `--color-primary` (indigo) as the dominant brand color for navigation, primary buttons, and the account switcher. Reserve `--color-accent` (teal-cyan) specifically for "live" or "in-motion" moments — the SSE token stream in the Content Studio, active session indicators, real-time usage meters — so it reads as the platform's signature color for anything happening *right now*. Don't let the two accents compete on the same element.

### Typography
| Role | Typeface | Notes |
|---|---|---|
| Display / headings | **Space Grotesk** | Geometric, slightly technical character — used for page titles, dashboard headers, marketing hero. Use with restraint: large sizes only, medium/semibold weight. |
| Body / UI | **Inter** | All body copy, form labels, buttons, nav items. Highly legible at small sizes across the dense admin/dashboard screens. |
| Data / numeric | **IBM Plex Mono** | Credit balances, invoice amounts, timestamps, audit log entries, token counts. Tabular figures for anything numeric reinforces the "financial ledger" feel of the credits system. |

Load all three via `next/font` (Google Fonts) rather than a CDN `<link>`, and expose them as CSS variables (`--font-display`, `--font-body`, `--font-mono`) in `globals.css` so every component references the variable, never the raw font name.

### Type scale (suggested, in rem)
`--text-xs: 0.75` · `--text-sm: 0.875` · `--text-base: 1` · `--text-lg: 1.125` · `--text-xl: 1.5` · `--text-2xl: 2` · `--text-3xl: 2.75` (hero only)

### Signature touch
Give the Content Studio's live token stream a subtle animated underline or cursor in `--color-accent` as tokens render — this becomes the one memorable "this platform feels alive" moment. Keep every other surface (dashboard cards, tables, forms) calm, high-contrast, and undecorated so that signature stands out rather than competing with ambient motion elsewhere.

---

## Suggested Folder Structure

```
frontend/
  app/
    (public)/
      page.tsx                  # Home / marketing
      signup/page.tsx
      login/page.tsx
      forgot-password/page.tsx
      verify-email/page.tsx
    (onboarding)/
      create-or-join/page.tsx
    (dashboard)/
      layout.tsx                 # includes Account Switcher + nav + route guards
      dashboard/page.tsx          # Owner dashboard
      team/page.tsx                # Team management (owner only)
      billing/page.tsx             # Billing & invoices (owner only)
      credits/page.tsx              # Credits & marketplace (owner only)
      content-studio/page.tsx        # Owner + member
      calendar/page.tsx               # Owner + member
      linkedin/page.tsx                # Owner + member
    (admin)/
      admin/directory/page.tsx          # SuperAdmin only
      admin/sessions/page.tsx
      admin/usage/page.tsx
      admin/audit-log/page.tsx
  components/
    AccountSwitcher/
    RouteGuard/
    ConfirmDialog/
    ContentStudio/
    Calendar/
    ...
  lib/
    api-client.ts       # REST wrapper with auth header + silent refresh
    sse-client.ts       # SSE helper for streaming generation
    auth-context.tsx    # in-memory access token + role/account state
  styles/
    globals.css
    variables.css
    (component-scoped .module.css files alongside their components)
  public/
```

---

## Deliverable
A working Next.js app inside `frontend/` implementing all pages above, with plain CSS styling, role-based route guarding, an account switcher, SSE-based streaming in the Content Studio, and a calendar-based scheduler. Backend endpoints can be stubbed/mocked for now if the real API Gateway isn't reachable — but structure the API client so swapping in real endpoints later requires minimal changes.
