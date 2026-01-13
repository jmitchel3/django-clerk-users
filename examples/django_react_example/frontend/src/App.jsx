import { useState } from 'react'
import {
  SignedIn,
  SignedOut,
  SignInButton,
  SignOutButton,
  UserButton,
  useAuth,
} from '@clerk/clerk-react'
import './App.css'

const API_BASE = 'http://localhost:8000/api'

function App() {
  return (
    <div className="app">
      <header>
        <h1>Django + Clerk Example</h1>
        <div className="auth-status">
          <SignedOut>
            <SignInButton mode="modal">
              <button className="sign-in-btn">Sign In</button>
            </SignInButton>
          </SignedOut>
          <SignedIn>
            <UserButton />
            <SignOutButton>
              <button className="sign-out-btn">Sign Out</button>
            </SignOutButton>
          </SignedIn>
        </div>
      </header>

      <main>
        <SignedOut>
          <p>Sign in to test authenticated API calls to Django.</p>
        </SignedOut>
        <SignedIn>
          <ApiTester />
        </SignedIn>
      </main>
    </div>
  )
}

function ApiTester() {
  const { getToken } = useAuth()
  const [publicResult, setPublicResult] = useState(null)
  const [protectedResult, setProtectedResult] = useState(null)
  const [profileResult, setProfileResult] = useState(null)
  const [loading, setLoading] = useState('')

  const callApi = async (endpoint, setResult) => {
    setLoading(endpoint)
    try {
      const token = await getToken()
      const response = await fetch(`${API_BASE}${endpoint}`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
        credentials: 'include',
      })
      const data = await response.json()
      setResult({ status: response.status, data })
    } catch (error) {
      setResult({ error: error.message })
    }
    setLoading('')
  }

  return (
    <div className="api-tester">
      <h2>Test Django API Endpoints</h2>

      <div className="endpoint">
        <h3>Public Endpoint</h3>
        <p>
          <code>GET /api/public/</code> - No authentication required
        </p>
        <button
          onClick={() => callApi('/public/', setPublicResult)}
          disabled={loading === '/public/'}
        >
          {loading === '/public/' ? 'Loading...' : 'Call API'}
        </button>
        {publicResult && <ResultDisplay result={publicResult} />}
      </div>

      <div className="endpoint">
        <h3>Protected Endpoint</h3>
        <p>
          <code>GET /api/protected/</code> - Requires @clerk_user_required
        </p>
        <button
          onClick={() => callApi('/protected/', setProtectedResult)}
          disabled={loading === '/protected/'}
        >
          {loading === '/protected/' ? 'Loading...' : 'Call API'}
        </button>
        {protectedResult && <ResultDisplay result={protectedResult} />}
      </div>

      <div className="endpoint">
        <h3>Profile Endpoint</h3>
        <p>
          <code>GET /api/profile/</code> - Returns full user profile
        </p>
        <button
          onClick={() => callApi('/profile/', setProfileResult)}
          disabled={loading === '/profile/'}
        >
          {loading === '/profile/' ? 'Loading...' : 'Call API'}
        </button>
        {profileResult && <ResultDisplay result={profileResult} />}
      </div>
    </div>
  )
}

function ResultDisplay({ result }) {
  return (
    <pre className="result">
      {JSON.stringify(result, null, 2)}
    </pre>
  )
}

export default App
