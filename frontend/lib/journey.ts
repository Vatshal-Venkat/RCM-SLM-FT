// Helpers for the patient-journey screens.

import { apiGet, apiPost, toQuery } from "@/lib/api";
import type { EncounterDetail, JourneyOptions, SampleVisit, Slots } from "@/types/journey";

const DEMO_NAMES = ["Ana Diaz", "Marcus Lee", "Priya Shah", "John Carter", "Mei Tanaka", "Sofia Rossi", "David Okoye", "Emma Novak", "Liam Byrne", "Nora Haddad"];

export function isoDay(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function nextBusinessDay(from = new Date()): string {
  const d = new Date(from);
  d.setDate(d.getDate() + 1);
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1);
  return isoDay(d);
}

/** Book a sample visit in the doctor's first free slot over the next two weeks. */
export async function bookSample(sample: SampleVisit, opts: JourneyOptions): Promise<EncounterDetail> {
  const plan = opts.plans.find((p) => p.payer_id === sample.payer_id)!;
  const d = new Date();
  for (let i = 0; i < 14; i++) {
    d.setDate(d.getDate() + 1);
    if (d.getDay() === 0 || d.getDay() === 6) continue;
    const day = isoDay(d);
    const slots = await apiGet<Slots>(`/api/encounters/slots${toQuery({ doctor_id: sample.doctor_id, day })}`);
    const free = slots.slots.find((s) => s.available);
    if (!free) continue;
    return apiPost<EncounterDetail>("/api/encounters", {
      patient_name: DEMO_NAMES[Math.floor(Math.random() * DEMO_NAMES.length)],
      birth_year: sample.birth_year, sex: sample.sex, state: "OH", payer_id: sample.payer_id,
      member_id: plan.member_id_example, doctor_id: sample.doctor_id, scheduled_at: `${day}T${free.time}:00`,
      visit_reason: sample.visit_reason, new_patient: sample.new_patient,
    });
  }
  throw new Error("No free appointment slots in the next two weeks");
}
