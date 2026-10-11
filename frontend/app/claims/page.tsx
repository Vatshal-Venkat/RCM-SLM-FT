import type { Metadata } from "next";
import { Suspense } from "react";

import { ClaimsExplorer } from "@/components/claims/ClaimsExplorer";
import { Skeleton } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "Claims · RCM Intelligence" };

export default function ClaimsPage() {
  return (
    // ClaimsExplorer reads its initial filters from the URL (useSearchParams).
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-[1400px] rounded-2xl" />}>
      <ClaimsExplorer />
    </Suspense>
  );
}
