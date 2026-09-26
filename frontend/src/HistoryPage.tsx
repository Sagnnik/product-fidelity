import { useEffect, useState } from 'react'
import { SignInButton, UserButton, useAuth } from '@clerk/react'
import AuthenticatedImage from './AuthenticatedImage'
import { api } from './authApi'

type CampaignSummary = {
  id: string; product: string; status: string; created_at: string
  preview_file: string | null
}

type Metrics = {
  campaigns_completed: number; images_generated: number; images_reviewed: number
  images_approved: number; approval_rate: number | null
  product_detail_error_rate: number | null
  mean_generation_seconds: number | null; mean_time_to_first_preview_seconds: number | null
  estimated_cost_per_approved_usd: number | null; note: string
}

const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 })
const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
const date = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium' })

function statusLabel(status: string) {
  if (status === 'completed') return 'Ready to review'
  if (status === 'failed' || status === 'interrupted') return 'Needs attention'
  return 'Creating images'
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div className="border-t border-line pt-4">
      <p className="text-[11px] font-bold tracking-[.12em] text-ink-soft uppercase">{label}</p>
      <p className="mt-2 font-display text-[32px] leading-tight text-ink tabular-nums">{value}</p>
      <p className="mt-1 text-xs leading-5 text-ink-soft">{detail}</p>
    </div>
  )
}

