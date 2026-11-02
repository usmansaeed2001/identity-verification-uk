import { useQueryClient } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router'

import { api } from '../api/client'
import { useMe } from '../api/hooks'

function Logo() {
  return (
    <svg viewBox="0 0 32 32" className="size-8" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="currentColor" />
      <path d="M7 19h13v-7h3.5l2.5 4v3h-1.5M7 19v-8h13" stroke="#fff" strokeWidth="2" fill="none" strokeLinejoin="round" />
      <circle cx="11" cy="21" r="2" fill="#fff" />
      <circle cx="22" cy="21" r="2" fill="#fff" />
    </svg>
  )
}

export function Layout({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  const { data: me } = useMe()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  async function signOut() {
    await api('/api/auth/logout', { method: 'POST' })
    queryClient.clear()
    navigate('/login')
  }

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="bg-brand-800 text-white">
        <div className={`mx-auto flex h-16 items-center justify-between gap-4 px-4 ${wide ? 'max-w-7xl' : 'max-w-2xl'}`}>
          <Link to="/" className="flex items-center gap-2 font-semibold text-white">
            <span className="text-brand-500">
              <Logo />
            </span>
            <span>
              Driver Onboarding
              {me?.is_reviewer && <span className="ml-2 font-normal text-brand-100">· Reviewer</span>}
            </span>
          </Link>
          {me && (
            <button type="button" onClick={signOut} className="min-h-11 rounded-lg px-3 text-sm font-medium text-brand-100 hover:bg-brand-700">
              Sign out
            </button>
          )}
        </div>
      </header>
      <main className={`mx-auto w-full flex-1 px-4 py-6 sm:py-10 ${wide ? 'max-w-7xl' : 'max-w-2xl'}`}>{children}</main>
      <footer className="pb-[max(1rem,env(safe-area-inset-bottom))] pt-4 text-center text-xs text-slate-500">
        Your details are encrypted and only seen by our onboarding team.
      </footer>
    </div>
  )
}
