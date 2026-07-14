import { SchedulerCalendar } from "@/components/Calendar/SchedulerCalendar";
import { RouteGuard } from "@/components/RouteGuard/RouteGuard";

export default function CalendarPage() {
  return (
    <RouteGuard allowedRoles={["Owner", "TenantAdmin", "Member"]}>
      <SchedulerCalendar />
    </RouteGuard>
  );
}

