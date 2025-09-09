import { useEffect, useMemo, useState } from 'react';
import PitcherTable from '../components/PitcherTable';

// Derive base path for API
const base = new URL('.', window.location.href).pathname.replace(/\/$/, '');

async function fetchJSON(path: string) {
  const u = base + path;
  const r = await fetch(u);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export default function MiniView() {
  const [date, setDate] = useState<string>(()=> new Date().toISOString().slice(0,10));
  const [team, setTeam] = useState<string>(()=> localStorage.getItem('favTeam') || '');
  const [games, setGames] = useState<any[]>([]);
  const [orders, setOrders] = useState<Record<string, any>>({}); // key: gamePk:side -> lineupSlots
  const [paMap, setPaMap] = useState<Record<string, Record<string,string[]>>>({}); // key -> name -> seq
  const [pitchers, setPitchers] = useState<Record<string, any[]>>({}); // key -> pitchers array

  useEffect(()=>{ localStorage.setItem('favTeam', team); }, [team]);

  useEffect(()=>{ (async()=>{
    try {
      const params = new URLSearchParams({ date });
      if (team) params.append('team', team);
      const j = await fetchJSON('/api/games?' + params.toString());
      setGames(j.games || []);
    } catch {}
  })(); }, [date, team]);

  useEffect(()=>{ (async()=>{
    // fetch lineup and PA for each relevant game
    const entries: Array<{ key: string; gamePk: number; side: 'home'|'away' }>= [];
    for (const g of games) {
      const sideGuess = (g.home?.team === team) ? 'home' : (g.away?.team === team ? 'away' : null);
      if (!sideGuess) { continue; }
      const side = sideGuess as 'home'|'away';
      entries.push({ key: `${g.gamePk}:${side}`, gamePk: g.gamePk, side });
    }
    const ord: Record<string, any> = {};
    const pa: Record<string, Record<string,string[]>> = {};
    const pit: Record<string, any[]> = {};
    await Promise.all(entries.map(async e => {
      try {
        const o = await fetchJSON(`/api/games/${e.gamePk}/batting-order?side=${e.side}`);
        ord[e.key] = o.slots || [];
      } catch {}
      try {
        const pr = await fetchJSON(`/api/games/${e.gamePk}/plate-appearances?side=${e.side}`);
        const m: Record<string,string[]> = {};
        for (const p of pr.players || []) { m[p.name] = p.pa || []; }
        pa[e.key] = m;
      } catch {}
      try {
        const qr = await fetchJSON(`/api/games/${e.gamePk}/pitchers?side=${e.side}`);
        pit[e.key] = qr.pitchers || [];
      } catch {}
    }));
    setOrders(ord);
    setPaMap(pa);
    setPitchers(pit);
  })(); }, [games, team]);

  const month = useMemo(()=> date.slice(0,7), [date]);

  return (
    <main>
      <div className="card">
        <h3>ミニビュー</h3>
        <div className="row">
          <label>日付 <input type="date" value={date} onChange={e=>setDate(e.target.value)} /></label>
          <label>チーム <input value={team} onChange={e=>setTeam(e.target.value)} placeholder="例: New York Yankees" /></label>
        </div>
      </div>
      <div style={{height:12}} />
      <div className="card">
        {!team ? (<p className="small">チームを入力してください。</p>) : (
          games.filter(g=> g.home?.team===team || g.away?.team===team).map(g=>{
            const side: 'home'|'away' = g.home.team===team? 'home':'away';
            const key = `${g.gamePk}:${side}`;
            const slots = orders[key] || [];
            const pa = paMap[key] || {};
            const opponent = side==='home'? g.away.team : g.home.team;
            return (
              <div key={key} style={{marginTop:8}}>
                <div className="row"><b>{team}</b> {side==='home'? 'vs':'@'} {opponent} <span className="small" style={{marginLeft:6}}>gamePk={g.gamePk}</span></div>
                <table style={{width:'100%', borderCollapse:'collapse', fontSize:13}}>
                  <tbody>
                    {slots.length? slots.map((s:any)=> (
                      <>
                        <tr key={`${key}:slot:${s.slot}`} style={{background:'#fafafa'}}>
                          <td colSpan={2}><b>{s.slot}番</b></td>
                        </tr>
                        {s.stints.map((t:any)=> (
                          <tr key={`${key}:${t.name}`}>
                            <td>{t.name}{t.note? <span className="small" style={{marginLeft:6,color:'#555'}}>({t.note})</span>: null}</td>
                            <td style={{textAlign:'right'}}>{(pa[t.name]||[]).join(' ')}</td>
                          </tr>
                        ))}
                      </>
                    )) : (
                      <tr><td className="small">打順情報がありません</td></tr>
                    )}
                  </tbody>
                </table>
                <div style={{marginTop:10}}>
                  <details>
                    <summary style={{cursor:'pointer'}}><b>投手/捕手 成績</b></summary>
                    <div style={{marginTop:6}}>
                      <PitcherTable pitchers={(pitchers[key]||[])} />
                    </div>
                  </details>
                </div>
              </div>
            );
          })
        )}
      </div>
    </main>
  );
}
