import { supabase } from '../lib/supabase'

export function Login() {
  const handleLogin = async () => {
    await supabase.auth.signInWithOAuth({
      provider: 'azure',
      options: { scopes: 'email profile openid' },
    })
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <h1>Kothari Group Expenses</h1>
        <p>Sign in to continue</p>
        <button className="btn btn-primary login-btn" onClick={handleLogin}>
          Sign in with Microsoft
        </button>
      </div>
    </div>
  )
}
