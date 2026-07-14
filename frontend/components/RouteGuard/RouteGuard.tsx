"use client";

import { useMemo } from "react";
import { useRequireAuth } from "@/lib/auth-context";
import type { AccountRole } from "@/lib/types";

const USE_LOCAL_AUTH = process.env.NEXT_PUBLIC_USE_LOCAL_AUTH !== "false";

type RouteGuardProps = {
  allowedRoles: AccountRole[];
  requireAccount?: boolean;
  children: React.ReactNode;
};

export function RouteGuard({ allowedRoles, requireAccount = true, children }: RouteGuardProps) {
  const roles = useMemo(() => allowedRoles, [allowedRoles]);
  const { status, isAllowed } = useRequireAuth(roles, requireAccount);

  if (USE_LOCAL_AUTH && status === "loading") {
    return <>{children}</>;
  }

  if (status === "loading" || !isAllowed) {
    return <div className="auth-loading">Checking access...</div>;
  }

  return <>{children}</>;
}
