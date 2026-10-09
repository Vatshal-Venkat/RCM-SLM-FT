import type { Metadata } from "next";
import { Suspense } from "react";

import { CopilotChat } from "@/components/chat/CopilotChat";
import { PageHeader, Skeleton } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "AI Copilot · RCM Intelligence" };

export default function CopilotPage() {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        eyebrow="AI Copilot"
        title="Ask about your revenue cycle"
        description="Answers combine your claims data, the validated RCM knowledge base and the fine-tuned SLM. Sources and validation checks are shown with every answer."
      />
      {/* CopilotChat reads ?q= (useSearchParams), so it renders client-side inside this boundary. */}
      <Suspense fallback={<Skeleton className="h-[calc(100vh-13rem)] min-h-[520px] rounded-2xl" />}>
        <CopilotChat />
      </Suspense>
    </div>
  );
}
