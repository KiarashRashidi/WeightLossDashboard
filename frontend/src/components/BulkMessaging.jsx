import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import ErrorBoundary from './ErrorBoundary';

const PRESET_MESSAGES = [
  { id: 'checkin', label: 'Monthly Check-in', text: 'سلام! وقت چکاپ ماهانه شما فرا رسیده است. لطفاً با مطب تماس بگیرید تا نوبت بگیرید. 🏥' },
  { id: 'holiday', label: 'Holiday Greeting', text: 'با آرزوی سلامتی و موفقیت برای شما در ادامه مسیر سلامت‌تان! ❤️' },
  { id: 'motivation', label: 'Motivational', text: 'پیشرفت شما فوق‌العاده است! ادامه دهید و فراموش نکنید که هر قدم کوچک به هدف بزرگ شما نزدیک‌تر می‌شود. 💪' },
];

const FILTERS = [
  { id: 'all',      label: 'All Active Patients' },
  { id: 'inactive', label: 'Inactive 3+ Weeks' },
  { id: 'linked',   label: 'Bale Linked Only' },
];

export default function BulkMessaging() {
  const [patients, setPatients] = useState([]);
  const [filtered, setFiltered] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [filter, setFilter] = useState('all');
  const [preset, setPreset] = useState(PRESET_MESSAGES[0]);
  const [customMsg, setCustomMsg] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadPatients = useCallback(async () => {
    setLoading(true);
    try {
      let res;
      if (filter === 'inactive') {
        res = await api.get('/patients/inactive');
      } else {
        res = await api.get('/patients/?active=true');
      }
      let data = res.data;
      if (filter === 'linked') {
        data = data.filter(p => p.bale_chat_id);
      }
      setPatients(data);
      setFiltered(data);
      setSelected(new Set());
    } catch {
      setPatients([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { loadPatients(); }, [loadPatients]);

  const toggleAll = (checked) => {
    if (checked) {
      setSelected(new Set(filtered.filter(p => p.bale_chat_id).map(p => p.id)));
    } else {
      setSelected(new Set());
    }
  };

  const toggleOne = (id, checked) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (checked) next.add(id); else next.delete(id);
      return next;
    });
  };

  const sendBulk = async () => {
    const message = customMsg.trim() || preset.text;
    if (!message) return;
    if (selected.size === 0) { alert('Select at least one patient.'); return; }

    setSending(true);
    setResult(null);
    try {
      const res = await api.post('/messaging/bulk-send', {
        patient_ids: Array.from(selected),
        message,
      });
      setResult(res.data);
      setSelected(new Set());
    } catch (e) {
      setResult({ error: e.response?.data?.error || 'Bulk send failed.' });
    } finally {
      setSending(false);
    }
  };

  const effectiveMsg = customMsg.trim() || preset.text;
  const eligibleCount = filtered.filter(p => p.bale_chat_id).length;

  return (
    <ErrorBoundary>
      <div className="section-header">
        <h2>💬 Bulk Messaging</h2>
        <span className="text-muted">{selected.size} patient{selected.size !== 1 ? 's' : ''} selected</span>
      </div>

      <div className="grid-2" style={{ gap: 20, alignItems: 'flex-start' }}>
        {/* Left — patient selector */}
        <div className="card">
          <div className="card-title">1. Select Patients</div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
            {FILTERS.map(f => (
              <button
                key={f.id}
                className={`btn btn-sm ${filter === f.id ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setFilter(f.id)}
              >
                {f.label}
              </button>
            ))}
          </div>

          {loading ? (
            <div className="flex-center" style={{ padding: 40 }}><span className="spinner" /></div>
          ) : filtered.length === 0 ? (
            <div className="empty-state" style={{ padding: '20px 0' }}>
              <p>No patients match this filter.</p>
            </div>
          ) : (
            <>
              <label className="checkbox-label mb-16" style={{ paddingBottom: 10, borderBottom: '1px solid var(--gray-100)' }}>
                <input
                  type="checkbox"
                  checked={selected.size === eligibleCount && eligibleCount > 0}
                  onChange={e => toggleAll(e.target.checked)}
                />
                Select all with Bale ({eligibleCount})
              </label>
              <div style={{ maxHeight: 340, overflowY: 'auto' }}>
                {filtered.map(p => (
                  <label key={p.id} className="checkbox-label" style={{ padding: '6px 0', borderBottom: '1px solid var(--gray-50)', display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <input
                        type="checkbox"
                        checked={selected.has(p.id)}
                        disabled={!p.bale_chat_id}
                        onChange={e => toggleOne(p.id, e.target.checked)}
                      />
                      {p.name}
                    </span>
                    {p.bale_chat_id
                      ? <span className="badge badge-green">✓ Bale</span>
                      : <span className="badge badge-red">No Bale</span>
                    }
                  </label>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Right — message composer */}
        <div>
          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-title">2. Compose Message</div>

            <div className="form-group">
              <label className="form-label">Message Template</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                {PRESET_MESSAGES.map(pm => (
                  <button
                    key={pm.id}
                    className={`btn btn-sm ${preset.id === pm.id && !customMsg ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => { setPreset(pm); setCustomMsg(''); }}
                  >
                    {pm.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Custom Message (overrides template)</label>
              <textarea
                className="form-textarea"
                rows={5}
                placeholder="Type your message here, or use a template above…"
                value={customMsg}
                onChange={e => setCustomMsg(e.target.value)}
              />
            </div>

            <div className="alert alert-info" style={{ fontSize: 12 }}>
              <strong>Preview:</strong><br />
              <span style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{effectiveMsg}</span>
            </div>
          </div>

          <div className="card">
            <div className="card-title">3. Send</div>

            {result && !result.error && (
              <div className="alert alert-success" style={{ marginBottom: 12 }}>
                ✅ Sent: {result.sent?.length} &nbsp;|&nbsp;
                ❌ Failed: {result.failed?.length} &nbsp;|&nbsp;
                ⚠ No Bale: {result.no_bale?.length}
              </div>
            )}
            {result?.error && (
              <div className="alert alert-error">{result.error}</div>
            )}

            <button
              className="btn btn-success btn-lg"
              onClick={sendBulk}
              disabled={sending || selected.size === 0 || !effectiveMsg}
              style={{ width: '100%' }}
            >
              {sending
                ? <><span className="spinner" /> Sending to {selected.size} patient{selected.size !== 1 ? 's' : ''}…</>
                : `📤 Send to ${selected.size} Patient${selected.size !== 1 ? 's' : ''}`
              }
            </button>
            {selected.size === 0 && (
              <p className="text-muted text-center" style={{ marginTop: 8 }}>Select patients on the left to enable sending.</p>
            )}
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
}
