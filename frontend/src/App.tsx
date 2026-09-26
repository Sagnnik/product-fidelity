import { useEffect, useState, type FormEvent } from 'react'
import { SignInButton, UserButton, useAuth, useClerk } from '@clerk/react'
import AuthenticatedImage from './AuthenticatedImage'
import { api, downloadFile } from './authApi'
import HistoryPage from './HistoryPage'
import SocialPublish from './SocialPublish'

type SceneConfig = { id: string; name: string; detail: string; setting: string }
type Config = {
  model: string; size: [number, number]; scenes: SceneConfig[]; key_present: boolean
  estimated_max_per_image_usd: number; max_free_images_per_campaign: number
  estimated_max_campaign_usd: number; reserved_spend_usd: number; spend_limit_usd: number
  free_campaigns_remaining: number; free_campaigns_total: number
  free_budget_available: boolean
}
type SceneResult = {
  id: string; name: string; detail: string; prompt: string; status: string
  file: string | null; generation_seconds: number | null
  review: 'pending' | 'approved' | 'rejected'; issues: string[]
}
type Campaign = {
  id: string; status: string; created_at: string; product: string; audience: string
  critical_details?: string; scene_description?: string; background_file?: string | null
  funding?: 'free' | 'byok'
  reference_file: string; scenes: SceneResult[]; first_preview_seconds: number | null
  estimated_reserved_usd: number; error?: string
}
const ISSUE_LABELS: Record<string, string> = {
  shape: 'Product shape', color: 'Product color', label: 'Label or logo', lighting: 'Lighting',
  artifact: 'Visual artifact', scene: 'Scene fit', extra_product: 'Extra product',
}
const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 })
const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
type SceneMode = 'ideas' | 'describe' | 'reference'
const FIELD = 'w-full rounded-xl border border-line bg-[#fffaf9] px-4 py-3 text-sm text-ink placeholder:text-[#93858c] focus:border-orange focus:outline-none'

function SiteHeader({ page }: { page: 'home' | 'create' }) {
  const { isLoaded, isSignedIn } = useAuth()
  return (
    <header className="border-b border-white/10 bg-[#172331]/80 backdrop-blur-md">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-5 py-4 sm:px-10 lg:px-14">
        <a href="/" className="flex items-center gap-2.5 text-[#fff3f1] hover:text-white" aria-label="Stillroom home">
          <span className="grid h-8 w-8 place-items-center rounded-[9px] bg-orange text-lg font-bold text-white">✳</span>
          <span className="font-display text-[27px] font-semibold tracking-[-.04em]">stillroom<span className="text-orange">.</span></span>
        </a>
        <nav aria-label="Main navigation" className="flex items-center gap-3 text-[11px] font-bold tracking-[.12em] text-[#e9ccd5] uppercase sm:gap-7">
          <a href="/create" aria-current={page === 'create' ? 'page' : undefined} className={page === 'create' ? 'text-white' : 'hover:text-white'}>Create</a>
          {isSignedIn ? <a href="/history" className="hover:text-white">History</a> : null}
          {isSignedIn ? <UserButton /> : null}
          {isLoaded && !isSignedIn ? <SignInButton mode="modal"><button type="button" className="rounded-full border border-[#f2b5c7]/55 px-4 py-2 text-[11px] font-bold tracking-[.08em] text-[#fff4f1] uppercase transition-colors hover:border-[#f2b5c7] hover:bg-white/10">Log in</button></SignInButton> : null}
        </nav>
      </div>
    </header>
  )
}

function fileUrl(id: string, filename: string) {
  return `/api/campaigns/${id}/files/${filename}`
}

function FallingPetals() {
  return (
    <div className="falling-petals pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      {Array.from({ length: 12 }, (_, index) => <span key={index} className="falling-petal" />)}
    </div>
  )
}

