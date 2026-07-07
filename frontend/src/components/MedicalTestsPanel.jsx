import React, { useState, useEffect, useCallback } from 'react';
import { toJalaali } from 'jalaali-js';
import api from '../services/api';

// ─── Jalali helpers (kept in sync with PatientProfile.jsx) ────────────────────
function toJalaliDate(isoStr) {
  try {
    const d = new Date(isoStr);
    const { jy, jm, jd } = toJalaali(d.getFullYear(), d.getMonth() + 1, d.getDate());
    return `${jd} ${['Farvardin','Ordibehesht','Khordad','Tir','Mordad','Shahrivar','Mehr','Aban','Azar','Dey','Bahman','Esfand'][jm - 1]} ${jy}`;
  } catch {
    return isoStr;
  }
}

// Field is intentionally doctor-only: never read by chart_service/messaging/forecast
// services, so nothing here should be wired into patient-facing reports or AI prompts.
const NUMERIC_FIELDS = [
  { group: 'Glucose Control', fields: [
    { key: 'fbs',   label: 'FBS',   unit: 'mg/dL' },
    { key: 'hba1c', label: 'HbA1c', unit: '%' },
  ]},
  { group: 'Kidney Function', fields: [
    { key: 'bun',        label: 'BUN', unit: 'mg/dL' },
    { key: 'creatinine', label: 'Cr (Creatinine)', unit: 'mg/dL' },
  ]},
  { group: 'Liver Enzymes', fields: [
    { key: 'alt', label: 'ALT', unit: 'U/L' },
    { key: 'ast', label: 'AST', unit: 'U/L' },
  ]},
  { group: 'Pancreatic Enzymes', fields: [
    { key: 'lipase',  label: 'Lipase',  unit: 'U/L' },
    { key: 'amylase', label: 'Amylase', unit: 'U/L' },
  ]},
  { group: 'Lipid Panel', fields: [
    { key: 'cholesterol_total', label: 'CHOL (Total)', unit: 'mg/dL' },
    { key: 'triglycerides',     label: 'TG',            unit: 'mg/dL' },
    { key: 'hdl',               label: 'HDL',           unit: 'mg/dL' },
    { key: 'ldl',               label: 'LDL',           unit: 'mg/dL' },
  ]},
  { group: 'Vitamins & Hormones', fields: [
    { key: 'vitamin_d',  label: 'Vitamin D',  unit: 'ng/mL' },
    { key: 'b12',        label: 'B12',        unit: 'pg/mL' },
    { key: 'calcitonin', label: 'Calcitonin', unit: 'pg/mL' },
  ]},
];
const ALL_NUMERIC_KEYS = NUMERIC_FIELDS.flatMap(g => g.fields.map(f => f.key));

const emptyForm = () => ({
  recorded_at: new Date().toISOString().slice(0, 10),
  ...Object.fromEntries(ALL_NUMERIC_KEYS.map(k => [k, ''])),
  cbc: '',
  liver_gallbladder_ultrasound: '',
  notes: '',
});

