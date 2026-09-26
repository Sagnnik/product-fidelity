import { useEffect, useState, type FormEvent } from 'react'
import { api, type GetToken } from './authApi'

type Account = { page_id: string; name: string; instagram_available: boolean }
type SocialConfig = { enabled: boolean; accounts: Account[] }
type Post = { scene_id: string; platform: string; page_id: string; status: string; remote_id: string | null }
type Scene = { id: string; name: string; review: string; file: string | null }

function DestinationIcons() {
  return (
    <div className="flex items-center gap-2" aria-label="Facebook and Instagram">
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#1877f2] font-sans text-[30px] font-bold leading-none text-white" title="Facebook" aria-label="Facebook">f</span>
      <span className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-[#7952d5] via-[#d7458f] to-[#f6a544] text-white" title="Instagram" aria-label="Instagram">
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.9" aria-hidden="true">
          <rect x="3" y="3" width="18" height="18" rx="5" /><circle cx="12" cy="12" r="4" /><circle cx="17.6" cy="6.5" r="1" fill="currentColor" stroke="none" />
        </svg>
      </span>
    </div>
  )
}

export default function SocialPublish({ campaignId, scenes, getToken }: {
  campaignId: string; scenes: Scene[]; getToken: GetToken
}) {
  const [config, setConfig] = useState<SocialConfig | null>(null)
  const [posts, setPosts] = useState<Post[]>([])
  const [sceneId, setSceneId] = useState('')
  const [destination, setDestination] = useState('')
  const [caption, setCaption] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const approved = scenes.filter((scene) => scene.review === 'approved' && scene.file)

  useEffect(() => {
    let active = true
    Promise.all([
      api<SocialConfig>(getToken, '/api/social/config'),
      api<Post[]>(getToken, `/api/social/posts/${campaignId}`),
    ]).then(([nextConfig, nextPosts]) => {
      if (active) { setConfig(nextConfig); setPosts(nextPosts) }
    }).catch((failure: Error) => { if (active) setError(failure.message) })
    return () => { active = false }
  }, [campaignId, getToken])

  useEffect(() => {
    if (!approved.some((scene) => scene.id === sceneId)) setSceneId(approved[0]?.id ?? '')
  }, [approved.map((scene) => scene.id).join(','), sceneId])

  const destinations = config?.accounts.flatMap((account) => [
    { value: `facebook:${account.page_id}`, label: `${account.name} · Facebook Page` },
    ...(account.instagram_available ? [{ value: `instagram:${account.page_id}`, label: `${account.name} · Instagram` }] : []),
  ]) ?? []
  const selectedDestination = destinations.some((item) => item.value === destination) ? destination : destinations[0]?.value ?? ''
  const [platform, pageId] = selectedDestination.split(':')
  const existing = posts.find((post) => post.scene_id === sceneId && post.platform === platform && post.page_id === pageId)

  async function connectMeta() {
    setError('')
    setBusy(true)
    try {
      const response = await api<{ url: string }>(getToken, '/api/social/connect', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ campaign_id: campaignId }),
      })
      window.location.assign(response.url)
    } catch (failure) {
      setError((failure as Error).message)
      setBusy(false)
    }
  }

  async function disconnect(pageId: string) {
    setError('')
    try {
      await api(getToken, `/api/social/accounts/${pageId}`, { method: 'DELETE' })
      setConfig((current) => current ? { ...current, accounts: current.accounts.filter((item) => item.page_id !== pageId) } : current)
      setDestination('')
    } catch (failure) {
      setError((failure as Error).message)
    }
  }

  async function publish(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!sceneId || !platform || !pageId) return
    setError('')
    setMessage('')
    setBusy(true)
    try {
      const result = await api<{ status: string; remote_id: string }>(getToken, `/api/campaigns/${campaignId}/publish`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_id: sceneId, platform, page_id: pageId, caption }),
      })
      setPosts((current) => [...current, { scene_id: sceneId, platform, page_id: pageId, status: result.status, remote_id: result.remote_id }])
      setMessage('Published to your connected account.')
    } catch (failure) {
      setError((failure as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="mt-8 rounded-[20px] border border-white/20 bg-[#172331]/85 p-5 sm:p-6" aria-label="Publish approved images">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><h3 className="font-display text-2xl">Publish when it is ready.</h3><p className="mt-1 text-xs text-[#e1d1d8]">Only images you mark usable can be posted.</p></div>
        <div className="flex items-center gap-4"><DestinationIcons />{config?.enabled ? <button type="button" onClick={() => void connectMeta()} disabled={busy} className="rounded-full border border-white/40 px-4 py-2 text-xs font-bold hover:bg-white/10 disabled:opacity-50">{config.accounts.length ? 'Connect another account' : 'Connect Meta account'}</button> : null}</div>
      </div>
      {config && !config.enabled ? <p className="mt-5 text-sm text-[#e1d1d8]">Facebook and Instagram publishing is coming after launch. For now, export the images you approve.</p> : null}
      {config?.enabled && config.accounts.length > 0 ? (
        <>
          <div className="mt-5 flex flex-wrap gap-2 text-xs text-[#e1d1d8]">
            {config.accounts.map((account) => <span key={account.page_id} className="rounded-full border border-white/20 px-3 py-1.5">{account.name} <button type="button" onClick={() => void disconnect(account.page_id)} className="ml-2 underline underline-offset-2">Disconnect</button></span>)}
          </div>
          {approved.length ? (
            <form onSubmit={publish} className="mt-5 grid gap-4 lg:grid-cols-2">
              <label className="text-xs font-bold">Approved image
                <select value={sceneId} onChange={(event) => setSceneId(event.target.value)} className="mt-2 block w-full rounded-xl border border-line bg-[#fff8f7] px-3 py-3 text-sm text-ink">
                  {approved.map((scene) => <option key={scene.id} value={scene.id}>{scene.name}</option>)}
                </select>
              </label>
              <label className="text-xs font-bold">Destination
                <select value={selectedDestination} onChange={(event) => setDestination(event.target.value)} className="mt-2 block w-full rounded-xl border border-line bg-[#fff8f7] px-3 py-3 text-sm text-ink">
                  {destinations.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                </select>
              </label>
              <label className="text-xs font-bold lg:col-span-2">Caption
                <textarea value={caption} onChange={(event) => setCaption(event.target.value)} maxLength={2200} rows={3} placeholder="Write the caption that should accompany this image" className="mt-2 block w-full rounded-xl border border-line bg-[#fff8f7] px-3 py-3 text-sm text-ink" />
              </label>
              <div className="flex flex-wrap items-center gap-3 lg:col-span-2">
                <button type="submit" disabled={busy || !!existing} className="rounded-full bg-orange px-5 py-3 text-xs font-bold text-white disabled:opacity-50">{busy ? 'Publishing…' : existing?.status === 'published' ? 'Already published' : existing ? 'Check destination account' : 'Publish now ↗'}</button>
                <p className="text-xs text-[#e1d1d8]">This posts immediately to the selected account.</p>
              </div>
            </form>
          ) : <p className="mt-5 text-sm text-[#e1d1d8]">Mark an image usable to enable posting.</p>}
        </>
      ) : null}
      {error ? <p role="alert" className="mt-4 rounded-xl bg-[#fae4da] px-4 py-3 text-sm text-[#8d3e2d]">{error}</p> : null}
      {message ? <p role="status" className="mt-4 text-sm text-[#f2b5c7]">{message}</p> : null}
    </section>
  )
}
