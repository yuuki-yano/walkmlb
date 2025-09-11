import { useEffect, useState } from 'react';
import FooterNav from '../components/FooterNav';

export default function MyPage() {
  const base = new URL('.', window.location.href).pathname.replace(/\/$/, '');
  const [teams, setTeams] = useState<string[]>([]);
  const [allTeams, setAllTeams] = useState<string[]>([]);
  const [newTeam, setNewTeam] = useState('');
  const [steps, setSteps] = useState<string>('');
  const [date, setDate] = useState<string>('');
  const [msg, setMsg] = useState<string>('');
  const [error, setError] = useState<string>('');

  const access = localStorage.getItem('access_token');
  const headers = access ? { Authorization: 'Bearer ' + access, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };

  async function loadTeams() {
    setError('');
    try {
      const r = await fetch(base + '/api/me/teams', { headers });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json();
      setTeams(j.teams || []);
    } catch (e:any) { setError(e.message || '取得失敗'); }
  }
  async function loadAllTeams() {
    try {
      const r = await fetch(base + '/api/calendar/teams');
      if (r.ok) {
        const j = await r.json();
        setAllTeams(j.teams || []);
      }
    } catch {}
  }

  async function addTeam(e: React.FormEvent) {
    e.preventDefault(); setMsg(''); setError('');
    try {
      if (!newTeam.trim()) return;
      const r = await fetch(base + '/api/me/teams', { method:'POST', headers, body: JSON.stringify({ team: newTeam.trim() })});
      if (!r.ok) throw new Error('HTTP ' + r.status);
      setNewTeam(''); await loadTeams(); setMsg('追加しました');
    } catch (e:any) { setError(e.message || '追加失敗'); }
  }

  async function removeTeam(t: string) {
    setMsg(''); setError('');
    try {
      const r = await fetch(base + '/api/me/teams/' + encodeURIComponent(t), { method:'DELETE', headers });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      await loadTeams(); setMsg('削除しました');
    } catch (e:any) { setError(e.message || '削除失敗'); }
  }

  async function saveSteps(e: React.FormEvent) {
    e.preventDefault(); setMsg(''); setError('');
    try {
      const payload: any = { steps: Number(steps||'0') };
      if (date) payload.date = date;
      const r = await fetch(base + '/api/me/steps', { method:'POST', headers, body: JSON.stringify(payload) });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      setMsg('保存しました');
    } catch (e:any) { setError(e.message || '保存失敗'); }
  }

  useEffect(()=>{ loadTeams(); loadAllTeams(); }, []);

  if (!access) {
    return <main><div className="card"><h2>マイページ</h2><p>ログインしてください。</p></div></main>;
  }

  return (
    <>
      <main>
        <div className="card">
          <h2>マイページ</h2>
          <h3>お気に入りチーム</h3>
          <form onSubmit={addTeam} className="row" style={{gap:'0.5rem'}}>
            <select value={newTeam} onChange={e=>setNewTeam(e.target.value)}>
              <option value="">チームを選択</option>
              {allTeams.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <button type="submit" disabled={!newTeam}>追加</button>
          </form>
          <ul>
            {teams.map(t => (
              <li key={t} style={{display:'flex', gap:8, alignItems:'center'}}>
                <span>{t}</span>
                <button onClick={()=>removeTeam(t)} style={{fontSize:'0.8rem'}}>削除</button>
              </li>
            ))}
            {teams.length === 0 && <li>なし</li>}
          </ul>

          <h3>今日の歩数</h3>
          <form onSubmit={saveSteps} className="row" style={{gap:'0.5rem', flexWrap:'wrap'}}>
            <input type="date" value={date} onChange={e=>setDate(e.target.value)} />
            <input type="number" min="0" step="1" placeholder="steps" value={steps} onChange={e=>setSteps(e.target.value)} />
            <button type="submit">保存</button>
          </form>
          {msg && <p className="small">{msg}</p>}
          {error && <p className="error">{error}</p>}
        </div>
      </main>
      <FooterNav />
    </>
  );
}
