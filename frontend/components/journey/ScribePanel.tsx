"use client";

import clsx from "clsx";
import { ClipboardPaste, FileAudio, Mic, MicOff, Sparkles, Stethoscope, Trash2, User } from "lucide-react";
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { Btn, Section } from "@/components/journey/shared";
import type { SampleVisit, Speaker, Utterance } from "@/types/journey";

// Minimal Web Speech API typings (not in TypeScript's DOM lib).
interface SpeechAlternative { transcript: string }
interface SpeechResult { isFinal: boolean; 0: SpeechAlternative; length: number }
interface SpeechEvent { resultIndex: number; results: { length: number; [i: number]: SpeechResult } }
interface Recognition {
  lang: string; continuous: boolean; interimResults: boolean;
  onresult: ((e: SpeechEvent) => void) | null; onerror: ((e: { error: string }) => void) | null; onend: (() => void) | null;
  start(): void; stop(): void;
}
type RecognitionCtor = new () => Recognition;

function getRecognition(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

const noopSubscribe = () => () => {};

/** "Doctor: ..." / "Patient: ..." lines -> utterances (unlabelled lines continue the last speaker). */
export function parseTranscript(raw: string): Utterance[] {
  const out: Utterance[] = [];
  for (const line of raw.split(/\r?\n/)) {
    const t = line.trim();
    if (!t) continue;
    const m = t.match(/^(doctor|dr\.?|physician|nurse|d|patient|pt\.?|p)\s*[:\-]\s*(.*)$/i);
    if (m) {
      const who = m[1].toLowerCase().replace(".", "");
      const speaker: Speaker = ["doctor", "dr", "physician", "nurse", "d"].includes(who) ? "doctor" : "patient";
      if (m[2].trim()) out.push({ speaker, text: m[2].trim() });
    } else if (out.length) {
      out[out.length - 1] = { ...out[out.length - 1], text: `${out[out.length - 1].text} ${t}` };
    } else {
      out.push({ speaker: "unknown", text: t });
    }
  }
  return out;
}

export function ScribePanel({ initial, samples, visitReason, onSave, onFinish, busy }: {
  initial: Utterance[];
  samples: SampleVisit[];
  visitReason: string;
  onSave: (u: Utterance[]) => Promise<void>;
  onFinish: (u: Utterance[]) => Promise<void>;
  busy: boolean;
}) {
  const [utts, setUtts] = useState<Utterance[]>(initial);
  const [speaker, setSpeaker] = useState<Speaker>("doctor");
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [typed, setTyped] = useState("");
  const [paste, setPaste] = useState<string | null>(null);
  const [micError, setMicError] = useState<string | null>(null);
  const recRef = useRef<Recognition | null>(null);
  const speakerRef = useRef<Speaker>("doctor");
  const listRef = useRef<HTMLDivElement | null>(null);
  // Server render assumes no speech API; the client snapshot reads the real browser capability.
  const supported = useSyncExternalStore(noopSubscribe, () => getRecognition() !== null, () => false);

  useEffect(() => { speakerRef.current = speaker; }, [speaker]);
  useEffect(() => { listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" }); }, [utts, interim]);
  useEffect(() => () => recRef.current?.stop(), []);

  const add = useCallback((who: Speaker, text: string) => {
    const t = text.trim();
    if (!t) return;
    setUtts((prev) => {
      const last = prev[prev.length - 1];
      // Consecutive phrases from the same speaker join one utterance.
      if (last && last.speaker === who) return [...prev.slice(0, -1), { speaker: who, text: `${last.text} ${t}` }];
      return [...prev, { speaker: who, text: t.charAt(0).toUpperCase() + t.slice(1) }];
    });
  }, []);

  const start = () => {
    const Ctor = getRecognition();
    if (!Ctor) return;
    setMicError(null);
    const rec = new Ctor();
    rec.lang = "en-US";
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (e) => {
      let live = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) {
          const text = r[0].transcript.trim();
          add(speakerRef.current, /[.?!]$/.test(text) ? text : `${text}.`);
        } else live += r[0].transcript;
      }
      setInterim(live);
    };
    rec.onerror = (e) => {
      if (e.error !== "no-speech") setMicError(e.error === "not-allowed" ? "Microphone permission was denied." : `Speech recognition error: ${e.error}`);
    };
    rec.onend = () => {
      // Chrome ends continuous sessions after silence; restart while the user still wants to listen.
      if (recRef.current === rec) {
        try { rec.start(); } catch { setListening(false); }
      }
    };
    recRef.current = rec;
    rec.start();
    setListening(true);
  };

  const stop = () => {
    const rec = recRef.current;
    recRef.current = null;
    rec?.stop();
    setListening(false);
    setInterim("");
  };

  const loadSample = (id: string) => {
    const s = samples.find((x) => x.id === id);
    if (s) setUtts(s.transcript);
  };

  const suggested = samples.find((s) => s.visit_reason.toLowerCase() === visitReason.toLowerCase());

  return (
    <Section id="consultation" step="Step 6 · Doctor consultation" title="AI scribe"
      subtitle="Listens to the conversation so the doctor can focus on the patient. The note, codes and coverage are drafted the moment the visit ends."
      right={<div className="flex items-center gap-2">
        <select aria-label="Load a sample conversation" className="rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-xs text-ink-2"
          value="" onChange={(e) => loadSample(e.target.value)}>
          <option value="">Load sample conversation…</option>
          {samples.map((s) => <option key={s.id} value={s.id}>{s.title}{s.id === suggested?.id ? " (matches visit)" : ""}</option>)}
        </select>
        <Btn variant="ghost" onClick={() => setPaste(paste === null ? "" : null)}><ClipboardPaste className="h-3.5 w-3.5" /> Paste</Btn>
      </div>}>

      {/* Recorder controls */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-white/[0.02] p-3">
        {supported ? (
          listening ? (
            <Btn variant="danger" onClick={stop}><MicOff className="h-3.5 w-3.5" /> Stop listening</Btn>
          ) : (
            <Btn variant="primary" onClick={start}><Mic className="h-3.5 w-3.5" /> Start listening</Btn>
          )
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs text-ink-3"><FileAudio className="h-3.5 w-3.5" />
            Live speech-to-text needs Chrome or Edge. Type, paste or load a sample instead.</span>
        )}
        <div className="flex items-center gap-1 rounded-lg bg-white/[0.04] p-0.5" role="radiogroup" aria-label="Who is speaking">
          {(["doctor", "patient"] as const).map((s) => (
            <button key={s} role="radio" aria-checked={speaker === s} onClick={() => setSpeaker(s)}
              className={clsx("inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs capitalize",
                speaker === s ? (s === "doctor" ? "bg-violet-500/20 text-violet-200" : "bg-sky-500/20 text-sky-200") : "text-ink-3 hover:text-ink")}>
              {s === "doctor" ? <Stethoscope className="h-3 w-3" /> : <User className="h-3 w-3" />} {s} speaking
            </button>
          ))}
        </div>
        {listening && (
          <span className="inline-flex items-center gap-1.5 text-xs text-critical">
            <span className="h-2 w-2 animate-pulse rounded-full bg-critical" aria-hidden /> Recording
          </span>
        )}
        {micError && <span className="text-xs text-critical">{micError}</span>}
      </div>
      {supported && (
        <p className="mt-1.5 text-[11px] text-ink-3">
          Switch the speaker toggle as the conversation changes hands. Browser speech recognition may send audio to the browser vendor&rsquo;s
          service; use it only with consented, de-identified demo conversations.
        </p>
      )}

      {paste !== null && (
        <div className="mt-3 space-y-2">
          <textarea value={paste} onChange={(e) => setPaste(e.target.value)} rows={6}
            placeholder={"Doctor: What brings you in today?\nPatient: I've had a sore throat for three days."}
            className="w-full rounded-xl border border-line bg-surface-2 p-3 font-mono text-xs text-ink placeholder:text-ink-3" />
          <div className="flex gap-2">
            <Btn variant="primary" disabled={!paste.trim()} onClick={() => { setUtts(parseTranscript(paste)); setPaste(null); }}>Use transcript</Btn>
            <Btn variant="ghost" onClick={() => setPaste(null)}>Cancel</Btn>
          </div>
        </div>
      )}

      {/* Transcript */}
      <div ref={listRef} className="mt-3 max-h-[420px] min-h-[160px] space-y-2 overflow-y-auto rounded-xl border border-line bg-black/20 p-3" aria-live="polite">
        {utts.length === 0 && !interim && (
          <p className="py-10 text-center text-xs text-ink-3">
            The conversation appears here as it is spoken.{suggested ? ` Tip: load "${suggested.title}" to see a full visit.` : ""}
          </p>
        )}
        {utts.map((u, i) => (
          <div key={i} className={clsx("group flex gap-2", u.speaker === "patient" && "flex-row-reverse")}>
            <div className={clsx("max-w-[85%] rounded-xl px-3 py-2 text-sm",
              u.speaker === "doctor" ? "bg-violet-500/10 text-ink ring-1 ring-inset ring-violet-400/20"
                : u.speaker === "patient" ? "bg-sky-500/10 text-ink ring-1 ring-inset ring-sky-400/20" : "bg-white/5 text-ink")}>
              <p className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-3">{u.speaker}</p>
              {u.text}
            </div>
            <button aria-label="Remove this line" onClick={() => setUtts(utts.filter((_, j) => j !== i))}
              className="self-center rounded p-1 text-ink-3 opacity-0 hover:text-critical group-hover:opacity-100 focus:opacity-100">
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
        {interim && <p className="text-sm italic text-ink-3">{speaker}: {interim}…</p>}
      </div>

      <form className="mt-3 flex gap-2" onSubmit={(e) => { e.preventDefault(); add(speaker, typed); setTyped(""); }}>
        <input value={typed} onChange={(e) => setTyped(e.target.value)} maxLength={2000}
          placeholder={`Type what the ${speaker} said and press Enter`}
          className="min-w-0 flex-1 rounded-lg border border-line bg-surface-2 px-3 py-1.5 text-sm text-ink placeholder:text-ink-3" />
        <Btn type="submit" disabled={!typed.trim()}>Add</Btn>
      </form>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <p className="text-xs text-ink-3">{utts.length} utterance{utts.length === 1 ? "" : "s"} captured</p>
        <div className="flex gap-2">
          <Btn disabled={!utts.length || busy} onClick={() => onSave(utts)}>Save draft</Btn>
          <Btn variant="primary" busy={busy} disabled={!utts.length} onClick={() => { stop(); void onFinish(utts); }}>
            <Sparkles className="h-3.5 w-3.5" /> End visit: draft note, codes &amp; coverage
          </Btn>
        </div>
      </div>
    </Section>
  );
}
