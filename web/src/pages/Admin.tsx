import { useEffect, useRef, useState } from 'react';

// Derive base path for API (works when app is mounted under a subpath)
const base = new URL('.', window.location.href).pathname.replace(/\/$/, '');

async function fetchJSON(path: string, opts: RequestInit = {}, retryAlt?: ()=>Promise<RequestInit | null>) {
  const r = await fetch(base + path, opts);
  if (r.ok) return r.json();
  // If 401 and retryAlt provider exists, try alternate auth once
  if (r.status === 401 && retryAlt) {
    const alt = await retryAlt();
    if (alt) {
      const r2 = await fetch(base + path, alt);
      if (r2.ok) return r2.json();
      throw new Error(`HTTP ${r2.status}`);
    }
  }
  throw new Error(`HTTP ${r.status}`);
}

export default function Admin() {
  const [month, setMonth] = useState<string>(()=> new Date().toISOString().slice(0,7));
  const [date, setDate] = useState<string>(()=> new Date().toISOString().slice(0,10));
  const [token, setToken] = useState<string>(()=> localStorage.getItem('walkmlb_admin_token')||'');
  const [status, setStatus] = useState<any | null>(null);
  const [cacheSummary, setCacheSummary] = useState<any | null>(null);
  const [message, setMessage] = useState<string>('');
  const [busy, setBusy] = useState<boolean>(false);
  const timerRef = useRef<number | null>(null);
  const [authMode, setAuthMode] = useState<'bearer'|'basic'>(()=> (localStorage.getItem('walkmlb_admin_authmode') as any) || 'bearer');
  const [basicUser, setBasicUser] = useState<string>(()=> localStorage.getItem('walkmlb_admin_basic_user')||'');
  const [basicPass, setBasicPass] = useState<string>('');

  useEffect(()=>()=>{ if (timerRef.current) window.clearInterval(timerRef.current); },[]);

  function authHeaders() {
    if (authMode === 'basic') {
      if (!basicUser || !basicPass) return {};
      const enc = btoa(`${basicUser}:${basicPass}`);
      return { Authorization: `Basic ${enc}` };
    }
    const t = token.trim();
    return t ? { Authorization: `Bearer ${t}` } : {};
  }

  async function refreshStatus() {
    try {
      const headersPrimary = { ...authHeaders() };
      const s = await fetchJSON('/api/updater/status', { headers: headersPrimary }, async()=>{
        // fallback: if bearer empty but basic filled OR vice versa
        try {
          const sel = (document.querySelector('select') as HTMLSelectElement)?.value;
          // heuristic: gather inputs
          const userInput = (document.querySelector('input[placeholder="ユーザ"]') as HTMLInputElement)?.value;
          const passInput = (document.querySelector('input[placeholder="パスワード"]') as HTMLInputElement)?.value;
          const tokenInput = (document.querySelector('input[placeholder="ADMIN_TOKEN"]') as HTMLInputElement)?.value;
          if (sel === 'bearer' && (!tokenInput) && userInput && passInput) {
            const enc = btoa(`${userInput}:${passInput}`);
            return { headers: { Authorization: `Basic ${enc}` } };
          }
          if (sel === 'basic' && (!userInput || !passInput) && tokenInput) {
            return { headers: { Authorization: `Bearer ${tokenInput}` } };
          }
        } catch {}
        return null;
      });
      setStatus(s);
    } catch (e:any) {
      setMessage('ステータス取得に失敗: ' + (e?.message||''));
    }
  }

  function startPolling() {
    if (timerRef.current) window.clearInterval(timerRef.current);
    timerRef.current = window.setInterval(refreshStatus, 1000);
  }

  async function startBackfill() {
    if (!month) { setMessage('月を選択してください'); return; }
    if (!token.trim()) { setMessage('ADMIN_TOKEN を入力してください'); return; }
    setBusy(true);
    localStorage.setItem('walkmlb_admin_token', token.trim());
    try {
      // Helper: format YYYY-MM-DD in local time (avoid UTC shift)
      const fmtLocal = (dd: Date) => {
        const y = dd.getFullYear();
        const m = (dd.getMonth()+1).toString().padStart(2,'0');
        const d2 = dd.getDate().toString().padStart(2,'0');
        return `${y}-${m}-${d2}`;
      };
      // Generate all dates in the selected month (local time)
      const [y, m] = month.split('-').map(Number);
      const first = new Date(y, (m-1), 1);
      const days: string[] = [];
      for (let d = new Date(first); d.getMonth() === (m-1); d.setDate(d.getDate()+1)) {
        days.push(fmtLocal(d));
      }
      // Run sequentially and wait for updater to finish each day
      for (let i=0; i<days.length; i++) {
        const d = days[i];
        setMessage(`更新中 ${i+1} / ${days.length} (${d})`);
        await fetchJSON(`/api/updater/run-once?date=${encodeURIComponent(d)}`, { method: 'POST', headers: { ...authHeaders() } });
        // wait until not running (max 90s per day)
        const start = Date.now();
        const max = 90_000;
        // small initial delay
        await new Promise(r => setTimeout(r, 800));
        while (Date.now() - start < max) {
          try {
            const s = await fetchJSON('/api/updater/status', { headers: { ...authHeaders() } });
            if (!s.isRunning) break;
          } catch {}
          await new Promise(r => setTimeout(r, 1000));
        }
      }
      setMessage('完了。ステータスを確認してください。');
      await refreshStatus();
    } catch (e:any) {
      setMessage('開始に失敗: ' + (e?.message||''));
    } finally {
      setBusy(false);
    }
  }

  async function runOnce() {
    if (!date) { setMessage('日付を選択してください'); return; }
    if (!token.trim()) { setMessage('ADMIN_TOKEN を入力してください'); return; }
    setBusy(true); setMessage('単日更新を開始…');
    localStorage.setItem('walkmlb_admin_token', token.trim());
    try {
      await fetchJSON(`/api/updater/run-once?date=${encodeURIComponent(date)}`, {
        method: 'POST', headers: { ...authHeaders() }
      });
      setMessage('バックグラウンドで実行中…');
      await refreshStatus();
      startPolling();
    } catch (e:any) {
      setMessage('開始に失敗: ' + (e?.message||''));
    } finally {
      setBusy(false);
    }
  }

  async function refreshCache() {
    try {
  const headersPrimary = { ...authHeaders() };
  const s = await fetchJSON('/api/cache/summary', { headers: headersPrimary });
      setCacheSummary(s);
    } catch (e:any) {
      setMessage('キャッシュ取得失敗: ' + (e?.message||''));
    }
  }

  async function clearCache(kind: string) {
    if (!window.confirm(kind==='all' ? '本当に全キャッシュを削除しますか？' : `${kind} キャッシュを削除しますか？`)) return;
    try {
      const r = await fetchJSON(`/api/cache/clear?kind=${encodeURIComponent(kind)}`, { method: 'DELETE', headers: { ...authHeaders() } });
      setMessage('削除: ' + JSON.stringify(r.cleared||r));
      await refreshCache();
    } catch (e:any) {
      setMessage('削除失敗: ' + (e?.message||''));
    }
  }

  useEffect(()=>{ refreshStatus(); refreshCache(); },[]);

  return (
    <>
      <main>
        <div className="card">
          <h2>管理者: 月データ更新</h2>
          <div className="row" style={{gap:'1rem'}}>
            <label>認証方式
              <select value={authMode} onChange={e=>{ const v = e.target.value as any; setAuthMode(v); localStorage.setItem('walkmlb_admin_authmode', v); }}>
                <option value="bearer">Bearer Token</option>
                <option value="basic">Basic Auth</option>
              </select>
            </label>
            {authMode==='bearer' ? (
              <label>TOKEN
                <input type="password" value={token} onChange={e=>{ setToken(e.target.value); localStorage.setItem('walkmlb_admin_token', e.target.value);} } placeholder="ADMIN_TOKEN" />
              </label>
            ) : (
              <>
                <label>User
                  <input value={basicUser} onChange={e=>{ setBasicUser(e.target.value); localStorage.setItem('walkmlb_admin_basic_user', e.target.value);} } placeholder="ユーザ" />
                </label>
                <label>Pass
                  <input type="password" value={basicPass} onChange={e=>setBasicPass(e.target.value)} placeholder="パスワード" />
                </label>
              </>
            )}
          </div>
          <div className="row" style={{gap:'1rem', marginTop:8}}>
            <label>月
              <input type="month" value={month} onChange={e=>setMonth(e.target.value)} />
            </label>
            <button onClick={startBackfill} disabled={busy}>この月をバックフィル</button>
          </div>
          <div className="row" style={{gap:'1rem', marginTop:8}}>
            <label>単日
              <input type="date" value={date} onChange={e=>setDate(e.target.value)} />
            </label>
            <button onClick={runOnce} disabled={busy}>この日を更新</button>
          </div>
          {message && <p className="small" style={{marginTop:8}}>{message}</p>}
        </div>

        <div style={{height:12}} />
        <div className="card">
          <h3>キャッシュ</h3>
          <div className="row" style={{gap:'0.5rem', flexWrap:'wrap'}}>
            <button onClick={()=>{ refreshCache(); }}>再読込</button>
            <button onClick={()=> clearCache('boxscore')}>Boxscore削除</button>
            <button onClick={()=> clearCache('linescore')}>Linescore削除</button>
            <button onClick={()=> clearCache('status')}>Status削除</button>
            <button onClick={()=> clearCache('all')}>全削除</button>
          </div>
          {cacheSummary ? (
            <div style={{marginTop:8}}>
              <div className="row"><b>boxscore:</b><span>{cacheSummary.counts?.boxscore} (最新: {cacheSummary.latest?.boxscore || '-'})</span></div>
              <div className="row"><b>linescore:</b><span>{cacheSummary.counts?.linescore} (最新: {cacheSummary.latest?.linescore || '-'})</span></div>
              <div className="row"><b>status:</b><span>{cacheSummary.counts?.status} (最新: {cacheSummary.latest?.status || '-'})</span></div>
            </div>
          ) : <p className="small">未取得</p>}
        </div>

        <div style={{height:12}} />
        <div className="card">
          <h3>アップデータ ステータス</h3>
          <div className="row" style={{gap:'1rem'}}>
            <button onClick={refreshStatus}>更新</button>
          </div>
          {status ? (
            <div style={{marginTop:8}}>
              <div className="row"><b>isRunning:</b> <span>{String(status.isRunning)}</span></div>
              <div className="row"><b>lastStart:</b> <span>{status.lastStart || '-'}</span></div>
              <div className="row"><b>lastFinish:</b> <span>{status.lastFinish || '-'}</span></div>
              <div className="row"><b>lastUpdatedGames:</b> <span>{status.lastUpdatedGames ?? 0}</span></div>
              <div className="row"><b>lastError:</b> <span>{status.lastError || '-'}</span></div>
            </div>
          ) : (
            <p className="small">ステータスなし</p>
          )}
        </div>
      </main>
    </>
  );
}
