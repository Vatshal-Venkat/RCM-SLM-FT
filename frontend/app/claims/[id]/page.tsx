import type { Metadata } from "next";
import { Suspense } from "react";

import { ClaimRoute } from "@/components/claims/ClaimDetailView";
import { Skeleton } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "Claim · RCM Intelligence" };

export default function ClaimPage() {
  return (
    // The claim ID is URL data, read on the client inside this boundary so the shell stays static.
    <Suspense fallback={<Skeleton className="mx-auto h-64 max-w-[1400px] rounded-2xl" />}>
      <ClaimRoute />
    </Suspense>
  );
}
