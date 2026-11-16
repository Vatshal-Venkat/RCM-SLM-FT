import type { Metadata } from "next";

import { BookingForm } from "@/components/journey/BookingForm";

export const metadata: Metadata = { title: "Book a visit · RCM Intelligence" };

export default function BookPage() {
  return <BookingForm />;
}
