import React, { useEffect, useState, useRef } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { io } from 'socket.io-client';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import ErrorBoundary from './components/ErrorBoundary';
import Login from './components/Login';
import Dashboard from './components/Dashboard';
import PatientList from './components/PatientList';
import PatientProfile from './components/PatientProfile';
import BulkMessaging from './components/BulkMessaging';
import Analytics from './components/Analytics';
import api from './services/api';

function ProtectedRoute({ children }) {
  const { token, loading } = useAuth();
  if (loading) return <div className="flex-center" style={{ height: '100vh' }}><div className="spinner" /></div>;
  return token ? children : <Navigate to="/login" replace />;
}

function NotifBell({ notifications, onClearAll }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const unread = notifications.length;
  return (
    <div style={{ position: 'relative' }} ref={ref}>
      <button className="notif-btn" onClick={() => setOpen(v => !v)} title="Notifications">
        🔔
        {unread > 0 && <span className="notif-badge">{unread > 9 ? '9+' : unread}</span>}
      </button>
      {open && (
        <div className="notif-dropdown">
          <div className="notif-dropdown-header">
            <span>Notifications ({unread})</span>
            {unread > 0 && (
              <button className="btn btn-sm btn-ghost" onClick={() => { onClearAll(); setOpen(false); }}>
                Mark all read
              </button>
            )}
          </div>
          {notifications.length === 0 && (
            <div className="notif-item text-muted text-center" style={{ padding: 20 }}>No new notifications</div>
          )}
          {notifications.slice(0, 10).map(n => (
            <div key={n.id} className="notif-item">
              <span className={`notif-type-tag badge ${n.type === 'new_user' ? 'badge-blue' : 'badge-orange'}`}>
                {n.type === 'new_user' ? 'New User' : 'Inactive'}
              </span>
              <div className="notif-text">{n.message}</div>
              <div className="notif-time">{new Date(n.created_at).toLocaleString()}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [notifications, setNotifications] = useState([]);
  const socketRef = useRef(null);

  useEffect(() => {
    api.get('/notifications/').then(r => setNotifications(r.data)).catch(() => {});

    const socket = io('http://localhost:5000', { transports: ['websocket', 'polling'] });
    socketRef.current = socket;
    socket.on('notification:new', (notif) => {
      setNotifications(prev => [notif, ...prev]);
    });
    return () => socket.disconnect();
  }, []);

  const clearAllNotifs = () => {
    api.put('/notifications/read-all').catch(() => {});
    setNotifications([]);
  };

  const pageTitle = {
    '/': 'Dashboard',
    '/patients': 'Patients',
    '/analytics': 'Analytics',
    '/messaging': 'Bulk Messaging',
  }[location.pathname] || 'SmartWeigh MedDash';

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <h1>⚕ SmartWeigh</h1>
          <span>MedDash</span>
        </div>
        <nav className="sidebar-nav">
          <NavLink to="/" end className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">📊</span> Dashboard
          </NavLink>
          <NavLink to="/patients" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">👥</span> Patients
          </NavLink>
          <NavLink to="/analytics" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">📈</span> Analytics
          </NavLink>
          <NavLink to="/messaging" className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}>
            <span className="nav-icon">💬</span> Bulk Messaging
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          <div style={{ marginBottom: 6, color: 'rgba(255,255,255,.75)', fontSize: 13 }}>Dr. {user?.username}</div>
          <button className="nav-item" style={{ padding: '6px 0', color: 'rgba(255,255,255,.5)', fontSize: 12 }}
            onClick={() => { logout(); navigate('/login'); }}>
            🚪 Sign out
          </button>
        </div>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <span className="topbar-title">{pageTitle}</span>
          <div className="topbar-right">
            <NotifBell notifications={notifications} onClearAll={clearAllNotifs} />
            <span style={{ fontSize: 13, color: 'var(--gray-500)' }}>Dr. {user?.username}</span>
          </div>
        </header>

        <main className="content">
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<Dashboard notifications={notifications} socket={socketRef} />} />
              <Route path="/patients" element={<PatientList />} />
              <Route path="/patients/:id" element={<PatientProfile socket={socketRef} />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/messaging" element={<BulkMessaging />} />
            </Routes>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*" element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          } />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
