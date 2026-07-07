import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts';
import { toJalaali } from 'jalaali-js';
import api from '../services/api';
import ErrorBoundary from './ErrorBoundary';
import MeasurementPanel from './MeasurementPanel';
import MedicalTestsPanel from './MedicalTestsPanel';
import ReportModal from './ReportModal';

// ─── Jalali helpers (dates shown in Persian calendar, UI labels in English) ───
const JALALI_MONTHS = [
  'Farvardin','Ordibehesht','Khordad','Tir','Mordad','Shahrivar',
  'Mehr','Aban','Azar','Dey','Bahman','Esfand',
];

function toJalaliDate(isoStr) {
  try {
    const d = new Date(isoStr);
    const { jy, jm, jd } = toJalaali(d.getFullYear(), d.getMonth() + 1, d.getDate());
    return `${jd} ${JALALI_MONTHS[jm - 1]} ${jy}`;
  } catch {
    return isoStr;
  }
}

function toJalaliShort(isoStr) {
  try {
    const d = new Date(isoStr);
    const { jy, jm, jd } = toJalaali(d.getFullYear(), d.getMonth() + 1, d.getDate());
    return `${jy}/${String(jm).padStart(2,'0')}/${String(jd).padStart(2,'0')}`;
  } catch {
    return isoStr;
  }
}

