import { useEffect, useState } from 'react';
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
  const [date, setDate] = useState<string>(()=> readDateFromURL() || new Date().toISOString().slice(0,10));

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
  }, [date]);

  return (
    <>
      <main>
        <div className="card">
          <h2>カレンダー</h2>
          <div className="row">
            <label>日付 <input type="date" value={date} onChange={e=>setDate(e.target.value)} /></label>
          </div>
          <p className="small">日付を変更すると、URL の ?date= が自動で更新されます。</p>
          <p>かみんぐすーん</p>
          {/* <p>右上の静的HTML版はそのまま使えますが、将来的にこちらに置き換え予定です。</p> */}
          {/* <a href="/calendar.html">静的版カレンダーへ</a> */}
        </div>
      </main>
      <FooterNav />
    </>
  );
}
