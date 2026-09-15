import { Receipt } from "lucide-react";
import { EmptyState } from "@infinity-radius/ui";

export default function PortalPage() {
  return (
    <main className="mx-auto max-w-4xl px-4 py-10 sm:px-6 lg:px-8">
      <h1 className="text-on-surface text-2xl font-bold">My Account</h1>
      <p className="text-on-surface-variant mt-1 text-sm">Customer self-service portal.</p>

      <div className="mt-8">
        <EmptyState
          icon={<Receipt size={28} />}
          title="No transactions yet"
          description="Your subscription, sessions, and payment history will appear here."
        />
      </div>
    </main>
  );
}