export default function HistoryPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([])
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [metricsLoading, setMetricsLoading] = useState(false)
  const [error, setError] = useState('')
  const [metricsError, setMetricsError] = useState('')

  useEffect(() => {
    if (!isSignedIn) { setLoading(false); return }
    setLoading(true)
    api<CampaignSummary[]>(getToken, '/api/campaigns')
      .then((items) => { setCampaigns(items); setError('') })
      .catch((failure: Error) => setError(failure.message))
      .finally(() => setLoading(false))
  }, [getToken, isSignedIn])

  function loadMetrics() {
    if (metrics || metricsLoading || !isSignedIn) return
    setMetricsLoading(true)
    api<Metrics>(getToken, '/api/metrics')
      .then((result) => { setMetrics(result); setMetricsError('') })
      .catch((failure: Error) => setMetricsError(failure.message))
      .finally(() => setMetricsLoading(false))
  }

  return (
    <div className="site-shell min-h-screen">
      <a href="#main" className="sr-only rounded bg-ink px-4 py-2 text-white focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50">Skip to main content</a>
      <header className="border-b border-white/10 bg-[#172331]/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-5 py-4 sm:px-10 lg:px-14">
          <a href="/" className="flex items-center gap-2.5 text-[#fff3f1] hover:text-white" aria-label="Stillroom home">
            <span className="grid h-8 w-8 place-items-center rounded-[9px] bg-orange text-lg font-bold text-white">✳</span>
            <span className="font-display text-[27px] font-semibold tracking-[-.04em]">stillroom<span className="text-orange">.</span></span>
          </a>
          <nav aria-label="Main navigation" className="flex items-center gap-4 text-[11px] font-bold tracking-[.12em] text-[#e9ccd5] uppercase sm:gap-7">
            <a href="/create" className="hover:text-white">Create</a>
            <span aria-current="page" className="text-white">History</span>
            {isSignedIn ? <UserButton /> : null}
            {isLoaded && !isSignedIn ? <SignInButton mode="modal"><button type="button" className="rounded-full border border-[#f2b5c7]/55 px-4 py-2 text-[11px] font-bold tracking-[.08em] text-[#fff4f1] uppercase transition-colors hover:border-[#f2b5c7] hover:bg-white/10">Log in</button></SignInButton> : null}
          </nav>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-[1440px] px-5 pb-24 pt-10 sm:px-10 lg:px-14 lg:pt-16">
        <div className="flex flex-wrap items-end justify-between gap-6 border-b border-white/20 pb-8 text-[#fff4f1]">
          <div>
            <p className="text-[11px] font-bold tracking-[.18em] text-[#f0a6bb] uppercase">Your creative library</p>
            <h1 className="mt-3 font-display text-[clamp(3rem,6vw,5.8rem)] leading-[1.02] tracking-[-.05em]">Campaign history.</h1>
            <p className="mt-4 max-w-[520px] text-sm leading-7 text-[#e1d1d8]">Revisit your images, continue reviewing, and export the directions you want to keep.</p>
          </div>
          <a href="/create" className="rounded-full bg-orange px-5 py-3 text-sm font-bold text-white transition-colors duration-150 hover:bg-[#8e3d5d]">Create a campaign ↗</a>
        </div>

        {!isLoaded || loading && isSignedIn ? <p role="status" className="py-16 text-sm text-[#e1d1d8]">Loading your campaigns…</p> : null}

        {isLoaded && !isSignedIn ? (
          <div className="mt-10 max-w-xl rounded-[24px] border border-line bg-[#fff8f7] p-7 sm:p-10">
            <h2 className="font-display text-3xl">Your history is private.</h2>
            <p className="mt-3 text-sm leading-7 text-ink-soft">Sign in to see campaigns created with your account.</p>
            <SignInButton mode="modal"><button type="button" className="mt-6 rounded-full bg-orange px-5 py-3 text-sm font-bold text-white hover:bg-[#8e3d5d]">Sign in or create an account ↗</button></SignInButton>
          </div>
        ) : null}

        {isSignedIn && !loading ? (
          <>
            {error ? <p role="alert" className="mt-8 rounded-xl bg-[#fae4da] px-4 py-3 text-sm text-[#8d3e2d]">{error}</p> : null}
            {!error && campaigns.length === 0 ? (
              <div className="mt-10 rounded-[24px] border border-dashed border-line bg-[#fff8f7] px-6 py-20 text-center">
                <p className="font-display text-3xl">Your first images will appear here.</p>
                <p className="mt-3 text-sm text-ink-soft">Create a campaign to start your library.</p>
              </div>
            ) : null}
            <div className="mt-9 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {campaigns.map((item) => (
                <a key={item.id} href={`/create?run=${item.id}#campaign-results`} className="group overflow-hidden rounded-[22px] border border-line bg-[#fff8f7] shadow-[0_12px_30px_rgba(34,53,42,.04)] transition-transform duration-150 hover:-translate-y-1">
                  <div className="aspect-[3/4] overflow-hidden bg-[#e9dce1]">
                    {item.preview_file ? <AuthenticatedImage path={`/api/campaigns/${item.id}/files/${item.preview_file}`} alt={`Campaign image for ${item.product}`} className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" />
                      : <div className="flex h-full items-center justify-center px-8 text-center font-display text-3xl text-ink-soft">Images are on their way.</div>}
                  </div>
                  <div className="p-5">
                    <p className="text-[11px] font-bold tracking-[.12em] text-[#a24d6d] uppercase">{date.format(new Date(item.created_at))} · {statusLabel(item.status)}</p>
                    <h2 className="mt-2 font-display text-[26px] leading-tight text-ink">{item.product}</h2>
                    <p className="mt-4 text-xs font-bold text-ink underline decoration-orange decoration-2 underline-offset-4">Open campaign ↗</p>
                  </div>
                </a>
              ))}
            </div>

            <details className="group mt-16 rounded-[22px] border border-line bg-[#fff8f7] p-5 sm:p-7" onToggle={(event) => { if (event.currentTarget.open) loadMetrics() }}>
              <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-display text-[25px] text-ink [&::-webkit-details-marker]:hidden">
                <span>View workflow metrics</span><span className="text-xl text-orange transition-transform group-open:rotate-45" aria-hidden="true">+</span>
              </summary>
              <p className="mt-2 text-xs leading-6 text-ink-soft">Review and generation details for your own campaigns.</p>
              {metricsLoading ? <p role="status" className="mt-6 text-sm text-ink-soft">Loading metrics…</p> : null}
              {metricsError ? <p role="alert" className="mt-6 text-sm text-[#a24d6d]">{metricsError}</p> : null}
              {metrics ? (
                <div className="mt-7 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
                  <Metric label="Images generated" value={String(metrics.images_generated)} detail={`${metrics.campaigns_completed} campaigns completed`} />
                  <Metric label="Images approved" value={String(metrics.images_approved)} detail={`${metrics.images_reviewed} images reviewed`} />
                  <Metric label="Review acceptance" value={metrics.approval_rate == null ? '—' : `${number.format(metrics.approval_rate * 100)}%`} detail="Approved / reviewed" />
                  <Metric label="First preview" value={metrics.mean_time_to_first_preview_seconds == null ? '—' : `${number.format(metrics.mean_time_to_first_preview_seconds)} s`} detail="Mean from worker start" />
                  <Metric label="Generation time" value={metrics.mean_generation_seconds == null ? '—' : `${number.format(metrics.mean_generation_seconds)} s`} detail="Mean per completed image" />
                  <Metric label="Product detail issues" value={metrics.product_detail_error_rate == null ? '—' : `${number.format(metrics.product_detail_error_rate * 100)}%`} detail="Shape, color, or label / reviewed" />
                  <Metric label="Estimated cost / approved" value={metrics.estimated_cost_per_approved_usd == null ? '—' : money.format(metrics.estimated_cost_per_approved_usd)} detail="Local reservation, not account billing" />
                </div>
              ) : null}
              {metrics ? <p className="mt-6 max-w-2xl text-xs leading-6 text-ink-soft">{metrics.note}</p> : null}
            </details>
          </>
        ) : null}
      </main>
      <footer className="border-t border-white/10 bg-[#172331]/70 px-5 py-6 text-center text-[11px] text-[#dacbd2] sm:px-10">Stillroom · Product photography workflow</footer>
    </div>
  )
}
