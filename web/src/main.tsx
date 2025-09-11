import React from 'react';
import { createRoot } from 'react-dom/client';
import { createHashRouter, RouterProvider } from 'react-router-dom';
import Top from './pages/Top';
import Settings from './pages/Settings';
import Calendar from './pages/Calendar';
import Login from './pages/Login';
import Signup from './pages/Signup';
import Users from './pages/Users';
import Admin from './pages/Admin';
import MyPage from './pages/MyPage';
import './styles.css';

const router = createHashRouter([
  { path: '/', element: <Top /> },
  { path: '/settings', element: <Settings /> },
  { path: '/calendar', element: <Calendar /> },
  { path: '/login', element: <Login /> },
  { path: '/signup', element: <Signup /> },
  { path: '/me', element: <MyPage /> },
  { path: '/users', element: <Users /> },
  { path: '/admin', element: <Admin /> },
]);

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
