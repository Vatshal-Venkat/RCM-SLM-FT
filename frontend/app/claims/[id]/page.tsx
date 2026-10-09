import type { Metadata } from "next";
import { Suspense } from "react";

import { ClaimDetailView } from "@/components/claims/ClaimDetailView";
import { Skeleton } from "@/components/ui/primitives";

export const metadata: Metadata = { title: "Claim · RCM Intelligence" };

// Not async: params are runtime data under Cache Components, so they are awaited inside the
// Suspense boundary and the rest of the page stays in the static shell.
export default function ClaimPage(props: PageProps<"/claims/[id]">) {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-64 max-w-[1400px] rounded-2xl" />}>
      <ClaimFromParams params={props.params} />
    </Suspense>
  );
}

async function ClaimFromParams({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ClaimDetailView claimId={decodeURIComponent(id)} />;
}