function HomePage() {
  return (
    <div className="site-shell min-h-screen">
      <a href="#main" className="sr-only rounded bg-ink px-4 py-2 text-white focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50">Skip to main content</a>
      <SiteHeader page="home" />
      <main id="main">
        <section className="relative isolate overflow-hidden">
          <div className="hero-atmosphere pointer-events-none absolute inset-0" aria-hidden="true" />
          <FallingPetals />
          <div className="relative z-10 mx-auto flex min-h-[590px] max-w-[1440px] items-center px-5 py-16 sm:px-10 lg:min-h-[680px] lg:px-14">
            <div className="max-w-[750px]">
              <h1 className="font-display text-[clamp(3.4rem,7.1vw,7.5rem)] leading-[.96] tracking-[-.055em] text-[#fff4f1] text-balance">Create campaign photos <em className="font-medium text-[#f2a7b8]">from your product.</em></h1>
              <p className="mt-7 max-w-[550px] text-base leading-[1.75] text-[#e1d1d8] sm:text-lg">Bring a product photo. Direct the setting with a scene brief or a background reference. Generate portrait images, then review each one against the original before export.</p>
              <div className="mt-9 flex flex-wrap items-center gap-4">
                <a href="/create" className="rounded-full bg-orange px-6 py-3 text-sm font-bold text-white transition-colors duration-150 hover:bg-[#8e3d5d]">Create a campaign <span aria-hidden="true">↗</span></a>
                <span className="text-xs text-[#e1d1d8]">Set the scene · compare the product · export your picks</span>
              </div>
            </div>
          </div>
        </section>
        <section className="border-t border-white/10 bg-[#182635]/90 px-5 py-12 sm:px-10 lg:px-14">
          <div className="mx-auto grid max-w-[1328px] gap-6 text-[#fff4f1] sm:grid-cols-3">
            <div><span className="text-xs font-bold text-[#f0a6bb]">01 / PRODUCT</span><p className="mt-2 text-sm text-[#e1d1d8]">Start with a clear photo and name the details the edit should retain.</p></div>
            <div><span className="text-xs font-bold text-[#f0a6bb]">02 / DIRECTION</span><p className="mt-2 text-sm text-[#e1d1d8]">Choose the scene mix, describe your own setting, or add a background reference.</p></div>
            <div><span className="text-xs font-bold text-[#f0a6bb]">03 / SELECTION</span><p className="mt-2 text-sm text-[#e1d1d8]">Compare results side by side, record issues, and export the images you approve.</p></div>
          </div>
        </section>
      </main>
      <footer className="border-t border-white/10 bg-[#172331]/70 px-5 py-6 text-center text-[11px] text-[#dacbd2] sm:px-10">Stillroom · Product photography workflow</footer>
    </div>
  )
}

