import { useEffect, useRef, useState } from 'react';

// Derive base path for API (works when app is mounted under a subpath)
const base = new URL('.', window.location.href).pathname.replace(/\/$/, '');

async function fetchJSON(path: string, opts: RequestInit = {}) {
  const r = await fetch(base + path, opts);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export default function Admin() {
  const [month, setMonth] = useState<string>(()=> new Date().toISOString().slice(0,7));
  const [date, setDate] = useState<string>(()=> new Date().toISOString().slice(0,10));
  const [token, setToken] = useState<string>(()=> localStorage.getItem('walkmlb_admin_token')||'');
  const [status, setStatus] = useState<any | null>(null);
  const [message, setMessage] = useState<string>('');
  const [busy, setBusy] = useState<boolean>(false);
  const timerRef = useRef<number | null>(null);

  useEffect(()=>()=>{ if (timerRef.current) window.clearInterval(timerRef.current); },[]);

  function authHeaders() {
    const t = token.trim();
    return t ? { Authorization: `Bearer ${t}` } : {};
  }

  async function refreshStatus() {
    try {
      const s = await fetchJSON('/api/updater/status', { headers: { ...authHeaders() } });
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

  useEffect(()=>{ refreshStatus(); },[]);

  return (
    <>
      <main>
        <div className="card">
          <h2>管理者: 月データ更新</h2>
          <div className="row" style={{gap:'1rem'}}>
            <label>ADMIN_TOKEN
              <input type="password" value={token} onChange={e=>setToken(e.target.value)} placeholder="サーバのADMIN_TOKEN" />
            </label>
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
