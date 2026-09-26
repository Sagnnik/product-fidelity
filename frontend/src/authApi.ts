export type GetToken = () => Promise<string | null>

export async function authedFetch(getToken: GetToken, path: string, init?: RequestInit): Promise<Response> {
  const token = await getToken()
  if (!token) throw new Error('Sign in to continue.')
  const headers = new Headers(init?.headers)
  headers.set('Authorization', `Bearer ${token}`)
  return fetch(path, { ...init, headers })
}

export async function api<T>(getToken: GetToken, path: string, init?: RequestInit): Promise<T> {
  const response = await authedFetch(getToken, path, init)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = body.detail
    throw new Error(typeof detail === 'string' ? detail : 'The request could not be completed.')
  }
  return body as T
}

export async function downloadFile(getToken: GetToken, path: string, filename: string): Promise<void> {
  const response = await authedFetch(getToken, path)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : 'Download failed.')
  }
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