function SceneCard({
  campaign, scene, guides, issues, busy, onIssue, onReview, onDownload,
}: {
  campaign: Campaign; scene: SceneResult; guides: boolean; issues: string[]; busy: boolean
  onIssue: (sceneId: string, issue: string) => void
  onReview: (sceneId: string, approved: boolean) => void
  onDownload: (scene: SceneResult) => void
}) {
  return (
    <article className="min-w-0 overflow-hidden rounded-[20px] border border-line bg-[#fff8f7] text-ink shadow-[0_12px_30px_rgba(34,53,42,.04)]">
      <div className="relative aspect-[3/4] overflow-hidden bg-[#e9dce1]">
        {scene.file ? (
          <div className={`relative h-full w-full ${guides ? 'portrait-guides' : ''}`}>
            <AuthenticatedImage path={fileUrl(campaign.id, scene.file)} alt={`${scene.name} campaign photo for ${campaign.product}`} className="h-full w-full object-cover" />
          </div>
        ) : (
          <div className="flex h-full flex-col items-center justify-center gap-4 px-7 text-center">
            <div className={`h-10 w-10 rounded-full border-[3px] border-ink/15 border-t-orange ${scene.status === 'running' ? 'animate-spin' : ''}`} />
            <p className="text-sm text-ink-soft">{scene.status === 'running' ? 'Creating this scene…' : scene.status === 'interrupted' ? 'Interrupted. This request may have been billed.' : scene.status === 'failed' ? 'This scene stopped.' : 'Waiting its turn'}</p>
          </div>
        )}
        <span className="absolute left-3 top-3 rounded-full bg-[#fff8f7]/90 px-3 py-1 text-[10px] font-bold tracking-[.13em] text-ink uppercase backdrop-blur-sm">{scene.name}</span>
      </div>
      <div className="p-4 sm:p-5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="font-display text-[25px] leading-tight">{scene.name}</h3>
            <p className="mt-1 text-xs text-ink-soft">{scene.detail}</p>
          </div>
          {scene.review !== 'pending' ? (
            <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${scene.review === 'approved' ? 'bg-mint text-ink' : 'bg-[#f6ddd3] text-[#8f3e2f]'}`}>{scene.review === 'approved' ? 'Usable' : 'Revise'}</span>
          ) : null}
        </div>
        {scene.file ? (
          <>
            <p className="mt-3 text-[11px] text-ink-soft tabular-nums">Generated in {number.format(scene.generation_seconds ?? 0)} s · Review product details before use</p>
            <div className="mt-4 flex flex-wrap gap-1.5" aria-label={`Issues for ${scene.name}`}>
              {Object.entries(ISSUE_LABELS).map(([code, label]) => (
                <button key={code} type="button" onClick={() => onIssue(scene.id, code)} aria-pressed={issues.includes(code)} className={`rounded-full border px-2.5 py-1.5 text-[11px] font-medium transition-colors duration-150 ${issues.includes(code) ? 'border-orange bg-[#f5dae3] text-[#813d59]' : 'border-line bg-transparent text-ink-soft hover:border-ink/50 hover:text-ink'}`}>{label}</button>
              ))}
            </div>
            <div className="mt-4 flex gap-2">
              <button type="button" disabled={busy} onClick={() => onReview(scene.id, true)} className="flex-1 rounded-xl bg-ink px-3 py-2.5 text-xs font-bold text-white transition-colors duration-150 hover:bg-[#36495c] disabled:opacity-50">Mark Usable</button>
              <button type="button" disabled={busy} onClick={() => onReview(scene.id, false)} className="flex-1 rounded-xl border border-line px-3 py-2.5 text-xs font-bold text-ink transition-colors duration-150 hover:border-orange hover:text-[#a24d6d] disabled:opacity-50">Needs Changes</button>
            </div>
            <button type="button" onClick={() => onDownload(scene)} className="mt-3 text-xs font-bold text-ink underline decoration-orange decoration-2 underline-offset-4 hover:text-[#a24d6d]">Download draft ↗</button>
          </>
        ) : null}
      </div>
    </article>
  )
}

function CreatePage() {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const clerk = useClerk()
  const [config, setConfig] = useState<Config | null>(null)
  const [runId, setRunId] = useState(() => new URLSearchParams(window.location.search).get('run'))
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [backgroundFile, setBackgroundFile] = useState<File | null>(null)
  const [backgroundPreview, setBackgroundPreview] = useState<string | null>(null)
  const [product, setProduct] = useState('')
  const [audience, setAudience] = useState('')
  const [criticalDetails, setCriticalDetails] = useState('')
  const [sceneDescription, setSceneDescription] = useState('')
  const [sceneMode, setSceneMode] = useState<SceneMode>('ideas')
  const [imageCount, setImageCount] = useState(3)
  const [moreCount, setMoreCount] = useState(3)
  const [funding, setFunding] = useState<'free' | 'byok'>('free')
  const [falKey, setFalKey] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submittingMore, setSubmittingMore] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [error, setError] = useState('')
  const [authRequested, setAuthRequested] = useState(false)
  const [reviewError, setReviewError] = useState('')
  const [selectedIssues, setSelectedIssues] = useState<Record<string, string[]>>({})
  const [guides, setGuides] = useState(false)

  useEffect(() => {
    if (!isSignedIn) { setConfig(null); return }
    api<Config>(getToken, '/api/config')
      .then(setConfig)
      .catch((failure: Error) => setError(failure.message))
  }, [getToken, isSignedIn])

  useEffect(() => {
    if (!file) { setPreview(null); return }
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  useEffect(() => {
    if (!backgroundFile) { setBackgroundPreview(null); return }
    const url = URL.createObjectURL(backgroundFile)
    setBackgroundPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [backgroundFile])

  useEffect(() => {
    if (!runId || !isSignedIn) return
    let stopped = false
    async function refresh() {
      try {
        const next = await api<Campaign>(getToken, `/api/campaigns/${runId}`)
        if (!stopped) setCampaign(next)
      } catch (failure) {
        if (!stopped) setError((failure as Error).message)
      }
    }
    void refresh()
    const active = !campaign || ['queued', 'running'].includes(campaign.status)
    const timer = active ? window.setInterval(() => { void refresh() }, 2500) : undefined
    return () => { stopped = true; window.clearInterval(timer) }
  }, [campaign?.status, getToken, isSignedIn, runId])

  const progressKey = campaign?.scenes.map((scene) => scene.status).join(',')

  useEffect(() => {
    if (!campaign || !isSignedIn) return
    api<Config>(getToken, '/api/config')
      .then(setConfig)
      .catch(() => {})
  }, [campaign?.id, campaign?.status, getToken, isSignedIn, progressKey])

  useEffect(() => {
    if (campaign?.id === runId) {
      document.getElementById('campaign-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }, [campaign?.id, runId])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError('')
    if (!file) { setError('Choose a product photo to create your campaign.'); return }
    if (file.size > 10 * 1024 * 1024) { setError('Choose a photo under 10 MB.'); return }
    if (sceneMode === 'reference' && backgroundFile && backgroundFile.size > 10 * 1024 * 1024) { setError('Choose a background photo under 10 MB.'); return }
    if (sceneMode === 'describe' && !sceneDescription.trim()) { setError('Describe the scene you want to create.'); return }
    if (sceneMode === 'reference' && !backgroundFile) { setError('Choose a background photo for this direction.'); return }
    if (!Number.isInteger(imageCount) || imageCount < 1 || imageCount > 10) { setError('Choose 1–10 images for this batch.'); return }
    if (funding === 'byok' && !falKey.trim()) { setError('Enter your fal key to use BYOK.'); return }
    if (!isLoaded) return
    if (!isSignedIn) {
      setAuthRequested(true)
      clerk.openSignIn({})
      return
    }
    const form = new FormData()
    form.append('image', file)
    form.append('product', product)
    form.append('audience', audience)
    form.append('critical_details', criticalDetails)
    form.append('scene_description', sceneMode === 'ideas' ? '' : sceneDescription)
    form.append('image_count', String(imageCount))
    if (sceneMode === 'reference' && backgroundFile) form.append('background', backgroundFile)
    setSubmitting(true)
    try {
      const next = await api<Campaign>(getToken, '/api/campaigns', {
        method: 'POST', body: form,
        headers: funding === 'byok' ? { 'X-Fal-Key': falKey.trim() } : undefined,
      })
      window.history.replaceState(null, '', `/create?run=${next.id}`)
      setRunId(next.id)
      setCampaign(next)
      setAuthRequested(false)
      if (funding === 'free') setConfig((current) => current ? { ...current, free_campaigns_remaining: Math.max(0, current.free_campaigns_remaining - 1) } : current)
    } catch (failure) {
      setError((failure as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  async function addMore(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!campaign) return
    if (campaign.funding === 'byok' && !falKey.trim()) { setReviewError('Enter your fal key to add images.'); return }
    const remaining = campaign.funding === 'free' ? 10 - campaign.scenes.length : 10
    const count = Math.min(moreCount, remaining)
    if (!Number.isInteger(count) || count < 1 || count > 10) { setReviewError('Choose an available image count for this batch.'); return }
    setReviewError('')
    setSubmittingMore(true)
    const form = new FormData()
    form.append('image_count', String(count))
    try {
      const next = await api<Campaign>(getToken, `/api/campaigns/${campaign.id}/images`, {
        method: 'POST', body: form,
        headers: campaign.funding === 'byok' ? { 'X-Fal-Key': falKey.trim() } : undefined,
      })
      setCampaign(next)
    } catch (failure) {
      setReviewError((failure as Error).message)
    } finally {
      setSubmittingMore(false)
    }
  }

  async function resumeRemaining() {
    if (!campaign) return
    if (campaign.funding === 'byok' && !falKey.trim()) { setReviewError('Enter your fal key to continue.'); return }
    setReviewError('')
    setSubmittingMore(true)
    try {
      const next = await api<Campaign>(getToken, `/api/campaigns/${campaign.id}/resume`, {
        method: 'POST', headers: campaign.funding === 'byok' ? { 'X-Fal-Key': falKey.trim() } : undefined,
      })
      setCampaign(next)
    } catch (failure) {
      setReviewError((failure as Error).message)
    } finally {
      setSubmittingMore(false)
    }
  }

  function toggleIssue(sceneId: string, issue: string) {
    setSelectedIssues((current) => {
      const chosen = current[sceneId] ?? campaign?.scenes.find((scene) => scene.id === sceneId)?.issues ?? []
      return { ...current, [sceneId]: chosen.includes(issue) ? chosen.filter((item) => item !== issue) : [...chosen, issue] }
    })
  }

  async function review(sceneId: string, approved: boolean) {
    if (!campaign) return
    const issues = selectedIssues[sceneId] ?? campaign.scenes.find((scene) => scene.id === sceneId)?.issues ?? []
    if (!approved && issues.length === 0) { setReviewError('Choose at least one issue before marking a scene for changes.'); return }
    setReviewError('')
    setReviewing(true)
    try {
      const next = await api<Campaign>(getToken, `/api/campaigns/${campaign.id}/reviews/${sceneId}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approved, issues: approved ? [] : issues }),
      })
      setCampaign(next)
      if (approved) setSelectedIssues((current) => ({ ...current, [sceneId]: [] }))
    } catch (failure) {
      setReviewError((failure as Error).message)
    } finally {
      setReviewing(false)
    }
  }

  async function download(path: string, filename: string) {
    try {
      await downloadFile(getToken, path, filename)
    } catch (failure) {
      setReviewError((failure as Error).message)
    }
  }

  const completed = campaign?.scenes.filter((scene) => scene.status === 'completed').length ?? 0
  const approved = campaign?.scenes.filter((scene) => scene.review === 'approved').length ?? 0
  const moreMax = campaign?.funding === 'free' ? Math.max(0, 10 - campaign.scenes.length) : 10
  const moreBatchCount = Math.min(moreCount, moreMax)
  const estimatedReservation = config ? (config.estimated_max_per_image_usd + (sceneMode === 'reference' && backgroundFile ? 0.015 : 0)) * (Number.isFinite(imageCount) ? imageCount : 0) : null
  const freeCanCoverBatch = !config || estimatedReservation === null || estimatedReservation <= config.spend_limit_usd - config.reserved_spend_usd + 0.000001

  return (
    <div className="site-shell min-h-screen">
      <a href="#main" className="sr-only rounded bg-ink px-4 py-2 text-white focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50">Skip to main content</a>
      <SiteHeader page="create" />

      <main id="main">
        <section id="create" className="border-b border-white/10 bg-[#182635]/75 pb-16 pt-9 sm:pt-14">
          <div className="mx-auto max-w-[1328px] px-5 sm:px-10 lg:px-14">
            <div className="mb-8 text-[#fff4f1] sm:mb-10">
              <p className="text-[11px] font-bold tracking-[.18em] text-[#f0a6bb] uppercase">Creation workspace</p>
              <h1 className="mt-3 font-display text-[clamp(2.5rem,5vw,4.8rem)] leading-[1.02] tracking-[-.05em]">Create a campaign</h1>
              <p className="mt-3 max-w-[690px] text-sm leading-7 text-[#e1d1d8] sm:text-base">Start with the product, choose the setting, then decide how many images to make. You can review every draft against its source before exporting.</p>
            </div>
            <form onSubmit={submit} className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_330px] lg:items-start">
              <div className="min-w-0 space-y-5">
                <section className="rounded-[24px] border border-[#ead2d8] bg-paper p-5 text-ink shadow-[0_20px_50px_rgba(4,12,22,.18)] sm:p-7">
                  <div className="flex items-start gap-4 border-b border-line pb-5"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-mint text-xs font-bold text-[#8e3d5d]">01</span><div><h2 className="font-display text-[29px] leading-tight">Your product</h2><p className="mt-1 text-xs leading-5 text-ink-soft">Use a clear photo. Call out any visual details that should survive the edit.</p></div></div>
              <div className="mt-6">
                <label htmlFor="product-photo" className="mb-2 block text-xs font-bold">Product photo <span className="text-orange">*</span></label>
                <div className="relative overflow-hidden rounded-[16px] border border-dashed border-[#bda9b2] bg-[#fff8f7] p-4 transition-colors duration-150 hover:border-orange focus-within:border-orange sm:p-5">
                  {preview ? <img src={preview} alt="Selected product preview" width="180" height="180" className="mx-auto mb-4 h-36 w-full rounded-lg object-contain" /> : <div className="mx-auto mb-4 grid h-24 w-24 place-items-center rounded-full bg-mint text-4xl text-ink" aria-hidden="true">↥</div>}
                  <input id="product-photo" name="product-photo" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => setFile(event.currentTarget.files?.[0] ?? null)} className="block w-full cursor-pointer text-xs text-ink-soft file:mr-3 file:cursor-pointer file:rounded-full file:border-0 file:bg-ink file:px-4 file:py-2 file:text-xs file:font-bold file:text-white hover:file:bg-[#36495c]" />
                  <p className="mt-3 text-[11px] leading-5 text-ink-soft">JPEG, PNG, or WebP · Up to 10&nbsp;MB · Isolated products work best</p>
                </div>
              </div>
              <div className="mt-5 grid gap-5 sm:grid-cols-2">
                <div><label htmlFor="product-description" className="mb-2 block text-xs font-bold">What is the product? <span className="text-orange">*</span></label><input id="product-description" name="product-description" type="text" autoComplete="off" maxLength={120} required value={product} onChange={(event) => setProduct(event.target.value)} placeholder="e.g. matte black over-ear headphones" className={FIELD} /><p className="mt-1.5 text-[10px] text-ink-soft">Name what appears in your photo.</p></div>
                <div><label htmlFor="audience" className="mb-2 block text-xs font-bold">Who is it for? <span className="font-normal text-ink-soft">Optional</span></label><input id="audience" name="audience" type="text" autoComplete="off" maxLength={100} value={audience} onChange={(event) => setAudience(event.target.value)} placeholder="e.g. design-minded commuters" className={FIELD} /><p className="mt-1.5 text-[10px] text-ink-soft">A short cue for the mood.</p></div>
              </div>
              <div className="mt-5">
                <label htmlFor="critical-details" className="mb-2 block text-xs font-bold">Details to preserve <span className="font-normal text-ink-soft">Optional</span></label>
                <input id="critical-details" type="text" maxLength={180} value={criticalDetails} onChange={(event) => setCriticalDetails(event.target.value)} placeholder="e.g. silver logo, over-ear shape, matte finish" className={FIELD} />
                <p className="mt-1.5 text-[10px] text-ink-soft">Guides the edit and gives you a review checklist. Check the result against the source.</p>
              </div>
                </section>
                <section className="rounded-[24px] border border-[#ead2d8] bg-paper p-5 text-ink shadow-[0_20px_50px_rgba(4,12,22,.18)] sm:p-7">
                  <div className="flex items-start gap-4 border-b border-line pb-5"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-mint text-xs font-bold text-[#8e3d5d]">02</span><div><h2 className="font-display text-[29px] leading-tight">Scene direction</h2><p className="mt-1 text-xs leading-5 text-ink-soft">Choose how to guide the background and overall mood.</p></div></div>
                  <fieldset className="mt-5">
                    <legend className="sr-only">Choose a scene direction</legend>
                    <div className="grid gap-2 sm:grid-cols-3">
                      {([
                        ['ideas', 'Explore ideas', 'Studio, lifestyle, and celebration scenes'],
                        ['describe', 'Describe a scene', 'Set your own place, light, and mood'],
                        ['reference', 'Use a photo', 'Guide the setting with an image'],
                      ] as const).map(([mode, title, description]) => (
                        <label key={mode} className={`flex cursor-pointer gap-2 rounded-xl border p-3 text-xs transition-colors ${sceneMode === mode ? 'border-orange bg-[#f5dae3]' : 'border-line bg-[#fffaf9] hover:border-orange/60'}`}>
                          <input type="radio" name="scene-mode" value={mode} checked={sceneMode === mode} onChange={() => setSceneMode(mode)} className="mt-0.5 accent-orange" />
                          <span><strong className="block text-ink">{title}</strong><span className="mt-1 block leading-5 text-ink-soft">{description}</span></span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                  {sceneMode === 'ideas' ? <p className="mt-4 rounded-xl bg-[#fffaf9] px-4 py-3 text-xs leading-6 text-ink-soft">We rotate through <strong className="text-ink">Studio</strong>, <strong className="text-ink">Lifestyle</strong>, and <strong className="text-ink">Celebration</strong>. If you choose fewer than three images, the first directions come first.</p> : null}
                  {sceneMode !== 'ideas' ? <div className="mt-5"><label htmlFor="scene-description" className="mb-2 block text-xs font-bold">Describe the setting {sceneMode === 'reference' ? <span className="font-normal text-ink-soft">Optional</span> : <span className="text-orange">*</span>}</label><textarea id="scene-description" rows={3} maxLength={400} required={sceneMode === 'describe'} value={sceneDescription} onChange={(event) => setSceneDescription(event.target.value)} placeholder="e.g. rain-soaked balcony at dusk, soft city lights behind the product" className={FIELD} /><p className="mt-1.5 text-[10px] text-ink-soft">Mention the surface, lighting, and mood you want to see.</p></div> : null}
                  {sceneMode === 'reference' ? <div className="mt-5"><label htmlFor="background-photo" className="mb-2 block text-xs font-bold">Background reference <span className="text-orange">*</span></label>{backgroundPreview ? <img src={backgroundPreview} alt="Selected background preview" className="mb-3 h-40 w-full rounded-xl object-cover" /> : null}<input id="background-photo" type="file" required accept="image/jpeg,image/png,image/webp" onChange={(event) => setBackgroundFile(event.currentTarget.files?.[0] ?? null)} className="block w-full rounded-xl border border-line bg-[#fffaf9] p-3 text-xs text-ink-soft file:mr-3 file:rounded-full file:border-0 file:bg-ink file:px-4 file:py-2 file:text-xs file:font-bold file:text-white" /><p className="mt-1.5 text-[10px] leading-5 text-ink-soft">This is a visual reference, not an exact backdrop. The edit may reinterpret it.</p></div> : null}
                </section>
              </div>
              <aside className="rounded-[24px] border border-[#ead2d8] bg-paper p-5 text-ink shadow-[0_20px_50px_rgba(4,12,22,.18)] sm:p-7 lg:sticky lg:top-5">
                <div className="flex items-start gap-4 border-b border-line pb-5"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-mint text-xs font-bold text-[#8e3d5d]">03</span><div><h2 className="font-display text-[27px] leading-tight">Output</h2><p className="mt-1 text-xs text-ink-soft">Portrait images, ready to review.</p></div></div>
              <div className="mt-5">
                <label htmlFor="image-count" className="mb-2 block text-xs font-bold">How many images?</label>
                <div className="flex flex-wrap items-center gap-2">
                  {[1, 3, 5, 10].map((count) => <button key={count} type="button" onClick={() => setImageCount(count)} aria-pressed={imageCount === count} className={`min-w-10 rounded-full border px-3 py-2 text-xs font-bold transition-colors ${imageCount === count ? 'border-orange bg-[#f5dae3] text-[#813d59]' : 'border-line bg-[#fffaf9] text-ink hover:border-orange'}`}>{count}</button>)}
                  <input id="image-count" aria-label="Custom image count" type="number" inputMode="numeric" min={1} max={10} step={1} value={imageCount} onChange={(event) => setImageCount(event.currentTarget.valueAsNumber)} className="w-16 rounded-xl border border-line bg-[#fffaf9] px-2 py-2 text-center text-xs text-ink" />
                </div>
                <p className="mt-2 text-[11px] leading-5 text-ink-soft">1–10 now. You can add more later with your own fal key.</p>
              </div>
              <fieldset className="mt-6 border-t border-line pt-5">
                <legend className="pt-5 text-xs font-bold">Generation credit</legend>
                <div className="mt-2 grid gap-2">
                  <label className={`flex cursor-pointer items-start gap-2 rounded-xl border p-3 text-xs ${funding === 'free' ? 'border-orange bg-[#f5dae3]' : 'border-line bg-[#fff8f7]'}`}>
                    <input type="radio" name="funding" value="free" checked={funding === 'free'} onChange={() => setFunding('free')} className="mt-0.5 accent-orange" />
                    <span><strong className="block text-ink">Free allowance</strong><span className="mt-1 block text-ink-soft">{isSignedIn ? `${config?.free_campaigns_remaining ?? '—'} of ${config?.free_campaigns_total ?? 3} campaigns left` : 'Available after sign-in'}</span></span>
                  </label>
                  <label className={`flex cursor-pointer items-start gap-2 rounded-xl border p-3 text-xs ${funding === 'byok' ? 'border-orange bg-[#f5dae3]' : 'border-line bg-[#fff8f7]'}`}>
                    <input type="radio" name="funding" value="byok" checked={funding === 'byok'} onChange={() => setFunding('byok')} className="mt-0.5 accent-orange" />
                    <span><strong className="block text-ink">Use my fal key</strong><span className="mt-1 block text-ink-soft">Your fal account pays for this campaign</span></span>
                  </label>
                </div>
                {funding === 'byok' ? <div className="mt-4"><label htmlFor="fal-key" className="mb-2 block text-xs font-bold">Your fal API key</label><input id="fal-key" type="password" autoComplete="off" spellCheck={false} value={falKey} onChange={(event) => setFalKey(event.target.value)} placeholder="Paste your fal key" className="w-full rounded-xl border border-line bg-[#fff8f7] px-4 py-3 text-sm text-ink" /><p className="mt-1.5 text-[10px] leading-5 text-ink-soft">Held only in this tab and sent to the server for this campaign; never saved in the project. <a href="https://fal.ai/dashboard/keys" target="_blank" rel="noreferrer" className="underline">Create a fal key ↗</a></p></div> : null}
              </fieldset>
              <div className="mt-6 border-t border-line pt-5">
                <p className="text-xs font-bold">{imageCount} portrait {imageCount === 1 ? 'image' : 'images'} · {sceneMode === 'ideas' ? 'three scene directions' : sceneMode === 'describe' ? 'your scene' : 'your background reference'}</p>
                <p className="mt-1 text-[11px] text-ink-soft">FLUX.2 Pro edit · {config ? `${config.size[0]} × ${config.size[1]} px` : 'portrait format'} · One at a time</p>
                <p className="mt-4 text-xs font-bold">{estimatedReservation === null ? 'Cost estimate available after sign-in' : `Estimated reservation: ${money.format(estimatedReservation)}`}</p>
                <p className="mt-1 text-[11px] leading-5 text-ink-soft">Estimate only; your fal account may bill differently when using your key.</p>
                <button type="submit" disabled={!isLoaded || submitting || (isSignedIn && funding === 'free' && (config?.key_present === false || config?.free_campaigns_remaining === 0 || config?.free_budget_available === false || !freeCanCoverBatch)) || (funding === 'byok' && !falKey.trim())} className="mt-5 w-full rounded-full bg-orange px-6 py-3 text-sm font-bold text-white transition-colors duration-150 hover:bg-[#8e3d5d] disabled:cursor-not-allowed disabled:opacity-50">{submitting ? 'Starting campaign…' : !isSignedIn ? 'Sign in to generate ↗' : `Generate ${imageCount} ${imageCount === 1 ? 'image' : 'images'} ↗`}</button>
              </div>
              {authRequested ? <p role="status" className="mt-3 text-sm text-ink-soft">{isSignedIn ? 'You are signed in. Press Create once more to start.' : 'Sign in or create an account to continue. Your brief will stay here.'}</p> : null}
              {funding === 'free' && config?.key_present === false ? <p className="mt-3 text-sm text-[#a24d6d]">Free generation is unavailable; choose BYOK to use your fal account.</p> : null}
              {funding === 'free' && config?.free_campaigns_remaining === 0 ? <p className="mt-3 text-sm text-[#a24d6d]">Your three free campaigns are used. Choose BYOK to continue.</p> : null}
              {funding === 'free' && config?.free_budget_available === false ? <p className="mt-3 text-sm text-[#a24d6d]">The studio's free budget is used. Choose BYOK to continue.</p> : null}
              {funding === 'free' && config?.free_budget_available !== false && !freeCanCoverBatch ? <p className="mt-3 text-sm text-[#a24d6d]">This batch exceeds the remaining studio budget. Choose fewer images or use your fal key.</p> : null}
              {error ? <p role="alert" className="mt-4 rounded-xl bg-[#fae4da] px-4 py-3 text-sm text-[#8d3e2d]">{error}</p> : null}
              <p className="mt-4 text-[11px] leading-5 text-ink-soft">Images are drafts. Compare shape, color, labels, and lighting with your source before export.</p>
              </aside>
            </form>
          </div>
        </section>

        {campaign ? (
          <section id="campaign-results" className="mx-auto max-w-[1440px] scroll-mt-8 px-5 py-16 text-[#fff4f1] sm:px-10 lg:px-14 lg:py-20">
            <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-7">
              <div><p className="text-[11px] font-bold tracking-[.18em] text-[#f0a6bb] uppercase">Campaign / {campaign.id}</p><h2 className="mt-3 font-display text-[clamp(2.2rem,4vw,4.25rem)] leading-tight tracking-[-.04em]">Your campaign directions.</h2><p className="mt-2 text-sm text-[#e1d1d8]" aria-live="polite">{campaign.status === 'completed' ? `All ${campaign.scenes.length} images are ready for review.` : ['failed', 'interrupted'].includes(campaign.status) ? campaign.error : `${completed} of ${campaign.scenes.length} images ready · creating one image at a time…`}</p></div>
              <div className="flex flex-wrap items-center gap-4">
                <label className="flex cursor-pointer items-center gap-2 text-xs font-bold"><input type="checkbox" checked={guides} onChange={(event) => setGuides(event.target.checked)} className="h-4 w-4 accent-orange" /> Show headline space</label>
                <button type="button" disabled={approved === 0} onClick={() => void download(`/api/campaigns/${campaign.id}/approved-download`, `approved-${campaign.id}.zip`)} className="rounded-full bg-ink px-4 py-2 text-xs font-bold text-white transition-colors duration-150 hover:bg-[#36495c] disabled:cursor-not-allowed disabled:opacity-50">Export approved ({approved}) ↓</button>
                <button type="button" onClick={() => void download(`/api/campaigns/${campaign.id}/download`, `internal-${campaign.id}.zip`)} className="text-xs font-bold text-[#f5dce3] underline decoration-orange decoration-2 underline-offset-4">Internal archive</button>
              </div>
            </div>
            {campaign.critical_details ? <p className="mt-5 rounded-xl border border-line bg-[#fff8f7] px-4 py-3 text-sm text-ink"><strong>Review against source:</strong> {campaign.critical_details}</p> : null}
            <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <article className="overflow-hidden rounded-[20px] border border-line bg-[#fff8f7] text-ink">
                <div className="aspect-[3/4] bg-[#faf9f6]"><AuthenticatedImage path={fileUrl(campaign.id, campaign.reference_file)} alt={`Original reference for ${campaign.product}`} className="h-full w-full object-cover" loading="eager" /></div>
                <div className="p-4 sm:p-5"><span className="text-[10px] font-bold tracking-[.13em] text-[#a24d6d] uppercase">Original / reference</span><h3 className="mt-2 font-display text-[25px] leading-tight">Starting point</h3><p className="mt-1 text-xs text-ink-soft">Keep this beside every generated image while reviewing product details.</p></div>
              </article>
              {campaign.scenes.map((scene) => <SceneCard key={scene.id} campaign={campaign} scene={scene} guides={guides} issues={selectedIssues[scene.id] ?? scene.issues} busy={reviewing} onIssue={toggleIssue} onReview={review} onDownload={(item) => { if (item.file) void download(fileUrl(campaign.id, item.file), `${item.id}-draft.png`) }} />)}
            </div>
            {reviewError ? <p role="alert" className="mt-5 rounded-xl bg-[#fae4da] px-4 py-3 text-sm text-[#8d3e2d]">{reviewError}</p> : null}
            {['interrupted', 'failed'].includes(campaign.status) && campaign.scenes.some((scene) => scene.status === 'queued') ? (
              <button type="button" disabled={submittingMore} onClick={() => void resumeRemaining()} className="mt-6 rounded-full bg-orange px-5 py-3 text-xs font-bold text-white disabled:opacity-50">Continue unstarted images ↗</button>
            ) : null}
            {(campaign.funding === 'byok' || (moreMax > 0 && !(campaign.status === 'failed' && campaign.estimated_reserved_usd === 0))) ? (
              <form onSubmit={addMore} className="mt-8 flex flex-wrap items-end gap-4 rounded-[20px] border border-white/20 bg-[#172331]/80 p-5 sm:p-6">
                <div className="min-w-[200px] flex-1"><h3 className="font-display text-2xl">More images, same campaign.</h3><p className="mt-1 text-xs text-[#e1d1d8]">{campaign.funding === 'byok' ? 'Add 1–10 per batch, with no campaign image cap.' : `${moreMax} of 10 project-funded image slots remain in this campaign.`}</p></div>
                <label className="text-xs font-bold">Images <input type="number" min={1} max={moreMax} step={1} value={moreBatchCount} onChange={(event) => setMoreCount(event.currentTarget.valueAsNumber)} className="mt-2 block w-20 rounded-xl border border-line bg-[#fff8f7] px-3 py-2.5 text-sm text-ink" /></label>
                {campaign.funding === 'byok' ? <label className="min-w-[180px] flex-1 text-xs font-bold">Your fal key <input type="password" autoComplete="off" value={falKey} onChange={(event) => setFalKey(event.target.value)} placeholder="Enter your fal key" className="mt-2 block w-full rounded-xl border border-line bg-[#fff8f7] px-3 py-2.5 text-sm text-ink" /></label> : null}
                <button type="submit" disabled={submittingMore || (campaign.funding === 'byok' && !falKey.trim()) || !['completed', 'failed', 'interrupted'].includes(campaign.status)} className="rounded-full bg-orange px-5 py-3 text-xs font-bold text-white disabled:opacity-50">{submittingMore ? 'Adding…' : 'Add images ↗'}</button>
              </form>
            ) : null}
            <SocialPublish campaignId={campaign.id} scenes={campaign.scenes} getToken={getToken} />
            <div className="mt-8 grid gap-4 rounded-[20px] border border-line bg-[#fff8f7] p-5 text-sm text-ink-soft sm:grid-cols-3 sm:p-6">
              <p><strong className="block text-ink">Look at the product</strong> Check shape, color, texture, labels, and logos against the source.</p>
              <p><strong className="block text-ink">Look at the scene</strong> Check shadows, reflections, extra objects, and headline space.</p>
              <p><strong className="block text-ink">Use the review buttons</strong> Approval and issue labels become measurable workflow data.</p>
            </div>
          </section>
        ) : null}

      </main>
      <footer className="border-t border-white/10 bg-[#172331]/70 px-5 py-6 text-center text-[11px] text-[#dacbd2] sm:px-10">Stillroom · Product photography workflow</footer>
    </div>
  )
}

export default function App() {
  if (window.location.pathname.startsWith('/history')) return <HistoryPage />
  if (window.location.pathname.startsWith('/create') || new URLSearchParams(window.location.search).has('run')) return <CreatePage />
  return <HomePage />
}
