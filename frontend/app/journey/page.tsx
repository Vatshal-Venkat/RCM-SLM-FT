import type { Metadata } from "next";

import { JourneyList } from "@/components/journey/JourneyList";

export const metadata: Metadata = { title: "Patient journeys · RCM Intelligence" };

export default function JourneyPage() {
  return <JourneyList />;
}
