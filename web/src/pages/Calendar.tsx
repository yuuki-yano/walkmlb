import { useEffect, useMemo, useState } from 'react';
import FooterNav from '../components/FooterNav';

function readDateFromURL(): string | null {
  try {
    const hash = window.location.hash || '';
    const qs = hash.includes('?') ? hash.split('?')[1] : (window.location.search || '').slice(1);
    if (!qs) return null;
    const sp = new URLSearchParams(qs);
    const d = sp.get('date');
    if (d && /^\d{4}-\d{2}-\d{2}$/.test(d)) return d;
  } catch {}
  return null;
}

function setHashQueryParam(key: string, value: string | null) {
  const hash = window.location.hash || '#/calendar';
  const [path, qs] = hash.split('?');
  const sp = new URLSearchParams(qs || '');
  if (value === null || value === '') sp.delete(key); else sp.set(key, value);
  const newHash = path + (sp.toString() ? `?${sp.toString()}` : '');
  if (newHash !== hash) window.history.replaceState(null, '', newHash);
}

export default function Calendar() {
  const base = new URL('.', window.location.href).pathname.replace(/\/$/, '');
  const [date, setDate] = useState<string>(()=> readDateFromURL() || new Date().toISOString().slice(0,10));
  const [month, setMonth] = useState<string>(()=> (readDateFromURL() || new Date().toISOString().slice(0,10)).slice(0,7));
  const [favTeams, setFavTeams] = useState<string[]>([]);
  const [allTeams, setAllTeams] = useState<string[]>([]);
  const [teamSelect, setTeamSelect] = useState<string>('');
  const [days, setDays] = useState<Array<{date:string; games:any[]}>>([]);
  const [stepsDays, setStepsDays] = useState<Record<string, number>>({});
  const [goalCache, setGoalCache] = useState<Record<string, number>>({});
  // シンプル表示をデフォルト ON
  const [simpleMobile, setSimpleMobile] = useState<boolean>(true);
  const access = localStorage.getItem('access_token');

  // Sync date when URL hash query changes (back/forward or external changes)
  useEffect(()=>{
    const onHashChange = () => {
      const d = readDateFromURL();
      if (d) setDate(prev => prev !== d ? d : prev);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  // Update query param when date changes via input
  useEffect(()=>{
    setHashQueryParam('date', date);
    setMonth(date.slice(0,7));
  }, [date]);

  // Load favorites and team list
  useEffect(()=>{
    (async()=>{
      try {
        if (access) {
          const r = await fetch(base + '/api/me/teams', { headers: { Authorization: 'Bearer ' + access } });
          if (r.ok) {
            const j = await r.json(); setFavTeams(j.teams||[]);
          }
        }
      } catch {}
      try {
        const r = await fetch(base + '/api/calendar/teams');
        if (r.ok) { const j = await r.json(); setAllTeams(j.teams||[]); }
      } catch {}
    })();
  }, [access]);

  // Load games for month for either favorite or selected team
  useEffect(()=>{
    (async()=>{
      const t = teamSelect || favTeams[0] || '';
      if (!t) { setDays([]); return; }
      try {
        const u = new URL(base + '/api/calendar', window.location.origin);
        u.searchParams.set('team', t); u.searchParams.set('month', month);
        const r = await fetch(u.toString());
        if (!r.ok) return;
        const j = await r.json();
        setDays(j.days || []);
      } catch {}
    })();
  }, [teamSelect, favTeams, month]);

  // Load steps for month (personal)
  useEffect(()=>{
    (async()=>{
      if (!access) { setStepsDays({}); return; }
      try {
        const u = new URL(base + '/api/me/steps/range', window.location.origin);
        u.searchParams.set('month', month);
        const r = await fetch(u.toString(), { headers: { Authorization: 'Bearer ' + access } });
        if (!r.ok) return;
        const j = await r.json();
        const m: Record<string, number> = {};
        for (const d of (j.days||[])) m[d.date] = d.steps || 0;
        setStepsDays(m);
      } catch {}
    })();
  }, [month, access]);

  // Compute or fetch daily goal per day (team-based)
  const daysWithGoal = useMemo(()=>{
    const t = teamSelect || favTeams[0] || '';
    return (days||[]).map(d => {
      const key = `${d.date}::${t}`;
      let goal = goalCache[key];
      if (goal === undefined) {
        (async()=>{
          try {
            const u = new URL(base + '/api/steps/goal', window.location.origin);
            u.searchParams.set('date', d.date);
            if (t) u.searchParams.set('team', t);
            const r = await fetch(u.toString());
            if (r.ok) {
              const j = await r.json();
              // unify with Top: just trust server steps (local player overrides not applicable for multi-day view)
              setGoalCache(prev => ({ ...prev, [key]: j.steps||0 }));
            }
          } catch {}
        })();
        goal = 0;
      }
      return { ...d, goal };
    });
  }, [days, teamSelect, favTeams, goalCache, base]);

  // Responsive: detect small width
  useEffect(()=>{
    const check = () => {
      // 画面幅が狭い場合は強制的にシンプル表示を有効化（広くてもユーザー操作までは保持）
      if (window.innerWidth < 520) setSimpleMobile(true);
    };
    window.addEventListener('resize', check);
    return ()=> window.removeEventListener('resize', check);
  }, []);

  return (
    <>
      <main>
        <div className="card">
          <h2>カレンダー</h2>
          <div style={{marginBottom:8}}>
            <label style={{fontSize:12}}><input type="checkbox" checked={simpleMobile} onChange={e=>setSimpleMobile(e.target.checked)} /> シンプル表示(1日1行)</label>
          </div>
          <div className="row" style={{gap:'0.5rem', flexWrap:'wrap'}}>
            <label>日付 <input type="date" value={date} onChange={e=>setDate(e.target.value)} /></label>
            <label>月 <input type="month" value={month} onChange={e=>setMonth(e.target.value)} /></label>
            <label>チーム
              <select value={teamSelect} onChange={e=>setTeamSelect(e.target.value)}>
                <option value="">{favTeams[0] ? `お気に入り(優先): ${favTeams[0]}` : '選択してください'}</option>
                {favTeams.map(t => <option key={'fav_'+t} value={t}>{t} (お気に入り)</option>)}
                {allTeams.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
          </div>
          {simpleMobile ? (
            <div style={{marginTop:8}}>
              <table style={{width:'100%', fontSize:12}}>
                <thead>
                  <tr><th style={{textAlign:'left'}}>日</th><th style={{textAlign:'left'}}>試合</th><th>目標</th><th>実績</th></tr>
                </thead>
                <tbody>
                  {daysWithGoal.map(d=>{
                    const gamesTxt = d.games.length===0 ? '試合なし' : d.games.map((g:any)=> `${g.away.team}@${g.home.team}${(g.home.R!=null&&g.away.R!=null)?' '+g.away.R+'-'+g.home.R:''}`).join(' / ');
                    return (
                      <tr key={d.date}>
                        <td>{d.date.slice(-2)}</td>
                        <td>{gamesTxt}</td>
                        <td style={{textAlign:'right'}}>{d.goal||0}</td>
                        <td style={{textAlign:'right'}}>{stepsDays[d.date]||0}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="calendar-grid" style={{display:'grid', gridTemplateColumns:'repeat(7,1fr)', gap:'4px', marginTop:8}}>
              {daysWithGoal.map(d => (
                <div key={d.date} className="card small" style={{padding:'6px'}}>
                  <div style={{fontWeight:600}}>{d.date.slice(-2)}日</div>
                  {d.games.length === 0 ? (
                    <div className="small" style={{opacity:0.7}}>試合なし</div>
                  ) : d.games.map((g:any)=> (
                    <div key={g.gamePk} style={{marginTop:4}}>
                      <div className="small">{g.away.team} @ {g.home.team}</div>
                      <div className="small">US {g.timeLocal||'-'} / JP {g.timeJP||'-'}</div>
                      <div className="small">{g.status?.detailedState || g.status?.abstractGameState}</div>
                      {typeof g.home.R === 'number' && typeof g.away.R === 'number' && (
                        <div className="small">{g.away.R}-{g.home.R}</div>
                      )}
                    </div>
                  ))}
                  <div className="small" style={{marginTop:6}}>目標: {d.goal||0} 歩</div>
                  <div className="small">実績: {stepsDays[d.date]||0} 歩</div>
                </div>
              ))}
            </div>
          )}
          <p className="small" style={{marginTop:8}}>お気に入りが無い場合はチームを選ぶと表示されます。</p>
          {/* <p>右上の静的HTML版はそのまま使えますが、将来的にこちらに置き換え予定です。</p> */}
          {/* <a href="/calendar.html">静的版カレンダーへ</a> */}
        </div>
      </main>
      <FooterNav />
    </>
  );
}
