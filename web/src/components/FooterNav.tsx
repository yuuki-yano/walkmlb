import { Link, useLocation } from 'react-router-dom';

export default function FooterNav() {
  const loc = useLocation();
  const is = (p: string) => loc.pathname === p;
  const loggedIn = !!localStorage.getItem('access_token');
  const doLogout = async () => {
    const base = new URL('.', window.location.href).pathname.replace(/\/$/, '');
    const refresh = localStorage.getItem('refresh_token');
    try {
      if (refresh) {
        await fetch(base + '/api/auth/logout', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ refresh_token: refresh }) });
      }
    } catch {}
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    // navigate to login
    window.location.hash = '#/login';
  };
  return (
    <nav className="footer-nav">
  <Link to="/" style={{opacity:is('/')?1:.7}}>TOP</Link>
  <Link to="/calendar" style={{opacity:is('/calendar')?1:.7}}>カレンダー</Link>
  {loggedIn ? (
    <>
      <Link to="/me" style={{opacity:is('/me')?1:.7}}>マイページ</Link>
      <a onClick={doLogout} style={{opacity:1, cursor:'pointer'}}>ログアウト</a>
    </>
  ) : (
    <>
      <Link to="/login" style={{opacity:is('/login')?1:.7}}>ログイン</Link>
      <Link to="/signup" style={{opacity:is('/signup')?1:.7}}>新規登録</Link>
    </>
  )}
  {/* <Link to="/users" style={{opacity:is('/users')?1:.7}}>ユーザー</Link> */}
    </nav>
  );
}
