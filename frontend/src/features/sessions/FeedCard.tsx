import { memo } from "react"
import { Link } from "react-router-dom"
import type { Session } from "../../types/receipt"
import { formatCost, formatRelative } from "../../lib/format"
import { RedFlagBadge } from "./RedFlagBadge"

// Grade → chip colour. Semantic: green = A, accent = B/C, amber = D, red = F.
// Unknown/ungraded falls back to a muted neutral.
const GRADE_CLS: Record<string, string> = {
  A: "bg-emerald-500/15 text-emerald-400 ring-emerald-500/30",
  B: "bg-accent-500/15 text-accent-500 ring-accent-500/30",
  C: "bg-accent-500/15 text-accent-500 ring-accent-500/30",
  D: "bg-amber-500/15 text-amber-400 ring-amber-500/30",
  F: "bg-red-500/15 text-red-400 ring-red-500/30",
}

// Archetype = the SAME honest clean/flagged signal the og:image uses (TSU-54):
// 0 flags over real tool calls → clean; any flag → flagged; no signal → none.
// Functional label only; persona naming is content-lead's call.
function archetype(s: Session): "CLEAN RUN" | "FLAGGED RUN" | null {
  if (s.flag_count > 0) return "FLAGGED RUN"
  if (s.tool_count > 0) return "CLEAN RUN"
  return null
}

function FeedCardImpl({ session }: { session: Session }) {
  const running = session.ended_at === null
  const grade = session.grade ?? null
  const arch = archetype(session)
  // Dedup flags so a session that trips one kind many times shows one badge.
  const flagKinds = Array.from(new Set(session.flags))

  return (
    <Link
      to={`/s/${session.id}`}
      aria-label={`Session by ${session.user_email}, grade ${grade ?? "ungraded"}, ${formatRelative(session.started_at)}`}
      className={
        "flex gap-4 rounded-sm border border-rule bg-surface p-4 hover:bg-sunken " +
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 " +
        "focus-visible:ring-offset-2 focus-visible:ring-offset-paper"
      }
    >
      {/* Verdict-first: the grade leads, big. */}
      <div
        className={
          "flex h-12 w-12 shrink-0 items-center justify-center rounded-sm font-mono text-xl " +
          "font-bold tabular-nums ring-1 " +
          (grade ? GRADE_CLS[grade] ?? "bg-sunken text-ink-muted ring-rule" : "bg-sunken text-ink-faint ring-rule")
        }
        title={grade ? `Grade ${grade}` : "Not yet graded"}
        aria-hidden
      >
        {grade ?? "—"}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-baseline gap-2">
          <span className="truncate font-sans text-caption text-ink" title={session.title ?? undefined}>
            {session.title ?? session.user_email}
          </span>
          {arch && (
            <span className="shrink-0 font-mono text-micro uppercase tracking-wider text-ink-faint">
              {arch}
            </span>
          )}
        </div>

        <div className="mt-0.5 truncate font-mono text-micro text-ink-faint">
          {session.user_email}
          <span className="mx-1.5 text-rule">·</span>
          <span title={session.started_at}>{formatRelative(session.started_at)}</span>
          {running && <span className="ml-1.5 italic text-accent-500">running…</span>}
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-micro tabular-nums text-ink-muted">
          <span>{session.tool_count} tools</span>
          <span>{session.flag_count} flags</span>
          <span>{session.cost_usd ? formatCost(session.cost_usd) : "$0"}</span>
          {flagKinds.length > 0 && (
            <span className="flex flex-wrap items-center gap-1">
              {flagKinds.map((k) => (
                <RedFlagBadge key={k} kind={k} />
              ))}
            </span>
          )}
        </div>
      </div>
    </Link>
  )
}

export const FeedCard = memo(FeedCardImpl)
