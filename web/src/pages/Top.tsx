import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import FooterNav from '../components/FooterNav';

// Derive base path for API (works when app is mounted under a subpath)
const base = new URL('.', window.location.href).pathname.replace(/\/$/, '');

function readDateFromURL(): string | null {
  // Support HashRouter: parse query after '#'
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
  const hash = window.location.hash || '#/';
  const [path, qs] = hash.split('?');
  const sp = new URLSearchParams(qs || '');
  if (value === null || value === '') sp.delete(key); else sp.set(key, value);
  const newHash = path + (sp.toString() ? `?${sp.toString()}` : '');
  if (newHash !== hash) window.history.replaceState(null, '', newHash);
}

async function fetchJSON(path: string) {
  const u = base + path;
  const r = await fetch(u);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export default function Top() {
  const [date, setDate] = useState<string>(()=> readDateFromURL() || new Date().toISOString().slice(0,10));
  const [teams, setTeams] = useState<string[]>([]);
  const [team, setTeam] = useState<string>(()=> localStorage.getItem('favTeam') || '');
  const [steps, setSteps] = useState<number | null>(null);
  const [games, setGames] = useState<any[]>([]);
  const [serverDefaults, setServerDefaults] = useState<{ base: number; perHit: number; perHR: number; perError: number; perSO: number } | null>(null);
  const [loadingGames, setLoadingGames] = useState(false);
  const [loadingPlayers, setLoadingPlayers] = useState(false);
  const [playerResults, setPlayerResults] = useState<Array<{
    gamePk: number;
    side: 'home'|'away';
    opponent: string;
    label: string; // e.g., vs OPP or @ OPP
  base: number;
  contrib: number; // per-player contribution sum (without base)
    total: number;
    list: Array<{ name: string, steps: number }>;
    pa?: Record<string,string[]>; // plate appearances per player (sequence)
  pitchers?: Array<any>; // extended pitcher stats
  appearanceOrder?: Record<number, number>;
  lineupSlots?: Array<{ slot: number; stints: Array<{ name: string; note?: string }> }>;
  }>>([]);
  const [expandedPA, setExpandedPA] = useState<Record<string, boolean>>({});
  const month = useMemo(()=> date.slice(0,7), [date]);

  useEffect(()=>{(async()=>{
    try {
      // Reuse backend calendar teams endpoint
      const j = await fetchJSON('/api/calendar/teams');
      setTeams(j.teams || []);
    } catch {}
    // Fetch server default settings once
    try {
      const s = await fetchJSON('/api/steps/settings');
      setServerDefaults({
        base: Number(s.base ?? 6000),
        perHit: Number(s.player?.perHit ?? -100),
        perHR: Number(s.player?.perHR ?? -300),
        perError: Number(s.player?.perError ?? 50),
        perSO: Number(s.player?.perSO ?? 100),
      });
    } catch {}
  })();},[]);

  useEffect(()=>{ localStorage.setItem('favTeam', team); }, [team]);

  // Keep date in sync if URL hash query changes (e.g., navigating with links that include ?date=)
  useEffect(()=>{
    const onHashChange = () => {
      const d = readDateFromURL();
      if (d) setDate(prev => prev !== d ? d : prev);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  // Update URL ?date= when date changes
  useEffect(()=>{
    setHashQueryParam('date', date);
  }, [date]);

  async function calcGoal() {
    const params = new URLSearchParams({ date });
    if (team) params.append('team', team);
  const j = await fetchJSON('/api/steps/goal?' + params.toString());
    setSteps(j.steps);
  }

  async function loadGames() {
    setLoadingGames(true);
    try {
      const params = new URLSearchParams({ date });
      if (team) params.append('team', team);
      const j = await fetchJSON('/api/games?' + params.toString());
      setGames(j.games || []);
    } finally {
      setLoadingGames(false);
    }
  }

  useEffect(()=>{ loadGames(); }, [date, team]);

  // Auto-calc goal whenever date changes and no team selected
  useEffect(()=>{ (async()=>{ if (!team) { try { await calcGoal(); } catch {} } })(); }, [date, team]);

  function readLocalSettings() {
    try {
      const global = JSON.parse(localStorage.getItem('playerSettings')||'null');
      const dailyMap = JSON.parse(localStorage.getItem('playerSettingsDaily')||'null') || {};
      const daily = (date && team && dailyMap?.[date]?.[team]) || null;
      // base and per-weights: prefer global overrides if present; else server defaults; else hard-coded fallback
      const baseVal = Number((global && global.base) ?? serverDefaults?.base ?? 6000);
      const perHit = Number((global && global.perPlayer?.perHit) ?? serverDefaults?.perHit ?? -100);
      const perHR = Number((global && global.perPlayer?.perHR) ?? serverDefaults?.perHR ?? -300);
      const perError = Number((global && global.perPlayer?.perError) ?? serverDefaults?.perError ?? 50);
      const perSO = Number((global && global.perPlayer?.perSO) ?? serverDefaults?.perSO ?? 100);
      // merge overrides: daily wins over global
      const mergedOverrides: Record<string, any> = { ...(global?.overrides||{}) };
      if (daily && daily.overrides) {
        for (const [name, vals] of Object.entries(daily.overrides)) {
          mergedOverrides[name] = { ...(mergedOverrides[name]||{}), ...(vals as any) };
        }
      }
      return { base: baseVal, perHit, perHR, perError, perSO, overrides: mergedOverrides };
    } catch {}
    return { base: serverDefaults?.base ?? 6000, perHit: serverDefaults?.perHit ?? -100, perHR: serverDefaults?.perHR ?? -300, perError: serverDefaults?.perError ?? 50, perSO: serverDefaults?.perSO ?? 100, overrides: {} };
  }

  async function calcPerPlayerForGame(game: any, side: 'home'|'away') {
    // fetch counts once from API
    const j = await fetchJSON(`/api/steps/goal/game/${game.gamePk}/players?side=${side}`);
    // plate appearances (optional; ignore errors)
    let paMap: Record<string,string[]> = {};
    let orderMap: Record<string, number> = {};
    let lineupSlots: Array<{ slot: number; stints: Array<{ name: string; note?: string }>}> = [];
    try {
      const paRes = await fetchJSON(`/api/games/${game.gamePk}/plate-appearances?side=${side}`);
      for (const p of paRes.players || []) {
        paMap[p.name] = p.pa || [];
      }
    } catch {}
    // pitchers (extended stats)
    let pitchers: any[] = [];
    try {
      const pr = await fetchJSON(`/api/games/${game.gamePk}/pitchers?side=${side}`);
      pitchers = pr.pitchers || [];
    } catch {}
    // batting order and substitutions
    try {
      const ordRes = await fetchJSON(`/api/games/${game.gamePk}/batting-order?side=${side}`);
      orderMap = ordRes.nameToOrder || {};
      lineupSlots = (ordRes.slots || []).map((s: any)=> ({ slot: s.slot, stints: s.stints.map((t: any)=> ({ name: t.name, note: t.note })) }));
    } catch {}
    const settings = readLocalSettings();
    // Build contribution per player
    const byName: Record<string, number> = {};
    const add = (arr: Array<{ name: string, hits?: number, homeRuns?: number, errors?: number, strikeOuts?: number }>, defaultW: number, key: 'hits'|'homeRuns'|'errors'|'strikeOuts') => {
      const mapKey = (k: typeof key) => {
        switch (k) {
          case 'hits': return 'perHit';
          case 'homeRuns': return 'perHR';
          case 'errors': return 'perError';
          case 'strikeOuts': return 'perSO';
        }
      };
      for (const p of arr || []) {
        const n = p.name;
        const c = Number((p as any)[key] || 0);
        // per-player override if available
        const ov = (settings as any).overrides?.[n] as any;
        const overrideKey = mapKey(key) as 'perHit'|'perHR'|'perError'|'perSO';
        const w = (ov && typeof ov[overrideKey] === 'number') ? ov[overrideKey] : defaultW;
        byName[n] = (byName[n] || 0) + (w * c);
      }
    };
    add(j.players.hits || [], settings.perHit, 'hits');
    add(j.players.homeRuns || [], settings.perHR, 'homeRuns');
    add(j.players.errors || [], settings.perError, 'errors');
    add(j.players.strikeOuts || [], settings.perSO, 'strikeOuts');
  // Build list and sort by batting order if available; else by steps desc
  let list = Object.entries(byName).map(([name, steps])=>({ name, steps, order: orderMap[name] || 99999 }));
  list.sort((a,b)=> a.order - b.order || b.steps - a.steps);
  const listOut = list.map(({name, steps})=> ({ name, steps }));
  const contrib = list.reduce((s,x)=> s + x.steps, 0);
  const total = Math.max(0, Math.trunc(settings.base + contrib));
    const opponent = side === 'home' ? game.away.team : game.home.team;
    const label = side === 'home' ? `vs ${opponent}` : `@ ${opponent}`;
  return { gamePk: game.gamePk, side, opponent, label, base: settings.base, contrib, total, list: listOut, pa: paMap, lineupSlots, pitchers };
  }

  // Auto-calc per-player results for the selected team (home or away)
  useEffect(()=>{
    (async()=>{
      try {
        if (!team) { setPlayerResults([]); return; }
        // pick games of the selected team (API already filtered, but double-check)
        const targetGames = (games || []).filter(g => g?.home?.team === team || g?.away?.team === team);
        if (targetGames.length === 0) { setPlayerResults([]); return; }
        setLoadingPlayers(true);
        const results = await Promise.all(targetGames.map(async g => {
          const side: 'home'|'away' = g.home.team === team ? 'home' : 'away';
          return calcPerPlayerForGame(g, side);
        }));
        setPlayerResults(results);
      } catch (e) {
        setPlayerResults([]);
      } finally { setLoadingPlayers(false); }
    })();
  }, [games, team, serverDefaults]);

  // Derived displayed steps: if team selected, use computed combined; else use general goal
  const displayedSteps = (() => {
    if (team) {
      if (playerResults.length === 0) return null; // loading or no games
      const baseOnce = playerResults[0]?.base ?? 0;
      const contribSum = playerResults.reduce((s, r) => s + (r.contrib || 0), 0);
      return Math.max(0, Math.trunc(baseOnce + contribSum));
    }
    return steps;
  })();

  return (
    <>
      <main>
        <div className="card">
          <div className="row">
            <label>日付 <input type="date" value={date} onChange={e=>setDate(e.target.value)} /></label>
            <label>チーム
              <select value={team} onChange={e=>setTeam(e.target.value)}>
                <option value="">(全体)</option>
                {teams.map(t=> <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
          </div>
          <div className="center">
            <div className="circle">
              <div className="steps">{displayedSteps!==null? displayedSteps.toLocaleString() : '—'}</div>
            </div>
          </div>
          <div className="center small">歩</div>
              <div className="center small"><Link to={team ? `/settings?date=${encodeURIComponent(date)}&team=${encodeURIComponent(team)}` : '/settings'}>設定（ローカル保存）</Link></div>
        </div>

        <div style={{ height: 12 }} />
        <div className="card">
          <h3>結果（{date}{team? ` / ${team}`: ''}）</h3>
          {!team ? (
            <p className="small">チームを選択してください。</p>
          ) : games.length === 0 ? (
            <p className="small">試合がありません</p>
          ) : (loadingGames || loadingPlayers || playerResults.length === 0) ? (
            <p className="small">計算中…</p>
          ) : (
            <>
              {/* Combined total to match the circle */}
              <div className="row" style={{marginBottom:8}}>
                <b>合計:</b> <span className="steps" style={{fontWeight:800, marginLeft:6}}>{displayedSteps!==null? displayedSteps.toLocaleString(): '—'}</span> 歩
              </div>
              {playerResults.map(r=> (
                <div key={r.gamePk} style={{marginTop:12}}>
                  <div className="row"><b>対象:</b> {team} {r.label} <span style={{marginLeft:8}}>gamePk={r.gamePk}</span></div>
                  <div className="row"><b>合計:</b> <span className="steps" style={{fontWeight:800}}>{r.total.toLocaleString()}</span> 歩</div>
                  <div style={{marginTop:8}}>
                    <table style={{width:'100%', borderCollapse:'collapse'}}>
                      <thead>
                        <tr><th style={{textAlign:'left'}}>選手</th><th style={{textAlign:'right'}}>歩数</th></tr>
                      </thead>
                      <tbody>
                        {/* If we have lineupSlots, render grouped by batting order with substitution notes */}
                        {r.lineupSlots && r.lineupSlots.length ? (
                          r.lineupSlots.map(slot => (
                            <>
                              <tr key={`${r.gamePk}:slot:${slot.slot}`} style={{background:'#fafafa'}}>
                                <td colSpan={2}><b>{slot.slot}番</b></td>
                              </tr>
                              {slot.stints.map(st => {
                                const key = `${r.gamePk}:${st.name}`;
                                const paSeq = r.pa?.[st.name] || [];
                                const open = expandedPA[key];
                                const stepsRow = r.list.find(x=> x.name === st.name);
                                return (
                                  <>
                                    <tr key={key} style={{cursor: paSeq.length? 'pointer':'default'}} onClick={()=>{ if(paSeq.length) setExpandedPA(s=>({...s,[key]:!open})); }}>
                                      <td>{st.name}{st.note? <span className="small" style={{marginLeft:6,color:'#555'}}>({st.note})</span>: null}</td>
                                      <td style={{textAlign:'right'}}>{stepsRow? Math.trunc(stepsRow.steps).toLocaleString() : '—'}</td>
                                    </tr>
                                    {paSeq.length ? (
                                      <tr key={key+'-pa'}>
                                        <td colSpan={2} style={{background:'#f7f9fc', fontSize:12, padding:'4px 8px'}}>
                                          打席: {paSeq.join(' ')}
                                        </td>
                                      </tr>
                                    ) : null}
                                  </>
                                );
                              })}
                            </>
                          ))
                        ) : (
                          r.list.map(p=> {
                          const key = r.gamePk + ':' + p.name;
                          const paSeq = r.pa?.[p.name] || [];
                          const open = expandedPA[key];
                          return (
                            <>
                              <tr key={key} style={{cursor: paSeq.length? 'pointer':'default'}} onClick={()=>{ if(paSeq.length) setExpandedPA(s=>({...s,[key]:!open})); }}>
                                <td>{p.name}</td>
                                <td style={{textAlign:'right'}}>{Math.trunc(p.steps).toLocaleString()}</td>
                              </tr>
                              {paSeq.length ? (
                                <tr key={key+'-pa'}>
                                  <td colSpan={2} style={{background:'#f7f9fc', fontSize:12, padding:'4px 8px'}}>
                                    打席: {paSeq.join(' ')}
                                  </td>
                                </tr>
                              ) : null}
                            </>
                          );
                        })
                        )}
                      </tbody>
                    </table>
                    {/* Pitchers below batters */}
                    {r.pitchers && r.pitchers.length ? (
                      <div style={{marginTop:8}}>
                        <div style={{marginTop:6}}>
                          <table style={{width:'100%', borderCollapse:'collapse'}}>
                              <thead>
                                <tr>
                                  <th style={{textAlign:'left'}}>投手/捕手</th>
                                  <th>IP</th><th>R</th><th>ER</th><th>H</th><th>HR</th><th>SO</th><th>BB</th><th>WP</th><th>BK</th><th>BAA</th><th>PB</th>
                                </tr>
                              </thead>
                              <tbody>
                                {r.pitchers.map((p:any)=> (
                                  <tr key={p.name}>
                                    <td>{p.name}</td>
                                    <td style={{textAlign:'right'}}>{p.IP||'0.0'}</td>
                                    <td style={{textAlign:'right'}}>{p.R??0}</td>
                                    <td style={{textAlign:'right'}}>{p.ER??0}</td>
                                    <td style={{textAlign:'right'}}>{p.H??0}</td>
                                    <td style={{textAlign:'right'}}>{p.HR??0}</td>
                                    <td style={{textAlign:'right'}}>{p.SO??0}</td>
                                    <td style={{textAlign:'right'}}>{p.BB??0}</td>
                                    <td style={{textAlign:'right'}}>{p.WP??0}</td>
                                    <td style={{textAlign:'right'}}>{p.BK??0}</td>
                                    <td style={{textAlign:'right'}}>{p.BAA!=null? p.BAA.toFixed(3): '-'}</td>
                                    <td style={{textAlign:'right'}}>{p.PB??0}</td>
                                  </tr>
                                ))}
                              </tbody>
                          </table>
                        </div>
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
              <br></br><br></br><br></br><br></br>
              {/* <div className="small" style={{marginTop:6}}>設定（ローカル保存）の係数を使用して算出しています。</div> */}
            </>
          )}
        </div>
      </main>
  <FooterNav />
    </>
  );
}
