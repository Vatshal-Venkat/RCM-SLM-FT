import type { Metadata } from "next";
import { Suspense } from "react";

import { EncounterRoute } from "@/components/journey/EncounterWorkspace";
import { Skeleton } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "Patient journey · RCM Intelligence" };

export default function EncounterPage() {
  return (
    // The encounter ID is URL data, read on the client inside this boundary so the shell stays static.
    <Suspense fallback={<Skeleton className="mx-auto h-64 max-w-[1400px] rounded-2xl" />}>
      <EncounterRoute />
    </Suspense>
  );
}
