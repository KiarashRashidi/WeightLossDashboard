import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import ErrorBoundary from './ErrorBoundary';

function KpiCard({ icon, label, value, sub, color }) {
  return (
    <div className="kpi-card">
      <div className="kpi-icon">{icon}</div>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={{ color }}>{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

function InactivePatientRow({ patient, onSendReminder }) {
  const navigate = useNavigate();
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const sendReminder = async () => {
    if (!patient.bale_chat_id) return;
    setSending(true);
    try {
      const token = localStorage.getItem('jwt_token');
      await api.post('/messaging/send', {
        patient_id: patient.id,
        message: `سلام ${patient.name} عزیز! وقت ویزیت مجدد شما فرا رسیده. لطفاً با مطب تماس بگیرید. 🏥`,
      }, { headers: { Authorization: `Bearer ${token}` } });
      setSent(true);
      onSendReminder(patient.id);
    } catch {
      alert('Failed to send reminder. Check Bale bot token.');
    } finally {
      setSending(false);
    }
  };

  return (
    <tr>
      <td>
        <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/patients/${patient.id}`)}>
          {patient.name}
        </button>
      </td>
      <td>{patient.days_inactive != null ? `${patient.days_inactive} days` : 'Never visited'}</td>
      <td>{patient.bale_chat_id ? <span className="badge badge-green">Linked</span> : <span className="badge badge-red">No Bale</span>}</td>
      <td>
        {sent ? (
          <span className="badge badge-green">✓ Sent</span>
        ) : (
          <button
            className="btn btn-warning btn-sm"
            disabled={!patient.bale_chat_id || sending}
            onClick={sendReminder}
          >
            {sending ? <span className="spinner" /> : '📲 Send Reminder'}
          </button>
        )}
      </td>
    </tr>
  );
}

export default function Dashboard({ notifications }) {
  const navigate = useNavigate();
  const [stats, setStats] = useState({ total: 0, active: 0, avgLoss: null });
  const [inactive, setInactive] = useState([]);
  const [newUsers, setNewUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [patientsRes, inactiveRes] = await Promise.all([
        api.get('/patients/?active=false'),
        api.get('/patients/inactive'),
      ]);
      const patients = patientsRes.data;
      const active = patients.filter(p => p.is_active);

      setStats({
        total: patients.length,
        active: active.length,
        avgLoss: null,
      });
      setInactive(inactiveRes.data);
    } catch {
      // non-critical
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    const nu = notifications.filter(n => n.type === 'new_user');
    setNewUsers(nu);
  }, [notifications]);

  const handleReminderSent = (patientId) => {
    setInactive(prev => prev.filter(p => p.id !== patientId));
  };

  return (
    <ErrorBoundary>
      {newUsers.map(n => (
        <div key={n.id} className="alert alert-info mb-16">
          👤 <strong>New Unregistered User Detected</strong> — Bale Chat ID: <code>{n.bale_chat_id}</code>.
          <button className="btn btn-sm btn-primary" style={{ marginLeft: 12 }} onClick={() => navigate('/patients')}>
            Register Patient
          </button>
        </div>
      ))}

      <div className="kpi-grid">
        <KpiCard icon="👥" label="Total Patients" value={loading ? '…' : stats.total} sub="All time" color="var(--navy)" />
        <KpiCard icon="✅" label="Active Patients" value={loading ? '…' : stats.active} sub="Currently active" color="var(--green)" />
        <KpiCard icon="⚠️" label="Inactive Patients" value={loading ? '…' : inactive.length} sub={`No visit in 3+ weeks`} color="var(--orange)" />
        <KpiCard icon="📊" label="Scale Status" value="Eufy C1" sub="T9146" color="var(--blue)" />
      </div>

      <div className="grid-2" style={{ gap: 20 }}>
        <div className="card">
          <div className="card-title">⚠ Inactive Patients — Action Required</div>
          {loading ? (
            <div className="flex-center" style={{ padding: 40 }}><span className="spinner" /></div>
          ) : inactive.length === 0 ? (
            <div className="empty-state" style={{ padding: '30px 0' }}>
              <div style={{ fontSize: 32 }}>🎉</div>
              <p>All patients are up to date!</p>
            </div>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Patient</th>
                    <th>Inactive For</th>
                    <th>Bale</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {inactive.map(p => (
                    <InactivePatientRow key={p.id} patient={p} onSendReminder={handleReminderSent} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title">🔔 Recent Notifications</div>
          {notifications.length === 0 ? (
            <div className="empty-state" style={{ padding: '30px 0' }}>
              <div style={{ fontSize: 32 }}>✅</div>
              <p>No new notifications</p>
            </div>
          ) : (
            <div style={{ maxHeight: 300, overflowY: 'auto' }}>
              {notifications.slice(0, 15).map(n => (
                <div key={n.id} style={{ padding: '10px 0', borderBottom: '1px solid var(--gray-100)' }}>
                  <span className={`badge ${n.type === 'new_user' ? 'badge-blue' : 'badge-orange'}`}>
                    {n.type === 'new_user' ? 'New User' : 'Inactive'}
                  </span>
                  <div style={{ fontSize: 13, color: 'var(--gray-700)', marginTop: 4 }}>{n.message}</div>
                  <div className="text-muted">{new Date(n.created_at).toLocaleString()}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </ErrorBoundary>
  );
}
