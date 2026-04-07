import { supabase } from '../lib/supabase'

export const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/**
 * Wrapper around fetch that attaches the Supabase JWT as a Bearer token.
 */
export async function authFetch(url, options = {}) {
  const { data: { session } } = await supabase.auth.getSession()
  const headers = { ...options.headers }
  if (session?.access_token) {
    headers['Authorization'] = `Bearer ${session.access_token}`
  }
  return fetch(url, { ...options, headers })
}

// Cache signed URLs for 50 min (they expire at 60)
const urlCache = {}
export async function getReceiptUrl(receiptId) {
  const cached = urlCache[receiptId]
  if (cached && Date.now() - cached.ts < 50 * 60 * 1000) return cached.url
  const res = await authFetch(`${API}/receipts/${receiptId}/url`)
  const data = await res.json()
  urlCache[receiptId] = { url: data.url, ts: Date.now() }
  return data.url
}
