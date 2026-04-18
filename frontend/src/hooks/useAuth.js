import { useState, useEffect, useRef } from 'react'
import { supabase } from '../lib/supabase'
import { API, authFetch } from '../utils/api'

export function useAuth() {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [userRole, setUserRole] = useState(null)
  const fetchedRef = useRef(false)

  useEffect(() => {
    const fetchRole = () => {
      if (fetchedRef.current) return
      fetchedRef.current = true
      // Fire-and-forget: upsert then fetch role, don't block anything
      authFetch(`${API}/users/upsert`, { method: 'POST' })
        .then(() => authFetch(`${API}/users/me`))
        .then(res => res.json())
        .then(data => setUserRole(data.role || 'accountant'))
        .catch(() => setUserRole('accountant'))
    }

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (event, session) => {
        setSession(session)
        setLoading(false)

        if ((event === 'SIGNED_IN' || event === 'INITIAL_SESSION') && session) {
          fetchRole()
        } else if (event === 'SIGNED_OUT') {
          setUserRole(null)
          fetchedRef.current = false
        }
      },
    )

    return () => subscription.unsubscribe()
  }, [])

  const signOut = () => supabase.auth.signOut()

  return { session, loading, signOut, userRole }
}
