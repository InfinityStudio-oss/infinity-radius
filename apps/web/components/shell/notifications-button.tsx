import { Bell } from "lucide-react";

/** No badge/count here on purpose — there is no notifications backend yet, so nothing to report. */
export function NotificationsButton() {
  return (
    <button
      type="button"
      aria-label="Notifications"
      className="text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface rounded-lg p-2 transition-colors"
    >
      <Bell size={20} />
    </button>
  );
}
