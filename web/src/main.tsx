import React from 'react';
import { createRoot } from 'react-dom/client';
import { createHashRouter, RouterProvider } from 'react-router-dom';
import Top from './pages/Top';
import Settings from './pages/Settings';
import Calendar from './pages/Calendar';
import Admin from './pages/Admin';
import './styles.css';

const router = createHashRouter([
  { path: '/', element: <Top /> },
  { path: '/settings', element: <Settings /> },
  { path: '/calendar', element: <Calendar /> },
  { path: '/admin', element: <Admin /> },
]);

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
