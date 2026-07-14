import { AppShell } from "@/components/AppShell/AppShell";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <RouteGuard allowedRoles={["Owner", "TenantAdmin", "Member"]}>
      <AppShell>{children}</AppShell>
    </RouteGuard>
  );
}

