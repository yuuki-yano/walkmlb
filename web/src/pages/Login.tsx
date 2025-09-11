import { useState } from 'react';
import FooterNav from '../components/FooterNav';

export default function Login() {
  // Derive base path for API (supports deployment under a subpath like /mlbwalk)
  const base = new URL('.', window.location.href).pathname.replace(/\/$/, '');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string|null>(null);
  const [role, setRole] = useState<string|null>(null);
  const [access, setAccess] = useState<string|null>(null);
  const [refresh, setRefresh] = useState<string|null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setLoading(true);
    try {
      const res = await fetch(base + '/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      if (!res.ok) {
        const j = await res.json().catch(()=>({detail:'error'}));
        throw new Error(j.detail || 'login failed');
      }
      const j = await res.json();
      setRole(j.role); setAccess(j.access_token); setRefresh(j.refresh_token);
      // store refresh minimally (demo) – production: use httpOnly cookie via server
      localStorage.setItem('access_token', j.access_token);
      localStorage.setItem('refresh_token', j.refresh_token);
    } catch (err:any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function doRefresh() {
    if (!refresh) return;
    try {
      const res = await fetch(base + '/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh })
      });
      if (res.ok) {
        const j = await res.json();
        setAccess(j.access_token); setRefresh(j.refresh_token); setRole(j.role);
        localStorage.setItem('access_token', j.access_token);
        localStorage.setItem('refresh_token', j.refresh_token);
      }
    } catch {}
  }

  function logout() {
    if (refresh) {
      fetch(base + '/api/auth/logout', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({refresh_token: refresh}) });
    }
    setAccess(null); setRefresh(null); setRole(null);
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }

  return (
    <>
      <main>
        <div className="card">
          <h2>ログイン</h2>
          {role && <p>ログイン中: <strong>{role}</strong></p>}
          {!access && (
            <form onSubmit={submit}>
              <div className="row"><label>メール <input type="email" value={email} onChange={e=>setEmail(e.target.value)} required /></label></div>
              <div className="row"><label>パスワード <input type="password" value={password} onChange={e=>setPassword(e.target.value)} required /></label></div>
              <button disabled={loading}>{loading? '送信中...' : 'ログイン'}</button>
              {error && <p className="error">{error}</p>}
            </form>
          )}
          {access && (
            <div>
              <p className="small">Access取得済み。必要なら更新トークンをローテーションできます。</p>
              <button onClick={doRefresh}>トークン更新</button>{' '}
              <button onClick={logout}>ログアウト</button>
              <details style={{marginTop:'1rem'}}>
                <summary>トークン表示</summary>
                <pre style={{whiteSpace:'pre-wrap', wordBreak:'break-all'}}>access: {access}</pre>
                <pre style={{whiteSpace:'pre-wrap', wordBreak:'break-all'}}>refresh: {refresh}</pre>
              </details>
            </div>
          )}
        </div>
      </main>
      <FooterNav />
    </>
  );
}
