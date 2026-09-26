import React from 'react'
import ReactDOM from 'react-dom/client'
import { ClerkProvider } from '@clerk/react'
import App from './App'
import './styles.css'

const clerkKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {clerkKey ? (
      <ClerkProvider publishableKey={clerkKey} afterSignOutUrl="/">
        <App />
      </ClerkProvider>
    ) : (
      <main className="mx-auto max-w-xl px-6 py-24 text-ink">
        <h1 className="font-display text-4xl">Stillroom needs a Clerk key</h1>
        <p className="mt-4 text-sm leading-7">Set VITE_CLERK_PUBLISHABLE_KEY in frontend/.env.local, then restart the frontend build or dev server.</p>
      </main>
    )}
  </React.StrictMode>,
)
