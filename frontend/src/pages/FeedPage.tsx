import { useEffect, useRef } from "react"
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query"
import { listSessions } from "../lib/api"
import { useFilters } from "../features/sessions/filters"
import { FilterBar } from "../features/sessions/FilterBar"
import { FeedCard } from "../features/sessions/FeedCard"
import { EmptySessionsState } from "../features/sessions/EmptySessionsState"
import { Skeleton } from "../components/ui/Skeleton"
import type { SessionList } from "../types/receipt"

const PAGE = 20

// Group-scoped reverse-chron feed (TSU-249). Reuses GET /sessions, which the
// backend already scopes to own + group-mates (visible_emails_sync; admin all;
// cross-group wall) and orders started_at DESC — so this is purely a denser,
// paginated presentation of what the caller is already entitled to see.
export function FeedPage() {
  const filters = useFilters()
  const queryClient = useQueryClient()

  const query = useInfiniteQuery<SessionList>({
    queryKey: ["feed", filters],
    queryFn: ({ pageParam }) =>
      listSessions({ ...filters, limit: PAGE, offset: pageParam as number }),
    initialPageParam: 0,
    getNextPageParam: (_last, pages) => {
      const loaded = pages.reduce((n, p) => n + p.items.length, 0)
      const total = pages[0]?.total ?? 0
      return loaded < total ? loaded : undefined
    },
  })

  const items = query.data?.pages.flatMap((p) => p.items) ?? []

  // Infinite scroll: fetch the next page when a sentinel near the end scrolls
  // into view.
  const sentinel = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = sentinel.current
    if (!el) return
    const io = new IntersectionObserver((entries) => {
      if (
        entries[0]?.isIntersecting &&
        query.hasNextPage &&
        !query.isFetchingNextPage
      ) {
        query.fetchNextPage()
      }
    })
    io.observe(el)
    return () => io.disconnect()
  }, [query.hasNextPage, query.isFetchingNextPage, query.fetchNextPage])

  return (
    <div className="space-y-4">
      <header className="border-b border-dashed border-rule pb-4">
        <h1 className="font-mono text-2xl font-semibold text-ink">Feed</h1>
        <p className="mt-1 font-mono text-caption text-ink-muted">
          Sessions you and your group ran — newest first.
        </p>
      </header>

      <FilterBar />

      {query.isPending ? (
        <div role="status" aria-label="Loading feed" className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton.Card key={i} decorative />
          ))}
        </div>
      ) : query.isError ? (
        <ErrorBanner
          message={
            query.error instanceof Error
              ? query.error.message
              : "Failed to load the feed."
          }
          onRetry={() =>
            queryClient.invalidateQueries({ queryKey: ["feed"] })
          }
        />
      ) : items.length === 0 ? (
        <EmptySessionsState />
      ) : (
        <>
          <ul className="space-y-2">
            {items.map((s) => (
              <li key={s.id}>
                <FeedCard session={s} />
              </li>
            ))}
          </ul>
          <div ref={sentinel} aria-hidden className="h-8" />
          {query.isFetchingNextPage && (
            <div role="status" aria-label="Loading more" className="space-y-2">
              <Skeleton.Card decorative />
            </div>
          )}
          {!query.hasNextPage && (
            <p className="py-4 text-center font-mono text-micro text-ink-faint">
              — end of feed —
            </p>
          )}
        </>
      )}
    </div>
  )
}

function ErrorBanner({
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <div
      role="alert"
      className="rounded-sm border border-rule border-l-2 border-l-flag-env bg-surface p-4"
    >
      <p className="font-mono text-caption text-ink">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-2 rounded-sm border border-rule px-3 py-1 font-mono text-micro text-ink hover:bg-sunken"
      >
        Retry
      </button>
    </div>
  )
}
