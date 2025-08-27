import { Link, useLocation } from 'react-router-dom';

export default function FooterNav() {
  const loc = useLocation();
  const is = (p: string) => loc.pathname === p;
  return (
    <nav className="footer-nav">
  <Link to="/" style={{opacity:is('/')?1:.7}}>TOP</Link>
  <Link to="/calendar" style={{opacity:is('/calendar')?1:.7}}>カレンダー</Link>
    </nav>
  );
}
