import { useCallback, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { SessionHeroView, type SessionDetail } from "@receipt/ui"
import {
  exportSessionTrail,
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

// localStorage flag: first-time share confirm (#79 AC — one-time warning).
// Cleared by the user via devtools if they want to re-see the warning.
const SHARE_CONFIRM_KEY = "yoru.share.confirmed"

export function SessionHero({ session }: SessionHeroProps) {
  const [exporting, setExporting] = useState(false)
  const [sharing, setSharing] = useState(false)
  const [shareModalOpen, setShareModalOpen] = useState(false)
  const queryClient = useQueryClient()

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

  // Shared logic: actually call the share/revoke API. Split from the click
  // handler so the modal's "accept" can call this without re-opening itself.
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

  // Top-level click: branch on current state + consent flag. Revoke is
  // frictionless (de-risking action); share asks for consent the first time.
  async function onToggleShare() {
    const currentlyPublic = Boolean(session.is_public)
    if (currentlyPublic) {
      await commitShare(false)
      return
    }
    const alreadyConfirmed =
      typeof window !== "undefined" &&
      window.localStorage?.getItem(SHARE_CONFIRM_KEY) === "1"
    if (alreadyConfirmed) {
      await commitShare(true)
      return
    }
    setShareModalOpen(true)
  }

  async function onModalConfirm() {
    try {
      window.localStorage?.setItem(SHARE_CONFIRM_KEY, "1")
    } catch {
      // quota / privacy-mode — no-op. Worst case user sees the modal again.
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
            You can revoke at any time from this same button. Revocation is
            immediate — the public URL will return 404.
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
