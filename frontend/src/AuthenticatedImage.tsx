import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/react'
import { authedFetch } from './authApi'

export default function AuthenticatedImage({ path, alt, className, loading = 'lazy' }: {
  path: string; alt: string; className?: string; loading?: 'eager' | 'lazy'
}) {
  const { getToken } = useAuth()
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    let objectUrl: string | null = null
    let stopped = false
    authedFetch(getToken, path)
      .then((response) => {
        if (!response.ok) throw new Error('Image unavailable')
        return response.blob()
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        if (stopped) URL.revokeObjectURL(objectUrl)
        else setUrl(objectUrl)
      })
      .catch(() => { if (!stopped) setUrl(null) })
    return () => {
      stopped = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [getToken, path])

  return url ? <img src={url} alt={alt} width="768" height="1024" loading={loading} className={className} />
    : <div role="img" aria-label={alt} className={`${className ?? ''} bg-[#e9dce1]`} />
}
