"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  CalendarDays,
  CreditCard,
  FileClock,
  LayoutDashboard,
  Linkedin,
  LogOut,
  PenLine,
  Search,
  Shield,
  Users,
  WalletCards,
  type LucideIcon
} from "lucide-react";
import { AccountSwitcher } from "@/components/AccountSwitcher/AccountSwitcher";
import { useAuth } from "@/lib/auth-context";
import type { AccountRole } from "@/lib/types";

type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
  roles: AccountRole[];
};

const appNav: NavItem[] = [
  { href: "/dashboard", label: "Owner dashboard", icon: LayoutDashboard, roles: ["Owner"] },
  { href: "/team", label: "Team", icon: Users, roles: ["Owner"] },
  { href: "/billing", label: "Billing", icon: CreditCard, roles: ["Owner"] },
  { href: "/credits", label: "Credits", icon: WalletCards, roles: ["Owner"] },
  { href: "/content-studio", label: "Content studio", icon: PenLine, roles: ["Owner", "TenantAdmin", "Member"] },
  { href: "/calendar", label: "Calendar", icon: CalendarDays, roles: ["Owner", "TenantAdmin", "Member"] },
  { href: "/scraper", label: "Research scraper", icon: Search, roles: ["Owner", "TenantAdmin", "Member"] },
  { href: "/linkedin", label: "LinkedIn", icon: Linkedin, roles: ["Owner", "TenantAdmin", "Member"] }
];

const adminNav: NavItem[] = [
  { href: "/admin/directory", label: "Directory", icon: Search, roles: ["SuperAdmin"] },
  { href: "/admin/sessions", label: "Sessions", icon: Activity, roles: ["SuperAdmin"] },
  { href: "/admin/usage", label: "Global dashboard", icon: WalletCards, roles: ["SuperAdmin"] },
  { href: "/admin/audit-log", label: "Audit log", icon: FileClock, roles: ["SuperAdmin"] }
];

export function AppShell({ children, mode = "app" }: { children: React.ReactNode; mode?: "app" | "admin" }) {
  const pathname = usePathname();
  const router = useRouter();
  const { session, activeAccount, logout } = useAuth();
  const role = session?.role;
  const navItems = (mode === "admin" ? adminNav : appNav).filter((item) => role && item.roles.includes(role));

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <Link className="brand" href={mode === "admin" ? "/admin/directory" : "/content-studio"}>
            <span className="brand-mark">
              <Shield size={18} aria-hidden="true" />
            </span>
            CreditFlow
          </Link>
        </div>
        <nav className="sidebar-nav" aria-label="Primary">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href;
            return (
              <Link key={item.href} href={item.href} className={`nav-item ${isActive ? "active" : ""}`}>
                <Icon size={17} aria-hidden={true} />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="app-main">
        <header className="topbar">
          <AccountSwitcher />
          <div className="status-row">
            {activeAccount ? (
              <span className="status-badge live">{activeAccount.type === "team" ? "Team" : "Individual"}</span>
            ) : (
              <span className="status-badge neutral">Platform</span>
            )}
            {role ? <span className="status-badge neutral">{role}</span> : null}
            <button className="icon-button ghost" type="button" onClick={handleLogout} aria-label="Log out">
              <LogOut size={17} aria-hidden="true" />
            </button>
          </div>
        </header>
        {children}
      </main>
    </div>
  );
}

