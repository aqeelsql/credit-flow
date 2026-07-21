import { ScraperResearch } from "@/components/ScraperResearch/ScraperResearch";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";

export default function ScraperPage() {
  return (
    <RouteGuard allowedRoles={["Owner", "TenantAdmin", "Member"]}>
      <ScraperResearch />
    </RouteGuard>
  );
}
