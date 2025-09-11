import { useState } from 'react';
import FooterNav from '../components/FooterNav';

export default function Signup() {
  const base = new URL('.', window.location.href).pathname.replace(/\/$/, '');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string|null>(null);
  const [done, setDone] = useState<string|null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(null); setDone(null); setLoading(true);
    try {
      const r = await fetch(base + '/api/auth/signup', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      if (!r.ok) {
        const j = await r.json().catch(()=>({detail:'signup failed'}));
        throw new Error(j.detail || 'signup failed');
      }
      const j = await r.json();
      localStorage.setItem('access_token', j.access_token);
      if (j.refresh_token) localStorage.setItem('refresh_token', j.refresh_token);
      setDone('登録しました。ログイン済みです。');
    } catch (e:any) { setError(e.message); }
    finally { setLoading(false); }
  }

  return (
    <>
      <main>
        <div className="card">
          <h2>新規ユーザー登録</h2>
          {done ? <p className="small">{done}</p> : (
            <form onSubmit={submit}>
              <div className="row"><label>メール <input type="email" required value={email} onChange={e=>setEmail(e.target.value)} /></label></div>
              <div className="row"><label>パスワード <input type="password" required value={password} onChange={e=>setPassword(e.target.value)} /></label></div>
              <button disabled={loading}>{loading? '送信中...' : '登録'}</button>
              {error && <p className="error">{error}</p>}
            </form>
          )}
        </div>
      </main>
      <FooterNav />
    </>
  );
}
