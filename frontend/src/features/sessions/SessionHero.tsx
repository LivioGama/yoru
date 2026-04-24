import { useCallback, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { SessionHeroView, type SessionDetail } from "@receipt/ui"
import {
  exportSessionTrail,
  getShareConsent,
  postShareConsent,
  postSummary,
  revokeShareSession,
  shareSession,
} from "../../lib/api"
import { toast } from "../../components/Toaster"
import { Modal } from "../../components/ui/Modal"

interface SessionHeroProps {
  session: SessionDetail
}

// Marketing host that serves /s/<id> — mirrors backend env YORU_PUBLIC_URL.
// Kept client-side for display when a session is already public (the backend
// returns `is_public` on SessionDetail but doesn't include a URL on that
// shape; ShareResponse does).
const PUBLIC_SITE =
  (import.meta.env.VITE_PUBLIC_SITE_URL as string | undefined) ?? "https://yoru.sh"

const CONSENT_QUERY_KEY = ["account", "share-consent"] as const

export function SessionHero({ session }: SessionHeroProps) {
  const [exporting, setExporting] = useState(false)
  const [sharing, setSharing] = useState(false)
  const [shareModalOpen, setShareModalOpen] = useState(false)
  const queryClient = useQueryClient()

  // Pull the consent state on mount so we know whether to show the modal
  // when the user clicks "share". Lightweight endpoint — safe to poll on
  // every session page load; react-query dedupes repeats.
  const consentQuery = useQuery({
    queryKey: CONSENT_QUERY_KEY,
    queryFn: getShareConsent,
    staleTime: 60_000, // consent doesn't change often; cache for a minute
  })

  async function onExport() {
    setExporting(true)
    try {
      await exportSessionTrail(session.id)
    } catch (err) {
      toast.error("Couldn't export trail", err instanceof Error ? err.message : String(err))
    } finally {
      setExporting(false)
    }
  }

  // Shared: perform the actual POST /share or /share/revoke. Split from
  // onToggleShare so the modal's accept flow can call it after POSTing
  // consent, without re-opening the modal.
  const commitShare = useCallback(
    async (goingPublic: boolean) => {
      setSharing(true)
      try {
        const res = goingPublic
          ? await shareSession(session.id)
          : await revokeShareSession(session.id)
        if (res.public_url) {
          try {
            await navigator.clipboard.writeText(res.public_url)
            toast.success("Public URL copied to clipboard", res.public_url)
          } catch {
            toast.success("Session is now public", res.public_url)
          }
        } else {
          toast.success("Session is now private", "The public URL no longer resolves.")
        }
        await queryClient.invalidateQueries({ queryKey: ["session", session.id] })
      } catch (err) {
        toast.error(
          goingPublic ? "Couldn't make session public" : "Couldn't revoke share",
          err instanceof Error ? err.message : String(err),
        )
      } finally {
        setSharing(false)
      }
    },
    [session.id, queryClient],
  )

  async function onToggleShare() {
    const currentlyPublic = Boolean(session.is_public)
    // Revoke path — no consent check, always frictionless.
    if (currentlyPublic) {
      await commitShare(false)
      return
    }
    // Share path — consent is server-side now. If the query hasn't loaded
    // yet, treat as "not consented" (the modal is the safer default).
    if (consentQuery.data?.consented) {
      await commitShare(true)
      return
    }
    setShareModalOpen(true)
  }

  async function onModalConfirm() {
    try {
      await postShareConsent()
      // Optimistically update so a second share on the same page load
      // doesn't re-trigger the modal.
      queryClient.setQueryData(CONSENT_QUERY_KEY, {
        consented: true,
        at: new Date().toISOString(),
      })
    } catch (err) {
      toast.error(
        "Couldn't save consent",
        err instanceof Error ? err.message : String(err),
      )
      // Don't proceed with the share — the user explicitly clicked "Make
      // public" but the consent write failed. Closing would be worse UX
      // (they think it worked and the session isn't public). Leave the
      // modal open; they can retry or cancel.
      return
    }
    setShareModalOpen(false)
    await commitShare(true)
  }

  const summaryMutation = useMutation({
    mutationFn: () => postSummary(session.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["session", session.id] })
      queryClient.invalidateQueries({ queryKey: ["session", session.id, "summary"] })
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : String(err)
      toast.error("Couldn't generate summary", msg)
    },
  })

  const publicUrl = session.is_public ? `${PUBLIC_SITE}/s/${session.id}` : null

  return (
    <>
      <SessionHeroView
        session={session}
        onExport={onExport}
        isExporting={exporting}
        onGenerateSummary={() => summaryMutation.mutate()}
        isGeneratingSummary={summaryMutation.isPending}
        onToggleShare={onToggleShare}
        isSharing={sharing}
        publicShareUrl={publicUrl}
      />
      <Modal
        open={shareModalOpen}
        onClose={() => setShareModalOpen(false)}
        title="Share session publicly?"
        size="md"
      >
        <div className="px-5 py-5">
          <h2 className="font-sans text-lg font-semibold text-ink">
            Share this session publicly?
          </h2>
          <p className="mt-2 text-sm text-ink-muted">
            Anyone with the link will see it at{" "}
            <code className="font-mono text-ink">
              {PUBLIC_SITE}/s/{session.id.slice(0, 8)}…
            </code>
          </p>

          <dl className="mt-4 space-y-2 rounded-sm border border-rule bg-sunken/40 p-3 font-mono text-caption">
            <div className="flex items-start gap-2">
              <dt className="shrink-0 w-20 text-ink-faint uppercase">public</dt>
              <dd className="text-ink">
                prompts · tool calls · file paths · red flags · grade
              </dd>
            </div>
            <div className="flex items-start gap-2">
              <dt className="shrink-0 w-20 text-accent-500 uppercase">redacted</dt>
              <dd className="text-ink">
                content of events flagged{" "}
                <code>secret_*</code> (AWS / Stripe / JWT / SSH / Anthropic / DB URL)
              </dd>
            </div>
          </dl>

          <p className="mt-3 text-caption text-ink-muted">
            You&apos;ll only be asked once per account. You can revoke any
            individual share at any time — revocation is immediate and the
            public URL will return 404.
          </p>

          <div className="mt-5 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setShareModalOpen(false)}
              className="rounded-sm border border-rule bg-paper px-4 py-2 font-mono text-caption text-ink-muted hover:bg-sunken hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 focus-visible:ring-offset-surface"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={onModalConfirm}
              disabled={sharing}
              className="rounded-sm bg-accent-500 px-4 py-2 font-mono text-caption text-paper hover:bg-accent-500/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:opacity-60"
            >
              {sharing ? "Making public…" : "Make public"}
            </button>
          </div>
        </div>
      </Modal>
    </>
  )
}
