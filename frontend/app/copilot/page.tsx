import type { Metadata } from "next";
import { Suspense } from "react";

import { CopilotChat } from "@/components/chat/CopilotChat";
import { Skeleton } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "AI Copilot · RCM Intelligence" };

export default function CopilotPage() {
  return (
    <div className="mx-auto max-w-[1400px]">
      {/* CopilotChat reads ?q= (useSearchParams), so it renders client-side inside this boundary.
          It fills the viewport and carries its own header. */}
      <Suspense fallback={<Skeleton className="h-[calc(100dvh-57px-3rem)] min-h-[520px] rounded-2xl lg:h-[calc(100dvh-4rem)]" />}>
        <CopilotChat />
      </Suspense>
    </div>
  );
}
