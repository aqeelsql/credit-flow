import { ContentStudio } from "@/components/ContentStudio/ContentStudio";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";

export default function ContentStudioPage() {
  return (
    <RouteGuard allowedRoles={["Owner", "TenantAdmin", "Member"]}>
      <ContentStudio />
    </RouteGuard>
  );
}

