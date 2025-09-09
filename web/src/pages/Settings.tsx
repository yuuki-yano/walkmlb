import { useEffect, useMemo, useState } from 'react';
import FooterNav from '../components/FooterNav';

type PerPlayer = { perHit: number; perHR: number; perError: number; perSO: number };

type PlayerWeight = { name: string; weight: number };

type SideWeights = {
  hits: PlayerWeight[];
  homeRuns: PlayerWeight[];
  errors: PlayerWeight[];
  strikeOuts: PlayerWeight[];
};

type TeamWeights = { home: SideWeights; away: SideWeights };

function getDefaultSettings(): { base: number; perPlayer: PerPlayer; team: TeamWeights } {
  // Try fetch server defaults
  return { base: 6000, perPlayer: { perHit: -100, perHR: -300, perError: 50, perSO: 100 }, team: { home: { hits: [], homeRuns: [], errors: [], strikeOuts: [] }, away: { hits: [], homeRuns: [], errors: [], strikeOuts: [] } } };
}

export default function Settings() {
  // Derive base path for API (works when app is mounted under a subpath)
  const basePath = new URL('.', window.location.href).pathname.replace(/\/$/, '');
  const fetchJSON = async (path: string) => {
    const url = basePath + path;
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  };

  // Server defaults (from /api/steps/settings) used for placeholders
  const [base, setBase] = useState<number>(6000);
  const [perPlayer, setPerPlayer] = useState<PerPlayer>({ perHit: -100, perHR: -300, perError: 50, perSO: 100 });
  // Global input states (strings allow blanks)
  type PerPlayerStr = Partial<Record<keyof PerPlayer, string>>;
  const [baseInput, setBaseInput] = useState<string>('');
  const [perInputs, setPerInputs] = useState<PerPlayerStr>({});
  const [overrides, setOverrides] = useState<Record<string, Partial<PerPlayer>>>({});
  const [dateParam, setDateParam] = useState<string | null>(null);
  const [teamParam, setTeamParam] = useState<string | null>(null);
  const [teams, setTeams] = useState<string[]>([]);
  const [dailyNames, setDailyNames] = useState<string[]>([]);
  const [dailyOverrides, setDailyOverrides] = useState<Record<string, Partial<PerPlayer>>>({});
  // Keep raw input text to allow blank and negative typing states (daily overrides)
  const [dailyInputs, setDailyInputs] = useState<Record<string, PerPlayerStr>>({});

  // Derived list of player names to render (from overrides keys)
  const playerNames = useMemo(()=> Object.keys(overrides).sort(), [overrides]);
  const dailyPlayerNames = useMemo(()=> Object.keys(dailyOverrides).sort(), [dailyOverrides]);

  useEffect(()=>{
    // read query params for date/team from hash (HashRouter)
    try {
      const hash = window.location.hash || '';
      const qs = hash.includes('?') ? hash.split('?')[1] : '';
      const sp = new URLSearchParams(qs);
      const d = sp.get('date');
      const t = sp.get('team');
      if (d) setDateParam(d);
      if (t) setTeamParam(t);
      if (!t) {
        const fav = localStorage.getItem('favTeam');
        if (fav) setTeamParam(fav);
      }
    } catch {}

    // load from API defaults
  (async()=>{
      try {
    const j = await fetchJSON('/api/steps/settings');
    setBase(j.base);
    setPerPlayer({ perHit: j.player.perHit, perHR: j.player.perHR, perError: j.player.perError, perSO: j.player.perSO });
      } catch {}
    })();
    // load overrides from localStorage
    const s = localStorage.getItem('playerSettings');
    if (s) {
      try {
        const j = JSON.parse(s);
        if (j.base != null) setBaseInput(String(j.base)); else setBaseInput('');
        if (j.perPlayer && typeof j.perPlayer === 'object') {
          setPerInputs({
            perHit: j.perPlayer.perHit != null ? String(j.perPlayer.perHit) : '',
            perHR: j.perPlayer.perHR != null ? String(j.perPlayer.perHR) : '',
            perError: j.perPlayer.perError != null ? String(j.perPlayer.perError) : '',
            perSO: j.perPlayer.perSO != null ? String(j.perPlayer.perSO) : '',
          });
        } else {
          setPerInputs({});
        }
  if (j.overrides && typeof j.overrides === 'object') setOverrides(j.overrides);
      } catch {}
    }
    // load teams for dropdown
    (async()=>{
      try {
        const jt = await fetchJSON('/api/calendar/teams');
        setTeams(jt.teams || []);
      } catch {}
    })();
  },[]);

  // load daily overrides after date/team are set
  useEffect(()=>{
    try {
      const m = JSON.parse(localStorage.getItem('playerSettingsDaily')||'null') || {};
      if (dateParam && teamParam && m?.[dateParam]?.[teamParam]) {
        setDailyOverrides(m[dateParam][teamParam].overrides || {});
      } else {
        setDailyOverrides({});
      }
    } catch { setDailyOverrides({}); }
  }, [dateParam, teamParam]);

  // Sync dailyInputs with names and overrides so blanks appear when unset
  useEffect(()=>{
    setDailyInputs(prev => {
      const next: Record<string, PerPlayerStr> = { ...prev };
      for (const name of dailyNames) {
        const ov = dailyOverrides[name] || {};
        const cur = next[name] || {};
        // initialize only missing; keep user typing
        if (cur.perHit === undefined) cur.perHit = ov.perHit != null ? String(ov.perHit) : '';
        if (cur.perHR === undefined) cur.perHR = ov.perHR != null ? String(ov.perHR) : '';
        if (cur.perError === undefined) cur.perError = ov.perError != null ? String(ov.perError) : '';
        if (cur.perSO === undefined) cur.perSO = ov.perSO != null ? String(ov.perSO) : '';
        next[name] = cur;
      }
      return next;
    });
  }, [dailyNames, dailyOverrides]);

  const save = () => {
    const payload: any = { overrides };
    if (baseInput !== '') payload.base = Number(baseInput);
    const pp: any = {};
    if (perInputs.perHit !== undefined && perInputs.perHit !== '') pp.perHit = Number(perInputs.perHit);
    if (perInputs.perHR !== undefined && perInputs.perHR !== '') pp.perHR = Number(perInputs.perHR);
    if (perInputs.perError !== undefined && perInputs.perError !== '') pp.perError = Number(perInputs.perError);
    if (perInputs.perSO !== undefined && perInputs.perSO !== '') pp.perSO = Number(perInputs.perSO);
    if (Object.keys(pp).length > 0) payload.perPlayer = pp;
    localStorage.setItem('playerSettings', JSON.stringify(payload));
    alert('保存しました');
  };

  const addPlayer = () => {
    const name = prompt('選手名を入力');
    if (!name) return;
    setOverrides(prev => ({ ...prev, [name]: { } }));
  };

  const removePlayer = (name: string) => {
    setOverrides(prev => { const n = { ...prev }; delete n[name]; return n; });
  };

  const setOverride = (name: string, key: keyof PerPlayer, value: number) => {
    setOverrides(prev => ({ ...prev, [name]: { ...prev[name], [key]: value } }));
  };

  // Daily helpers
  const setDailyOverride = (name: string, key: keyof PerPlayer, value: number) => {
    setDailyOverrides(prev => ({ ...prev, [name]: { ...prev[name], [key]: value } }));
  };
  const setDailyInput = (name: string, key: keyof PerPlayer, value: string) => {
    setDailyInputs(prev => ({ ...prev, [name]: { ...(prev[name]||{}), [key]: value } }));
  };
  const parseMaybe = (s?: string) => {
    if (s === undefined || s === '') return undefined;
    const n = Number(s);
    return Number.isFinite(n) ? n : undefined;
  };
  const saveDaily = () => {
    if (!dateParam || !teamParam) { alert('日付とチームを選択してください（TOPから設定リンクで遷移すると自動指定されます）'); return; }
    // Ensure latest typed strings are applied
    const merged: Record<string, Partial<PerPlayer>> = JSON.parse(JSON.stringify(dailyOverrides||{}));
    for (const name of dailyNames) {
      const inp = dailyInputs[name] || {};
      const cur = merged[name] || {};
      const vHit = parseMaybe(inp.perHit); if (vHit === undefined) delete cur.perHit; else cur.perHit = vHit;
      const vHR = parseMaybe(inp.perHR); if (vHR === undefined) delete cur.perHR; else cur.perHR = vHR;
      const vErr = parseMaybe(inp.perError); if (vErr === undefined) delete cur.perError; else cur.perError = vErr;
      const vSO = parseMaybe(inp.perSO); if (vSO === undefined) delete cur.perSO; else cur.perSO = vSO;
      if (Object.keys(cur).length > 0) merged[name] = cur; else delete merged[name];
    }
    const m = JSON.parse(localStorage.getItem('playerSettingsDaily')||'null') || {};
    if (!m[dateParam]) m[dateParam] = {};
    m[dateParam][teamParam] = { overrides: merged };
    localStorage.setItem('playerSettingsDaily', JSON.stringify(m));
    alert('この日付・チームの設定を保存しました');
  };

  // Auto-populate daily player list from actual games of the day
  useEffect(()=>{
    (async()=>{
      if (!dateParam || !teamParam) return;
      try {
        const params = new URLSearchParams({ date: dateParam, team: teamParam });
        const j = await fetchJSON(`/api/games?${params.toString()}`);
        const games = j.games || [];
        // Fetch players for all relevant games in parallel
        const perGamePromises = games.map(async (g: any) => {
          const side = g.home?.team === teamParam ? 'home' : (g.away?.team === teamParam ? 'away' : null);
          if (!side) return [] as string[];
          try {
            const pj = await fetchJSON(`/api/steps/goal/game/${g.gamePk}/players?side=${side}`);
            const names: string[] = [];
            const addNames = (arr: any[]) => (arr||[]).forEach((o:any)=> names.push(o.name));
            addNames(pj.players.hits);
            addNames(pj.players.homeRuns);
            addNames(pj.players.errors);
            addNames(pj.players.strikeOuts);
            return names;
          } catch { return [] as string[]; }
        });
        const namesArrays = await Promise.all(perGamePromises);
        const namesSet = new Set<string>(namesArrays.flat());
        const arr = Array.from(namesSet).sort();
        setDailyNames(arr);
        // ensure dailyOverrides has an entry for each with empty object so inputs render
        setDailyOverrides(prev => {
          const next = { ...prev } as Record<string, Partial<PerPlayer>>;
          for (const n of arr) if (!next[n]) next[n] = {};
          return next;
        });
      } catch {}
    })();
  }, [dateParam, teamParam]);

  return (
    <>
      <main>
        <div className="card">
          <h2>設定</h2>
          {/** 戻るリンク date=yyyy-mm-dd */}
          <div className="row">
              <a href={`?date=${encodeURIComponent(dateParam)}`} style={{float:'right', fontSize:'0.8em'}}>TOPに戻る</a>
          </div>
          <div className="row"><label>ベース（基準歩数） <input type="number" value={baseInput} placeholder={String(base)} onChange={e=>setBaseInput(e.target.value)} style={{width:'8em'}} /></label></div>
          <h3>全体の係数（デフォルト値）</h3>
          <div className="row" style={{gap:'12px', alignItems:'flex-end'}}>
            <label>ヒット <input type="number" value={perInputs.perHit ?? ''} placeholder={String(perPlayer.perHit)} onChange={e=>setPerInputs(p=>({...p, perHit: e.target.value}))} style={{width:'6em'}} /></label>
            <label>ホームラン <input type="number" value={perInputs.perHR ?? ''} placeholder={String(perPlayer.perHR)} onChange={e=>setPerInputs(p=>({...p, perHR: e.target.value}))} style={{width:'6em'}} /></label>
            <label>エラー <input type="number" value={perInputs.perError ?? ''} placeholder={String(perPlayer.perError)} onChange={e=>setPerInputs(p=>({...p, perError: e.target.value}))} style={{width:'6em'}} /></label>
            <label>三振 <input type="number" value={perInputs.perSO ?? ''} placeholder={String(perPlayer.perSO)} onChange={e=>setPerInputs(p=>({...p, perSO: e.target.value}))} style={{width:'6em'}} /></label>
            <button className="primary" onClick={save}>保存</button>
          </div>
          <p className="small">保存した設定はローカルストレージに記録され、再読み込みしても適用されます（負の値も入力できます）。</p>
        </div>

        {/* Daily section */}
        <div className="card">
          <h2>日ごとの選手設定</h2>
          <p className="small">TOPのリンクから来ると、日付とチームが自動で指定されます。この一覧は指定した日付・チームの試合に登場した選手が自動で表示されます。</p>
          <div className="row">
            <label>日付 <input type="date" value={dateParam||''} onChange={e=>setDateParam(e.target.value||null)} /></label>
            <label>チーム
              <select value={teamParam||''} onChange={e=>setTeamParam(e.target.value||null)}>
                <option value="">(選択)</option>
                {teams.map(t=> <option key={t} value={t}>{t}</option>)}
              </select>
            </label>
            <button className="primary" onClick={saveDaily}>この日付・チームの設定を保存</button>
          </div>
          {(!dateParam || !teamParam) ? (
            <p className="small">日付とチームを指定してください。</p>
          ) : dailyPlayerNames.length === 0 ? (
            <p className="small">選手を取得中、または対象の選手がいません。</p>
          ) : (
            <table style={{width:'100%', borderCollapse:'collapse', marginTop:8}}>
              <thead>
                <tr>
                  <th style={{textAlign:'left'}}>選手</th>
                  <th>ヒット</th>
                  <th>ホームラン</th>
                  <th>エラー</th>
                  <th>三振</th>
                </tr>
              </thead>
              <tbody>
                {dailyPlayerNames.map(name => (
                  <tr key={name}>
                    <td style={{textAlign:'left'}}>{name}</td>
                    <td><input type="number" value={(dailyInputs[name]?.perHit ?? '')} placeholder={String(perPlayer.perHit)} onChange={e=>setDailyInput(name, 'perHit', e.target.value)} style={{width:'5em'}} /></td>
                    <td><input type="number" value={(dailyInputs[name]?.perHR ?? '')} placeholder={String(perPlayer.perHR)} onChange={e=>setDailyInput(name, 'perHR', e.target.value)} style={{width:'5em'}} /></td>
                    <td><input type="number" value={(dailyInputs[name]?.perError ?? '')} placeholder={String(perPlayer.perError)} onChange={e=>setDailyInput(name, 'perError', e.target.value)} style={{width:'5em'}} /></td>
                    <td><input type="number" value={(dailyInputs[name]?.perSO ?? '')} placeholder={String(perPlayer.perSO)} onChange={e=>setDailyInput(name, 'perSO', e.target.value)} style={{width:'5em'}} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div><br></br><br></br>
      </main>
      <FooterNav />
    </>
  );
}
