import { useEffect, useState } from "react"
import { TimelineEvent } from "./TimelineEvent"
import type { SessionEvent } from "./types"

// TSU-55 follow-up — the live session-replay step-through, in the AUTHED
// dashboard (the share-pivot keeps the live player owner-side; the public
// viewer is dormant). NOT a video/DOM replay: the scrubber indexes EVENTS, so
// the idle gaps between an agent's steps collapse for free — an overnight run
// of hours steps through in seconds. Step state is internal (no URL coupling),
// so it drops into any authed page without router assumptions.

const CTL_BTN =
  "rounded-sm border border-rule px-3 py-1.5 font-mono text-caption text-ink " +
  "hover:bg-sunken disabled:opacity-40 disabled:hover:bg-transparent " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-surface"

interface SessionReplayProps {
  events: SessionEvent[]
  /** Autoplay cadence per step (ms). Event-indexed, so this is constant
   *  regardless of wall-clock gaps. */
  stepMs?: number
}

export function SessionReplay({ events, stepMs = 1100 }: SessionReplayProps) {
  const total = events.length
  const clamp = (i: number) => Math.min(Math.max(0, i), Math.max(0, total - 1))
  const [step, setStep] = useState(0)
  const [playing, setPlaying] = useState(false)

  const go = (i: number) => setStep(clamp(i))

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") go(step - 1)
      else if (e.key === "ArrowRight") go(step + 1)
      else if (e.key === " ") setPlaying((p) => !p)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, total])

  // Autoplay: advance one step per tick (event index, not wall-clock). Stops
  // at the end so it never loops past the final state.
  useEffect(() => {
    if (!playing) return
    if (step >= total - 1) {
      setPlaying(false)
      return
    }
    const t = window.setTimeout(() => go(step + 1), stepMs)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, step, total, stepMs])

  if (total === 0) return null
  const ev = events[clamp(step)]

  return (
    <section className="rounded-sm border border-rule bg-surface" aria-label="Session replay">
      <header className="flex items-center justify-between border-b border-dashed border-rule px-4 py-2">
        <span className="font-mono text-caption uppercase tracking-wider text-ink-faint">
          § Replay
        </span>
        <span className="font-mono text-caption tabular-nums text-ink-muted">
          step {step + 1} / {total}
        </span>
      </header>
      <div className="px-4 py-3">
        <TimelineEvent event={ev} expanded />
      </div>
      <div className="flex items-center gap-3 border-t border-dashed border-rule px-4 py-3">
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          disabled={step === total - 1 && !playing}
          aria-label={playing ? "Pause replay" : "Play replay"}
          className={CTL_BTN}
        >
          {playing ? "❚❚ Pause" : "▶ Play"}
        </button>
        <button type="button" onClick={() => go(step - 1)} disabled={step === 0} className={CTL_BTN}>
          ◀ Prev
        </button>
        <div className="relative flex-1">
          {/* Red-flag markers — the "trust strip": pins where the agent tripped
              a red flag. Click to jump to that moment. */}
          <div className="pointer-events-none absolute inset-x-0 -top-2 h-2">
            {events.map((e, i) =>
              e.flag ? (
                <button
                  key={i}
                  type="button"
                  onClick={() => go(i)}
                  title={`${e.flag} — jump to step ${i + 1}`}
                  aria-label={`Red flag ${e.flag} at step ${i + 1}`}
                  style={{
                    left: `${total > 1 ? (i / (total - 1)) * 100 : 0}%`,
                    background: "rgb(239 68 68)",
                  }}
                  className="pointer-events-auto absolute top-0 -ml-1 h-2 w-2 rounded-full ring-1 ring-paper"
                />
              ) : null,
            )}
          </div>
          <input
            type="range"
            min={0}
            max={total - 1}
            value={step}
            onChange={(e) => go(Number(e.target.value))}
            aria-label="Replay position"
            className="h-1.5 w-full cursor-pointer accent-accent-500"
          />
        </div>
        <button
          type="button"
          onClick={() => go(step + 1)}
          disabled={step === total - 1}
          className={CTL_BTN}
        >
          Next ▶
        </button>
      </div>
    </section>
  )
}
