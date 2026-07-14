import { AppShell } from "@/components/AppShell/AppShell";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <RouteGuard allowedRoles={["SuperAdmin"]} requireAccount={false}>
      <AppShell mode="admin">{children}</AppShell>
    </RouteGuard>
  );
}
