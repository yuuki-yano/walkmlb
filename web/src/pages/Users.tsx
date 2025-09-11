import { useCallback, useEffect, useState } from 'react';
import FooterNav from '../components/FooterNav';

type UserRow = { id: number; email: string; role: string; created_at?: string | null };

const ROLES = ["admin","Premium","Subscribe","Normal"];

export default function Users() {
  // Derive base path for API (supports deployment under a subpath like /mlbwalk)
  const base = new URL('.', window.location.href).pathname.replace(/\/$/, '');
  const [users, setUsers] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [roleFilter, setRoleFilter] = useState('');
  const [activeFilter, setActiveFilter] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [newPass, setNewPass] = useState('');
  const [newRole, setNewRole] = useState('Normal');
  const [resetEmail, setResetEmail] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [resetNewPass, setResetNewPass] = useState('');

  const access = () => localStorage.getItem('access_token');
  const refresh = () => localStorage.getItem('refresh_token');

  const authFetch = useCallback(async (path: string, init: RequestInit = {}, retry = true): Promise<Response> => {
    const headers: Record<string,string> = { ...(init.headers as any || {}) };
    const at = access();
    if (at) headers['Authorization'] = 'Bearer ' + at;
  const res = await fetch(base + '/api' + path, { ...init, headers });
    if (res.status === 401 && retry && refresh()) {
      try {
    const r2 = await fetch(base + '/api/auth/refresh', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ refresh_token: refresh() }) });
        if (r2.ok) {
          const j = await r2.json();
            localStorage.setItem('access_token', j.access_token);
            localStorage.setItem('refresh_token', j.refresh_token);
            return authFetch(path, init, false);
        }
      } catch {}
    }
    return res;
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setError(null); setInfo(null);
    try {
      const params = new URLSearchParams();
      if (q.trim()) params.append('q', q.trim());
      if (roleFilter) params.append('role', roleFilter);
      if (activeFilter) params.append('active', activeFilter);
      const res = await authFetch('/auth/users' + (params.toString()? ('?' + params.toString()):''));
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const j = await res.json();
      setUsers(j);
      setInfo('取得: ' + j.length + ' 件');
    } catch (e:any) {
      setError('取得失敗: ' + (e?.message||''));
    } finally {
      setLoading(false);
    }
  }, [authFetch]);

  useEffect(()=>{ load(); }, [load]);

  async function updateRole(id: number, role: string) {
    if (!window.confirm(`ユーザーID ${id} のロールを ${role} に変更しますか？`)) return;
    setError(null); setInfo(null);
    try {
      const res = await authFetch(`/auth/users/${id}/role`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ role }) });
      if (!res.ok) throw new Error('更新失敗: HTTP ' + res.status);
      setInfo('更新しました');
      await load();
    } catch (e:any) {
      setError(e.message);
    }
  }

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    setError(null); setInfo(null);
    try {
      const res = await authFetch('/auth/users', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ email:newEmail, password:newPass, role:newRole }) });
      if (!res.ok) throw new Error('作成失敗');
      setInfo('作成しました');
      setNewEmail(''); setNewPass(''); setNewRole('Normal');
      await load();
    } catch (e:any) { setError(e.message); }
  }

  async function deactivate(u: UserRow) {
    if (!window.confirm(`ユーザー ${u.email} を無効化しますか？`)) return;
    try { await authFetch(`/auth/users/${u.id}/deactivate`, { method:'POST' }); await load(); } catch { setError('無効化失敗'); }
  }
  async function activate(u: UserRow) {
    try { await authFetch(`/auth/users/${u.id}/activate`, { method:'POST' }); await load(); } catch { setError('有効化失敗'); }
  }
  async function remove(u: UserRow) {
    if (!window.confirm(`ユーザー ${u.email} を削除しますか？`)) return;
    try { await authFetch(`/auth/users/${u.id}`, { method:'DELETE' }); await load(); } catch { setError('削除失敗'); }
  }

  async function requestReset(e: React.FormEvent) {
    e.preventDefault();
    try {
  const res = await fetch(base + '/api/auth/password/reset-request', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ email: resetEmail }) });
      const j = await res.json();
      if (j.token) {
        setResetToken(j.token);
        setInfo('リセットトークン取得: ' + j.token.slice(0,12) + '...');
      } else setInfo('リセット手続き送信');
    } catch { setError('リクエスト失敗'); }
  }
  async function confirmReset(e: React.FormEvent) {
    e.preventDefault();
    try {
  const res = await fetch(base + '/api/auth/password/reset-confirm', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ token: resetToken, new_password: resetNewPass }) });
      if (res.ok) setInfo('パスワード再設定完了'); else setError('再設定失敗');
    } catch { setError('再設定失敗'); }
  }

  const myAccess = access();

  return (
    <>
      <main>
        <div className="card">
          <h2>ユーザー管理</h2>
          {!myAccess && <p className="error">先にログインしてください（右下ナビのログインから）。</p>}
          <div className="row" style={{gap:'0.5rem', flexWrap:'wrap'}}>
            <input placeholder="検索 (email)" value={q} onChange={e=>setQ(e.target.value)} style={{width:180}} />
            <select value={roleFilter} onChange={e=>setRoleFilter(e.target.value)}>
              <option value="">Role(全て)</option>
              {ROLES.map(r=> <option key={r} value={r}>{r}</option>)}
            </select>
            <select value={activeFilter} onChange={e=>setActiveFilter(e.target.value)}>
              <option value="">Active(全て)</option>
              <option value="1">Active</option>
              <option value="0">Inactive</option>
            </select>
            <button onClick={load} disabled={loading}>検索</button>
          </div>
          <details style={{marginTop:12}}>
            <summary>新規ユーザー作成</summary>
            <form onSubmit={createUser} className="small" style={{marginTop:8, display:'flex', flexWrap:'wrap', gap:'0.5rem'}}>
              <input required placeholder="email" value={newEmail} onChange={e=>setNewEmail(e.target.value)} />
              <input required placeholder="password" type="password" value={newPass} onChange={e=>setNewPass(e.target.value)} />
              <select value={newRole} onChange={e=>setNewRole(e.target.value)}>
                {ROLES.map(r => <option key={r}>{r}</option>)}
              </select>
              <button type="submit">作成</button>
            </form>
          </details>
          <details style={{marginTop:12}}>
            <summary>パスワードリセット (デモ用)</summary>
            <form onSubmit={requestReset} style={{marginTop:8, display:'flex', flexWrap:'wrap', gap:'0.5rem'}}>
              <input placeholder="email" value={resetEmail} onChange={e=>setResetEmail(e.target.value)} />
              <button type="submit">リセットトークン取得</button>
            </form>
            <form onSubmit={confirmReset} style={{marginTop:8, display:'flex', flexWrap:'wrap', gap:'0.5rem'}}>
              <input placeholder="token" value={resetToken} onChange={e=>setResetToken(e.target.value)} style={{flex:1,minWidth:240}} />
              <input placeholder="new password" type="password" value={resetNewPass} onChange={e=>setResetNewPass(e.target.value)} />
              <button type="submit">再設定</button>
            </form>
          </details>
          {loading && <p className="small">読み込み中...</p>}
          {error && <p className="error" style={{marginTop:8}}>{error}</p>}
          {info && <p className="small" style={{marginTop:8}}>{info}</p>}
          {users.length > 0 && (
            <div style={{marginTop:12}} className="table-scroll">
              <table className="table-bordered" style={{minWidth:760}}>
                <thead>
                  <tr>
                    <th>ID</th><th>Email</th><th>Role</th><th>Active</th><th>Created</th><th style={{width:130}}>Role変更</th><th style={{width:160}}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.id}>
                      <td>{u.id}</td>
                      <td>{u.email}</td>
                      <td>{u.role}</td>
                      <td>{String((u as any).is_active)}</td>
                      <td>{u.created_at || '-'}</td>
                      <td>
                        <select defaultValue={u.role} onChange={e=> updateRole(u.id, e.target.value)}>
                          {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                        </select>
                      </td>
                      <td style={{display:'flex', gap:4}}>
                        {(u as any).is_active ? (
                          <button type="button" onClick={()=>deactivate(u)} style={{fontSize:'0.7rem'}}>無効化</button>
                        ) : (
                          <button type="button" onClick={()=>activate(u)} style={{fontSize:'0.7rem'}}>有効化</button>
                        )}
                        <button type="button" onClick={()=>remove(u)} style={{fontSize:'0.7rem', background:'#922', color:'#fff'}}>削除</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {(!loading && users.length===0 && !error) && <p className="small">ユーザーなし / 権限エラーの可能性</p>}
        </div>
      </main>
      <FooterNav />
    </>
  );
}