// ─── Patient edit modal ────────────────────────────────────────────────────────
function EditPatientModal({ patient, onClose, onSaved }) {
  const [form, setForm] = useState({ ...patient });
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await api.put(`/patients/${patient.id}`, form);
      onSaved(res.data);
      onClose();
    } catch (err) {
      setError(err.response?.data?.error || 'Update failed.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Edit Patient</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          {error && <div className="alert alert-error">{error}</div>}
          <form id="edit-patient-form" onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Full Name</label>
              <input className="form-input" value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))} required />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Height (cm)</label>
                <input className="form-input" type="number" value={form.height_cm}
                  onChange={e => setForm(f => ({ ...f, height_cm: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label className="form-label">Age</label>
                <input className="form-input" type="number" value={form.age}
                  onChange={e => setForm(f => ({ ...f, age: e.target.value }))} required />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Sex</label>
              <select className="form-select" value={form.is_male ? 'male' : 'female'}
                onChange={e => setForm(f => ({ ...f, is_male: e.target.value === 'male' }))}>
                <option value="male">Male</option>
                <option value="female">Female</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">Target / Ideal Weight (kg) <span className="text-muted">(optional)</span></label>
              <input className="form-input" type="number" min="30" max="300" step="0.1" value={form.target_weight || ''}
                onChange={e => setForm(f => ({ ...f, target_weight: e.target.value }))} placeholder="e.g. 75" />
            </div>
            <div className="form-group">
              <label className="form-label">Bale Chat ID</label>
              <input className="form-input" value={form.bale_chat_id || ''}
                onChange={e => setForm(f => ({ ...f, bale_chat_id: e.target.value }))}
                placeholder="Optional" />
            </div>
          </form>
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" form="edit-patient-form" type="submit" disabled={saving}>
            {saving ? <><span className="spinner" /> Saving…</> : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Measurement edit modal ────────────────────────────────────────────────────
function EditMeasurementModal({ measurement, onClose, onSaved, onDeleted }) {
  const [form, setForm] = useState({
    weight:       measurement.weight ?? '',
    body_fat_pct: measurement.body_fat_pct ?? '',
    fat_mass:     measurement.fat_mass ?? '',
    muscle_mass:  measurement.muscle_mass ?? '',
    water_kg:     measurement.water_kg ?? '',
    notes:        measurement.notes ?? '',
  });
  const [saving, setSaving]         = useState(false);
  const [deleting, setDeleting]     = useState(false);
  const [error, setError]           = useState('');
  const [confirmDel, setConfirmDel] = useState(false);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await api.put(
        `/patients/${measurement.patient_id}/measurements/${measurement.id}`,
        form,
      );
      onSaved(res.data);
      onClose();
    } catch (err) {
      setError(err.response?.data?.error || 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await api.delete(
        `/patients/${measurement.patient_id}/measurements/${measurement.id}`,
      );
      onDeleted(measurement.id);
      onClose();
    } catch (err) {
      setError(err.response?.data?.error || 'Delete failed.');
      setDeleting(false);
    }
  };

  const Field = ({ label, fkey }) => (
    <div className="form-group">
      <label className="form-label">{label}</label>
      <input className="form-input" type="number" step="0.1" value={form[fkey]}
        onChange={e => setForm(f => ({ ...f, [fkey]: e.target.value }))} />
    </div>
  );

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Edit Measurement</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        <div className="modal-body">
          {error && <div className="alert alert-error">{error}</div>}
          <div style={{ background: '#ebf8ff', padding: '8px 14px', borderRadius: 8,
            marginBottom: 14, fontSize: 13, color: '#2b6cb0', fontWeight: 600 }}>
            📅 Date: {toJalaliDate(measurement.recorded_at)}
          </div>
          <form id="edit-m-form" onSubmit={handleSave}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Weight (kg) *</label>
                <input className="form-input" type="number" step="0.1" required
                  value={form.weight}
                  onChange={e => setForm(f => ({ ...f, weight: e.target.value }))} />
              </div>
              <Field label="Body Fat (%)" fkey="body_fat_pct" />
            </div>
            <div className="form-row">
              <Field label="Fat Mass (kg)" fkey="fat_mass" />
              <Field label="Muscle (kg)"   fkey="muscle_mass" />
            </div>
            <div className="form-row">
              <Field label="Water (kg)" fkey="water_kg" />
              <div className="form-group">
                <label className="form-label">Notes</label>
                <input className="form-input" value={form.notes}
                  onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
              </div>
            </div>
          </form>
        </div>
        <div className="modal-footer" style={{ justifyContent: 'space-between' }}>
          <button className="btn btn-sm"
            style={{ background: '#fff5f5', color: '#c53030', border: '1px solid #fc8181' }}
            onClick={() => setConfirmDel(true)}>
            🗑 Delete
          </button>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button className="btn btn-primary" form="edit-m-form" type="submit" disabled={saving}>
              {saving ? <><span className="spinner" /> Saving…</> : 'Save Changes'}
            </button>
          </div>
        </div>
        {confirmDel && (
          <div style={{ padding: '12px 20px', background: '#fff5f5',
            borderTop: '2px solid #fc8181',
            borderRadius: '0 0 var(--radius) var(--radius)' }}>
            <p style={{ color: '#c53030', marginBottom: 10, fontWeight: 600 }}>
              ⚠ Delete this measurement permanently?
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDel(false)}>
                Cancel
              </button>
              <button className="btn btn-sm" disabled={deleting}
                style={{ background: '#c53030', color: '#fff' }}
                onClick={handleDelete}>
                {deleting ? 'Deleting…' : 'Yes, Delete'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Export menu ───────────────────────────────────────────────────────────────
function ExportMenu({ patientId }) {
  const [open, setOpen] = useState(false);
  const download = (fmt) => {
    const token = localStorage.getItem('jwt_token');
    const url = `/api/patients/${patientId}/export?format=${fmt}`;
    const a = document.createElement('a');
    a.href = url;
    a.setAttribute('download', '');
    document.body.appendChild(a);
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(blob => {
        const burl = URL.createObjectURL(blob);
        a.href = burl;
        a.click();
        URL.revokeObjectURL(burl);
        document.body.removeChild(a);
      });
    setOpen(false);
  };
  return (
    <div style={{ position: 'relative' }}>
      <button className="btn btn-ghost" onClick={() => setOpen(v => !v)}>📥 Export ▾</button>
      {open && (
        <div style={{ position: 'absolute', top: '100%', right: 0, background: '#fff',
          border: '1px solid var(--gray-200)', borderRadius: 'var(--radius)',
          boxShadow: 'var(--shadow-md)', zIndex: 10, minWidth: 140 }}>
          <button className="btn btn-ghost"
            style={{ width: '100%', justifyContent: 'flex-start', borderRadius: 0 }}
            onClick={() => download('csv')}>📄 CSV</button>
          <button className="btn btn-ghost"
            style={{ width: '100%', justifyContent: 'flex-start', borderRadius: 0 }}
            onClick={() => download('excel')}>📊 Excel</button>
        </div>
      )}
    </div>
  );
}

// ─── BMI helper ───────────────────────────────────────────────────────────────
function bmiLabel(bmi) {
  if (!bmi) return '—';
  if (bmi < 18.5) return 'Underweight';
  if (bmi < 25.0) return 'Normal';
  if (bmi < 30.0) return 'Overweight';
  if (bmi < 35.0) return 'Obese I';
  if (bmi < 40.0) return 'Obese II';
  return 'Obese III';
}
function bmiColor(bmi) {
  if (!bmi) return '#a0aec0';
  if (bmi < 18.5) return '#3182ce';
  if (bmi < 25.0) return '#38a169';
  if (bmi < 30.0) return '#d69e2e';
  return '#e53e3e';
}

// ─── Chart config ──────────────────────────────────────────────────────────────
const CHART_LINES = [
  { key: 'weight',       name: 'Weight (kg)',  color: '#2b6cb0', yAxis: 'left'  },
  { key: 'bmi',          name: 'BMI',          color: '#7b2d8b', yAxis: 'right' },
  { key: 'body_fat_pct', name: 'Body Fat (%)', color: '#e53e3e', yAxis: 'right' },
  { key: 'muscle_mass',  name: 'Muscle (kg)',  color: '#38a169', yAxis: 'left'  },
  { key: 'water_kg',     name: 'Water (kg)',   color: '#3182ce', yAxis: 'left'  },
];

// ─── Main component ────────────────────────────────────────────────────────────
export default function PatientProfile({ socket }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [patient, setPatient]           = useState(null);
  const [measurements, setMeasurements] = useState([]);
  const [loading, setLoading]           = useState(true);
  const [tab, setTab]                   = useState('overview');
  const [showEdit, setShowEdit]         = useState(false);
  const [showReport, setShowReport]     = useState(false);
  const [editingM, setEditingM]         = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting]           = useState(false);
  const [selectedMetrics, setSelectedMetrics] = useState({
    weight: true, bmi: true, body_fat_pct: true, muscle_mass: false, water_kg: false,
  });

  const load = useCallback(async () => {
    try {
      const [pRes, mRes] = await Promise.all([
        api.get(`/patients/${id}`),
        api.get(`/patients/${id}/measurements`),
      ]);
      setPatient(pRes.data);
      setMeasurements(mRes.data);
    } catch {
      navigate('/patients');
    } finally {
      setLoading(false);
    }
  }, [id, navigate]);

  useEffect(() => { load(); }, [load]);

  const onNewMeasurement     = (m)   => setMeasurements(prev => [...prev, m]);
  const onMeasurementSaved   = (upd) => setMeasurements(prev => prev.map(m => m.id === upd.id ? upd : m));
  const onMeasurementDeleted = (mid) => setMeasurements(prev => prev.filter(m => m.id !== mid));

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await api.delete(`/patients/${id}`);
      navigate('/patients');
    } catch {
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  if (loading) return <div className="flex-center" style={{ height: 300 }}><span className="spinner" /></div>;
  if (!patient) return null;

  const chartData = measurements.map(m => ({
    date:         toJalaliShort(m.recorded_at),
    weight:       m.weight,
    bmi:          m.bmi ?? null,
    body_fat_pct: m.body_fat_pct,
    muscle_mass:  m.muscle_mass,
    water_kg:     m.water_kg,
  }));

  const firstW    = measurements[0]?.weight;
  const lastW     = measurements[measurements.length - 1]?.weight;
  const totalLoss = firstW && lastW ? (firstW - lastW).toFixed(1) : null;
  const firstDate = measurements[0]?.recorded_at;
  const lastDate  = measurements[measurements.length - 1]?.recorded_at;

  return (
    <ErrorBoundary>
      {showEdit && (
        <EditPatientModal
          patient={patient}
          onClose={() => setShowEdit(false)}
          onSaved={(p) => setPatient(p)}
        />
      )}
      {showReport && (
        <ReportModal
          patient={patient}
          measurements={measurements}
          onClose={() => setShowReport(false)}
        />
      )}
      {editingM && (
        <EditMeasurementModal
          measurement={editingM}
          onClose={() => setEditingM(null)}
          onSaved={onMeasurementSaved}
          onDeleted={onMeasurementDeleted}
        />
      )}

      {/* Header card */}
      <div className="card mb-20">
        <div className="flex-between">
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/patients')}>← Back</button>
            <div>
              <h2 style={{ fontSize: 20, fontWeight: 700 }}>{patient.name}</h2>
              <span className="text-muted" style={{ fontSize: 13 }}>
                {patient.age} yrs · {patient.height_cm} cm · {patient.is_male ? 'Male' : 'Female'}
                {patient.target_weight && <> · 🎯 Target: {patient.target_weight} kg</>}
                {patient.bale_chat_id && <> · 📲 Bale linked</>}
              </span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <ExportMenu patientId={patient.id} />
            <button className="btn btn-ghost" onClick={() => setShowEdit(true)}>✏️ Edit</button>
            <button
              className="btn btn-ghost"
              style={{ color: '#c53030' }}
              onClick={() => setConfirmDelete(true)}
            >
              🗑 Delete
            </button>
            <button className="btn btn-primary" onClick={() => setShowReport(true)}>
              📊 Report & Send
            </button>
          </div>
        </div>

        {totalLoss !== null && (
          <div style={{ marginTop: 16, display: 'flex', gap: 28, flexWrap: 'wrap', alignItems: 'center' }}>
            <div>
              <span className="text-muted">Starting weight:</span>{' '}
              <strong>{firstW} kg</strong>
              {firstDate && <span className="text-muted" style={{ fontSize: 12 }}> ({toJalaliDate(firstDate)})</span>}
            </div>
            <div>
              <span className="text-muted">Current weight:</span>{' '}
              <strong>{lastW} kg</strong>
              {lastDate && <span className="text-muted" style={{ fontSize: 12 }}> ({toJalaliDate(lastDate)})</span>}
            </div>
            <div>
              <span className="text-muted">Total loss:</span>{' '}
              <strong style={{ color: parseFloat(totalLoss) > 0 ? 'var(--green)' : 'var(--red)' }}>
                {parseFloat(totalLoss) > 0 ? '−' : '+'}{Math.abs(totalLoss)} kg
              </strong>
            </div>
            {(() => {
              const lastM = measurements[measurements.length - 1];
              const currentBmi = lastM?.bmi;
              return currentBmi ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span className="text-muted">Current BMI:</span>{' '}
                  <strong style={{ color: bmiColor(currentBmi) }}>{currentBmi}</strong>
                  <span style={{ fontSize: 11, fontWeight: 600, padding: '1px 8px',
                    borderRadius: 12, background: bmiColor(currentBmi) + '20',
                    color: bmiColor(currentBmi) }}>
                    {bmiLabel(currentBmi)}
                  </span>
                </div>
              ) : null;
            })()}
            <div>
              <span className="text-muted">Visits:</span>{' '}
              <strong>{measurements.length}</strong>
            </div>
          </div>
        )}
      </div>

      {/* Delete confirmation banner */}
      {confirmDelete && (
        <div style={{
          padding: '14px 20px',
          background: '#fff5f5',
          border: '1px solid #fc8181',
          borderRadius: 'var(--radius)',
          marginBottom: 20,
        }}>
          <p style={{ color: '#c53030', fontWeight: 600, marginBottom: 10 }}>
            ⚠ Delete {patient.name}? Their profile will be deactivated and hidden from the patient list.
          </p>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(false)}>
              Cancel
            </button>
            <button
              className="btn btn-sm"
              style={{ background: '#c53030', color: '#fff' }}
              disabled={deleting}
              onClick={handleDelete}
            >
              {deleting ? 'Deleting…' : 'Yes, Delete Patient'}
            </button>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="tabs">
        {['overview', 'measure', 'history', 'labs'].map(t => (
          <button key={t} className={`tab-btn ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>
            {{ overview: '📊 Overview', measure: '⚖️ Measure', history: '📋 History', labs: '🧪 Medical Tests' }[t]}
          </button>
        ))}
      </div>

      {/* Overview tab */}
      {tab === 'overview' && (
        measurements.length < 2 ? (
          <div className="card">
            <div className="empty-state">
              <div className="empty-state-icon">📊</div>
              <h3>Not enough data</h3>
              <p>At least 2 measurements needed to show charts.</p>
              <button className="btn btn-primary mt-12" onClick={() => setTab('measure')}>
                Take First Measurement
              </button>
            </div>
          </div>
        ) : (
          <div className="card">
            <div className="flex-between mb-16">
              <span className="card-title" style={{ marginBottom: 0 }}>Progress Chart</span>
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                {CHART_LINES.map(l => (
                  <label key={l.key} className="checkbox-label">
                    <input type="checkbox" checked={selectedMetrics[l.key]}
                      onChange={e => setSelectedMetrics(prev => ({ ...prev, [l.key]: e.target.checked }))} />
                    <span style={{ color: l.color }}>{l.name}</span>
                  </label>
                ))}
              </div>
            </div>
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--gray-200)" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Legend />
                  {CHART_LINES.filter(l => selectedMetrics[l.key]).map(l => (
                    <Line key={l.key} yAxisId={l.yAxis} type="monotone" dataKey={l.key}
                      name={l.name} stroke={l.color} strokeWidth={2}
                      dot={{ r: 4 }} activeDot={{ r: 6 }} connectNulls />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        )
      )}

      {/* Measure tab */}
      {tab === 'measure' && (
        <MeasurementPanel patient={patient} socket={socket} onMeasurementReady={onNewMeasurement} />
      )}

      {/* History tab */}
      {tab === 'history' && (
        <div className="card">
          <div className="card-title">Measurement History</div>
          {measurements.length === 0 ? (
            <div className="empty-state" style={{ padding: '30px 0' }}>
              <p>No measurements yet.</p>
            </div>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Weight (kg)</th>
                    <th>BMI</th>
                    <th>Body Fat (%)</th>
                    <th>Fat Mass (kg)</th>
                    <th>Muscle (kg)</th>
                    <th>Water (kg)</th>
                    <th>Notes</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {[...measurements].reverse().map(m => (
                    <tr key={m.id}>
                      <td style={{ whiteSpace: 'nowrap' }}>{toJalaliDate(m.recorded_at)}</td>
                      <td><strong>{m.weight}</strong></td>
                      <td>
                        {m.bmi ? (
                          <span style={{ fontWeight: 600, color: bmiColor(m.bmi) }}>
                            {m.bmi}
                            <span style={{ fontSize: 10, fontWeight: 400,
                              marginLeft: 4, color: bmiColor(m.bmi) }}>
                              {bmiLabel(m.bmi)}
                            </span>
                          </span>
                        ) : '—'}
                      </td>
                      <td>{m.body_fat_pct ?? '—'}</td>
                      <td>{m.fat_mass ?? '—'}</td>
                      <td>{m.muscle_mass ?? '—'}</td>
                      <td>{m.water_kg ?? '—'}</td>
                      <td className="text-muted">{m.notes || '—'}</td>
                      <td>
                        <button className="btn btn-ghost btn-sm"
                          style={{ padding: '2px 8px', fontSize: 13 }}
                          onClick={() => setEditingM(m)}>
                          ✏️
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Medical Tests tab */}
      {tab === 'labs' && <MedicalTestsPanel patientId={patient.id} />}
    </ErrorBoundary>
  );
}
