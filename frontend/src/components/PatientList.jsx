import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import ErrorBoundary from './ErrorBoundary';

function RegisterModal({ onClose, onSaved, prefillChatId }) {
  const [form, setForm] = useState({
    name: '', height_cm: '', age: '', is_male: true,
    bale_chat_id: prefillChatId || '',
  });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [recentUsers, setRecentUsers] = useState([]);
  const [newPatient, setNewPatient] = useState(null);
  const [sendResult, setSendResult] = useState(null); // null | 'success' | 'error'

  useEffect(() => {
    api.get('/patients/bale-recent-users').then(r => setRecentUsers(r.data)).catch(() => {});
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSaving(true);
    try {
      const res = await api.post('/patients/', {
        ...form,
        height_cm: parseFloat(form.height_cm),
        age: parseInt(form.age),
        bale_chat_id: form.bale_chat_id || null,
      });
      if (res.data.bale_chat_id) {
        setNewPatient(res.data);
        setSaving(false);
      } else {
        onSaved(res.data);
        onClose();
      }
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to register patient.');
      setSaving(false);
    }
  };

  const handleSendProfile = async () => {
    setSaving(true);
    try {
      await api.post(`/patients/${newPatient.id}/send-profile`);
      setSendResult('success');
    } catch {
      setSendResult('error');
    } finally {
      setSaving(false);
    }
  };

  if (newPatient) {
    return (
      <div className="modal-overlay">
        <div className="modal" onClick={e => e.stopPropagation()}>
          <div className="modal-header">
            <h2>Patient Registered</h2>
            <button className="modal-close" onClick={() => { onSaved(newPatient); onClose(); }}>×</button>
          </div>
          <div className="modal-body" style={{ padding: '28px 24px', textAlign: 'center' }}>
            <div style={{ fontSize: 44, marginBottom: 12 }}>✅</div>
            <p style={{ fontWeight: 600, fontSize: 16, marginBottom: 6 }}>
              {newPatient.name} has been registered.
            </p>
            <p style={{ color: 'var(--gray-600)', marginBottom: 20 }}>
              Would you like to send their profile to their Bale account{' '}
              <strong>#{newPatient.bale_chat_id}</strong> so they can review their details?
            </p>
            {sendResult === 'success' && (
              <div className="alert alert-success">Profile sent successfully via Bale!</div>
            )}
            {sendResult === 'error' && (
              <div className="alert alert-error">Failed to send. Check Bale bot token and chat ID.</div>
            )}
          </div>
          <div className="modal-footer">
            {sendResult ? (
              <button className="btn btn-primary" onClick={() => { onSaved(newPatient); onClose(); }}>
                Close
              </button>
            ) : (
              <>
                <button className="btn btn-ghost" onClick={() => { onSaved(newPatient); onClose(); }}>
                  Skip
                </button>
                <button className="btn btn-primary" onClick={handleSendProfile} disabled={saving}>
                  {saving ? <><span className="spinner" /> Sending…</> : 'Send Profile to Bale'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Register New Patient</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          {error && <div className="alert alert-error">{error}</div>}
          <form id="reg-form" onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Full Name *</label>
              <input className="form-input" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required placeholder="e.g. Ali Hosseini" />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Height (cm) *</label>
                <input className="form-input" type="number" min="100" max="250" value={form.height_cm} onChange={e => setForm(f => ({ ...f, height_cm: e.target.value }))} required placeholder="175" />
              </div>
              <div className="form-group">
                <label className="form-label">Age *</label>
                <input className="form-input" type="number" min="10" max="100" value={form.age} onChange={e => setForm(f => ({ ...f, age: e.target.value }))} required placeholder="35" />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Sex</label>
              <select className="form-select" value={form.is_male ? 'male' : 'female'} onChange={e => setForm(f => ({ ...f, is_male: e.target.value === 'male' }))}>
                <option value="male">Male</option>
                <option value="female">Female</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Bale Account</label>
              {recentUsers.length > 0 && (
                <div style={{ marginBottom: 8 }}>
                  <span className="text-muted" style={{ fontSize: 12, display: 'block', marginBottom: 6 }}>
                    Recent users who started the bot — click to link:
                  </span>
                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                    {recentUsers.map(u => {
                      const selected = form.bale_chat_id === u.chat_id;
                      return (
                        <button
                          key={u.chat_id}
                          type="button"
                          onClick={() => setForm(f => ({ ...f, bale_chat_id: selected ? '' : u.chat_id }))}
                          style={{
                            padding: '5px 12px',
                            borderRadius: 20,
                            border: `2px solid ${selected ? 'var(--primary)' : 'var(--gray-300)'}`,
                            background: selected ? 'var(--primary)' : '#fff',
                            color: selected ? '#fff' : 'var(--gray-700)',
                            cursor: 'pointer',
                            fontSize: 13,
                            fontWeight: selected ? 600 : 400,
                            transition: 'all .15s',
                          }}
                        >
                          {u.first_name}
                          <span style={{ opacity: 0.6, marginLeft: 4, fontSize: 11 }}>#{u.chat_id}</span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
              <input
                className="form-input"
                value={form.bale_chat_id}
                onChange={e => setForm(f => ({ ...f, bale_chat_id: e.target.value }))}
                placeholder="Select above or type Chat ID manually"
              />
              <span className="text-muted">Link this patient to their Bale messenger account.</span>
            </div>
          </form>
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" form="reg-form" type="submit" disabled={saving}>
            {saving ? <><span className="spinner" /> Saving…</> : 'Register Patient'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function PatientList() {
  const navigate = useNavigate();
  const [patients, setPatients] = useState([]);
  const [query, setQuery] = useState('');
  const [showAll, setShowAll] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showRegister, setShowRegister] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/patients/?q=${encodeURIComponent(query)}&active=${!showAll}`);
      setPatients(res.data);
    } catch {
      setPatients([]);
    } finally {
      setLoading(false);
    }
  }, [query, showAll]);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [load]);

  const daysSince = (dateStr) => {
    if (!dateStr) return null;
    return Math.floor((Date.now() - new Date(dateStr)) / 86400000);
  };

  return (
    <ErrorBoundary>
      {showRegister && (
        <RegisterModal
          onClose={() => setShowRegister(false)}
          onSaved={(p) => setPatients(prev => [p, ...prev])}
        />
      )}

      <div className="section-header">
        <h2>Patients</h2>
        <button className="btn btn-primary" onClick={() => setShowRegister(true)}>
          + Register Patient
        </button>
      </div>

      <div className="card">
        <div className="search-bar">
          <input
            className="search-input"
            placeholder="Search by name…"
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          <label className="checkbox-label">
            <input type="checkbox" checked={showAll} onChange={e => setShowAll(e.target.checked)} />
            Show inactive
          </label>
        </div>

        {loading ? (
          <div className="flex-center" style={{ padding: 60 }}><span className="spinner" /></div>
        ) : patients.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">👤</div>
            <h3>No patients found</h3>
            <p>Register your first patient to get started.</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Age</th>
                  <th>Height</th>
                  <th>Last Visit</th>
                  <th>Bale</th>
                  <th>Status</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {patients.map(p => {
                  const days = daysSince(p.last_visit);
                  const isInactive = days == null || days > 21;
                  return (
                    <tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/patients/${p.id}`)}>
                      <td><strong>{p.name}</strong></td>
                      <td>{p.age}</td>
                      <td>{p.height_cm} cm</td>
                      <td>
                        {p.last_visit
                          ? <>
                              {new Date(p.last_visit).toLocaleDateString()}{' '}
                              <span className="text-muted">({days}d ago)</span>
                            </>
                          : <span className="text-muted">Never</span>
                        }
                      </td>
                      <td>
                        {p.bale_chat_id
                          ? <span className="badge badge-green">✓ Linked</span>
                          : <span className="badge badge-red">Not linked</span>
                        }
                      </td>
                      <td>
                        {!p.is_active
                          ? <span className="badge badge-red">Inactive</span>
                          : isInactive
                            ? <span className="badge badge-orange">Overdue</span>
                            : <span className="badge badge-green">Active</span>
                        }
                      </td>
                      <td>
                        <button className="btn btn-ghost btn-sm" onClick={e => { e.stopPropagation(); navigate(`/patients/${p.id}`); }}>
                          View →
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