// ─── Add / edit modal ──────────────────────────────────────────────────────────
function TestFormModal({ test, patientId, onClose, onSaved, onDeleted }) {
  const isEdit = !!test;
  const [form, setForm] = useState(() => isEdit ? {
    recorded_at: test.recorded_at ? test.recorded_at.slice(0, 10) : new Date().toISOString().slice(0, 10),
    ...Object.fromEntries(ALL_NUMERIC_KEYS.map(k => [k, test[k] ?? ''])),
    cbc: test.cbc ?? '',
    liver_gallbladder_ultrasound: test.liver_gallbladder_ultrasound ?? '',
    notes: test.notes ?? '',
  } : emptyForm());
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');
  const [confirmDel, setConfirmDel] = useState(false);

  const set = (key) => (e) => setForm(f => ({ ...f, [key]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const payload = { ...form, recorded_at: form.recorded_at ? `${form.recorded_at}T00:00:00` : undefined };
      const res = isEdit
        ? await api.put(`/patients/${patientId}/medical-tests/${test.id}`, payload)
        : await api.post(`/patients/${patientId}/medical-tests`, payload);
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
      await api.delete(`/patients/${patientId}/medical-tests/${test.id}`);
      onDeleted(test.id);
      onClose();
    } catch (err) {
      setError(err.response?.data?.error || 'Delete failed.');
      setDeleting(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 640 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{isEdit ? 'Edit Medical Test' : 'Add Medical Test'}</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>
        <div className="modal-body" style={{ maxHeight: '65vh', overflowY: 'auto' }}>
          {error && <div className="alert alert-error">{error}</div>}
          <p className="text-muted" style={{ fontSize: 12, marginBottom: 14 }}>
            All fields are optional — fill in only the tests that were performed.
          </p>
          <form id="medical-test-form" onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Test Date</label>
              <input className="form-input" type="date" value={form.recorded_at} onChange={set('recorded_at')} />
            </div>

            {NUMERIC_FIELDS.map(({ group, fields }) => (
              <div key={group} style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--gray-500)', margin: '10px 0 6px' }}>
                  {group}
                </div>
                <div className="form-row">
                  {fields.map(({ key, label, unit }) => (
                    <div className="form-group" key={key}>
                      <label className="form-label">{label} {unit && <span className="text-muted">({unit})</span>}</label>
                      <input className="form-input" type="number" step="0.01" value={form[key]} onChange={set(key)} />
                    </div>
                  ))}
                </div>
              </div>
            ))}

            <div className="form-group">
              <label className="form-label">CBC (Complete Blood Count)</label>
              <textarea className="form-textarea" rows={2} value={form.cbc} onChange={set('cbc')}
                placeholder="Free-text result summary" />
            </div>
            <div className="form-group">
              <label className="form-label">Liver &amp; Gallbladder Ultrasound</label>
              <textarea className="form-textarea" rows={2} value={form.liver_gallbladder_ultrasound}
                onChange={set('liver_gallbladder_ultrasound')} placeholder="Imaging findings" />
            </div>
            <div className="form-group">
              <label className="form-label">Notes</label>
              <textarea className="form-textarea" rows={2} value={form.notes} onChange={set('notes')} />
            </div>
          </form>
        </div>
        <div className="modal-footer" style={{ justifyContent: isEdit ? 'space-between' : 'flex-end' }}>
          {isEdit && (
            <button className="btn btn-sm"
              style={{ background: '#fff5f5', color: '#c53030', border: '1px solid #fc8181' }}
              onClick={() => setConfirmDel(true)}>
              🗑 Delete
            </button>
          )}
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button className="btn btn-primary" form="medical-test-form" type="submit" disabled={saving}>
              {saving ? <><span className="spinner" /> Saving…</> : 'Save'}
            </button>
          </div>
        </div>
        {confirmDel && (
          <div style={{ padding: '12px 20px', background: '#fff5f5', borderTop: '2px solid #fc8181',
            borderRadius: '0 0 var(--radius) var(--radius)' }}>
            <p style={{ color: '#c53030', marginBottom: 10, fontWeight: 600 }}>
              ⚠ Delete this test record permanently?
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDel(false)}>Cancel</button>
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

// ─── Main tab component ────────────────────────────────────────────────────────
export default function MedicalTestsPanel({ patientId }) {
  const [tests, setTests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [showAdd, setShowAdd] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(`/patients/${patientId}/medical-tests`);
      setTests(res.data);
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => { load(); }, [load]);

  const onSaved = (t) => setTests(prev => {
    const exists = prev.some(x => x.id === t.id);
    return exists ? prev.map(x => x.id === t.id ? t : x) : [...prev, t];
  });
  const onDeleted = (tid) => setTests(prev => prev.filter(t => t.id !== tid));

  const COLUMNS = [
    { key: 'fbs', label: 'FBS' }, { key: 'hba1c', label: 'HbA1c' },
    { key: 'bun', label: 'BUN' }, { key: 'creatinine', label: 'Cr' },
    { key: 'alt', label: 'ALT' }, { key: 'ast', label: 'AST' },
    { key: 'lipase', label: 'Lipase' }, { key: 'amylase', label: 'Amylase' },
    { key: 'cholesterol_total', label: 'CHOL' }, { key: 'triglycerides', label: 'TG' },
    { key: 'hdl', label: 'HDL' }, { key: 'ldl', label: 'LDL' },
    { key: 'vitamin_d', label: 'Vit D' }, { key: 'b12', label: 'B12' },
    { key: 'calcitonin', label: 'Calcitonin' },
  ];

  if (loading) return <div className="flex-center" style={{ height: 200 }}><span className="spinner" /></div>;

  return (
    <div className="card">
      {showAdd && (
        <TestFormModal patientId={patientId} onClose={() => setShowAdd(false)}
          onSaved={onSaved} />
      )}
      {editing && (
        <TestFormModal test={editing} patientId={patientId} onClose={() => setEditing(null)}
          onSaved={onSaved} onDeleted={onDeleted} />
      )}

      <div className="flex-between mb-16">
        <span className="card-title" style={{ marginBottom: 0 }}>Medical Tests</span>
        <button className="btn btn-primary" onClick={() => setShowAdd(true)}>+ Add Test</button>
      </div>
      <p className="text-muted" style={{ fontSize: 12, marginBottom: 14 }}>
        Doctor-only lab &amp; imaging records. Not shown to the patient and not used in AI-generated reports.
      </p>

      {tests.length === 0 ? (
        <div className="empty-state" style={{ padding: '30px 0' }}>
          <p>No medical tests recorded yet.</p>
        </div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                {COLUMNS.map(c => <th key={c.key}>{c.label}</th>)}
                <th>CBC</th>
                <th>Ultrasound</th>
                <th>Notes</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {[...tests].reverse().map(t => (
                <tr key={t.id}>
                  <td style={{ whiteSpace: 'nowrap' }}>{toJalaliDate(t.recorded_at)}</td>
                  {COLUMNS.map(c => <td key={c.key}>{t[c.key] ?? '—'}</td>)}
                  <td className="text-muted" style={{ maxWidth: 160 }}>{t.cbc || '—'}</td>
                  <td className="text-muted" style={{ maxWidth: 160 }}>{t.liver_gallbladder_ultrasound || '—'}</td>
                  <td className="text-muted" style={{ maxWidth: 160 }}>{t.notes || '—'}</td>
                  <td>
                    <button className="btn btn-ghost btn-sm" style={{ padding: '2px 8px', fontSize: 13 }}
                      onClick={() => setEditing(t)}>
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
  );
}
