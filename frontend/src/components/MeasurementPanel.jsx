import React, { useState, useEffect } from 'react';
import api from '../services/api';

const STATUS_LABELS = {
  idle:     { label: 'Scale Disconnected', color: 'gray',   icon: '⚡' },
  scanning: { label: 'Scanning…',          color: 'orange', icon: '🔍' },
  connected:{ label: 'Scale Connected',    color: 'green',  icon: '⚖️' },
  finished: { label: 'Measurement Done',   color: 'green',  icon: '✅' },
  error:    { label: 'Bluetooth Error',    color: 'red',    icon: '❌' },
};

// BMI classification ──────────────────────────────────────────────────────────
function bmiCategory(bmi) {
  if (bmi === null || bmi === undefined) return null;
  if (bmi < 18.5) return { label: 'Underweight', bg: '#bee3f8', color: '#2b6cb0' };
  if (bmi < 25.0) return { label: 'Normal',       bg: '#c6f6d5', color: '#276749' };
  if (bmi < 30.0) return { label: 'Overweight',   bg: '#fefcbf', color: '#744210' };
  if (bmi < 35.0) return { label: 'Obese I',      bg: '#fed7d7', color: '#9b2c2c' };
  if (bmi < 40.0) return { label: 'Obese II',     bg: '#feb2b2', color: '#7b341e' };
  return                  { label: 'Obese III',    bg: '#fc8181', color: '#63171b' };
}

function bmiColor(bmi) {
  if (!bmi) return '#a0aec0';
  if (bmi < 18.5) return '#3182ce';
  if (bmi < 25.0) return '#38a169';
  if (bmi < 30.0) return '#d69e2e';
  if (bmi < 35.0) return '#e53e3e';
  return '#c53030';
}

// BMI range bar (visual indicator) ────────────────────────────────────────────
function BMIBar({ bmi }) {
  if (!bmi) return null;
  // BMI scale: 15 → 45 mapped to 0-100%
  const MIN = 15, MAX = 45;
  const pct = Math.min(100, Math.max(0, ((bmi - MIN) / (MAX - MIN)) * 100));
  const cat = bmiCategory(bmi);

  return (
    <div style={{ margin: '8px 0 4px' }}>
      <div style={{ position: 'relative', height: 6, background: '#e2e8f0', borderRadius: 4 }}>
        {/* Zone bands */}
        <div style={{ position: 'absolute', left: `${((18.5-MIN)/(MAX-MIN))*100}%`,
          width: `${((25-18.5)/(MAX-MIN))*100}%`, height: '100%',
          background: '#c6f6d5', borderRadius: 2 }} />
        <div style={{ position: 'absolute', left: `${((25-MIN)/(MAX-MIN))*100}%`,
          width: `${((30-25)/(MAX-MIN))*100}%`, height: '100%',
          background: '#fefcbf', borderRadius: 2 }} />
        {/* Needle */}
        <div style={{
          position: 'absolute', left: `${pct}%`, top: -3,
          width: 12, height: 12, borderRadius: '50%',
          background: cat?.color || '#a0aec0',
          border: '2px solid #fff',
          boxShadow: '0 1px 3px rgba(0,0,0,0.3)',
          transform: 'translateX(-50%)',
        }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between',
        fontSize: 9, color: '#a0aec0', marginTop: 3, letterSpacing: 0 }}>
        <span>15</span><span>18.5</span><span>25</span><span>30</span><span>45</span>
      </div>
    </div>
  );
}

// Metric card ─────────────────────────────────────────────────────────────────
function MetricCard({ label, value, unit, color, badge, extra }) {
  return (
    <div className="measure-card" style={{ '--metric-color': color }}>
      <div className="measure-label">{label}</div>
      <div style={{ marginTop: 8 }}>
        <span className="measure-value" style={{ color }}>
          {value ?? '—'}
        </span>
        {unit && <span className="measure-unit" style={{ marginLeft: 3 }}>{unit}</span>}
      </div>
      {badge && (
        <div className="measure-badge"
          style={{ background: badge.bg, color: badge.color }}>
          {badge.label}
        </div>
      )}
      {extra}
    </div>
  );
}

// Main component ──────────────────────────────────────────────────────────────
export default function MeasurementPanel({ patient, socket, onMeasurementReady }) {
  const [bleStatus, setBleStatus] = useState('idle');
  const [liveData, setLiveData]   = useState(null);
  const [saving, setSaving]       = useState(false);
  const [saved, setSaved]         = useState(false);
  const [notes, setNotes]         = useState('');
  const [error, setError]         = useState('');

  const [mode, setMode]             = useState('bluetooth');
  const [manualForm, setManualForm] = useState(() => {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    return { weight: '', body_fat_pct: '', muscle_mass: '', water_kg: '', notes: '', recorded_at: now.toISOString().slice(0, 16) };
  });
  const [manualSaving, setManualSaving] = useState(false);
  const [manualError, setManualError]   = useState('');
  const [manualSaved, setManualSaved]   = useState(false);
  const [manualResult, setManualResult] = useState(null);

  useEffect(() => {
    const sock = socket?.current;
    if (!sock) return;
    const onStatus   = ({ status }) => setBleStatus(status);
    const onData     = (data) => setLiveData(data);
    const onFinished = (data) => { setLiveData(data); setBleStatus('finished'); };
    sock.on('bluetooth:status',   onStatus);
    sock.on('bluetooth:data',     onData);
    sock.on('bluetooth:finished', onFinished);
    return () => {
      sock.off('bluetooth:status',   onStatus);
      sock.off('bluetooth:data',     onData);
      sock.off('bluetooth:finished', onFinished);
    };
  }, [socket]);

  const startScan = async () => {
    setError(''); setSaved(false); setLiveData(null);
    try {
      await api.post('/bluetooth/start', {
        patient_id: patient.id,
        height_cm:  patient.height_cm,
        age:        patient.age,
        is_male:    patient.is_male,
      });
      setBleStatus('scanning');
    } catch {
      setError('Failed to start Bluetooth scan. Is the backend running?');
    }
  };

  const stopScan = async () => {
    try { await api.post('/bluetooth/stop'); setBleStatus('idle'); } catch {}
  };

  const saveMeasurement = async () => {
    if (!liveData) return;
    setSaving(true); setError('');
    try {
      const res = await api.post(`/patients/${patient.id}/measurements`, {
        weight:    liveData.weight,
        impedance: liveData.impedance,
        notes,
      });
      setSaved(true);
      if (onMeasurementReady) onMeasurementReady(res.data);
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to save measurement.');
    } finally {
      setSaving(false);
    }
  };

  const saveManual = async (e) => {
    e.preventDefault();
    setManualSaving(true); setManualError('');
    try {
      const payload = { weight: parseFloat(manualForm.weight) };
      if (manualForm.body_fat_pct) payload.body_fat_pct = parseFloat(manualForm.body_fat_pct);
      if (manualForm.muscle_mass)  payload.muscle_mass  = parseFloat(manualForm.muscle_mass);
      if (manualForm.water_kg)     payload.water_kg     = parseFloat(manualForm.water_kg);
      if (manualForm.notes)        payload.notes        = manualForm.notes;
      if (manualForm.recorded_at)  payload.recorded_at  = manualForm.recorded_at;
      const res = await api.post(`/patients/${patient.id}/measurements`, payload);
      setManualResult({
        weight:       parseFloat(manualForm.weight),
        body_fat_pct: manualForm.body_fat_pct ? parseFloat(manualForm.body_fat_pct) : null,
        muscle_mass:  manualForm.muscle_mass  ? parseFloat(manualForm.muscle_mass)  : null,
        water_kg:     manualForm.water_kg     ? parseFloat(manualForm.water_kg)     : null,
      });
      setManualSaved(true);
      if (onMeasurementReady) onMeasurementReady(res.data);
    } catch (err) {
      setManualError(err.response?.data?.error || 'Failed to save measurement.');
    } finally {
      setManualSaving(false);
    }
  };

  // Compute BMI from live weight + patient height
  const bmi = liveData?.weight && patient.height_cm
    ? parseFloat((liveData.weight / Math.pow(patient.height_cm / 100, 2)).toFixed(1))
    : null;

  const manualBmi = manualResult?.weight && patient.height_cm
    ? parseFloat((manualResult.weight / Math.pow(patient.height_cm / 100, 2)).toFixed(1))
    : null;

  const st = STATUS_LABELS[bleStatus] || STATUS_LABELS.idle;

  const BmiLegend = () => (
    <div className="measure-card" style={{ '--metric-color': '#a0aec0',
      display: 'flex', flexDirection: 'column',
      justifyContent: 'center', gap: 5, padding: '12px 14px' }}>
      <div className="measure-label" style={{ marginBottom: 4 }}>BMI Scale</div>
      {[
        { range: '< 18.5',    label: 'Underweight', color: '#3182ce' },
        { range: '18.5–24.9', label: 'Normal',      color: '#38a169' },
        { range: '25–29.9',   label: 'Overweight',  color: '#d69e2e' },
        { range: '≥ 30',      label: 'Obese',       color: '#e53e3e' },
      ].map(r => (
        <div key={r.label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: r.color, flexShrink: 0 }} />
          <span style={{ fontSize: 10, color: '#4a5568' }}>
            <strong style={{ color: r.color }}>{r.range}</strong> {r.label}
          </span>
        </div>
      ))}
    </div>
  );

  return (
    <div className="card" style={{ marginBottom: 20 }}>

      {/* ── Mode toggle header ── */}
      <div className="flex-between mb-16">
        <span className="card-title" style={{ marginBottom: 0 }}>⚖️ Measurement</span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            className={`btn btn-sm ${mode === 'bluetooth' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setMode('bluetooth')}
          >
            📡 Bluetooth Scale
          </button>
          <button
            className={`btn btn-sm ${mode === 'manual' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setMode('manual')}
          >
            ✏️ Manual Entry
          </button>
          {mode === 'bluetooth' && (
            <div className="ble-status" style={{ marginLeft: 8 }}>
              <span className={`status-dot ${st.color}`} />
              {st.icon} {st.label}
            </div>
          )}
        </div>
      </div>

      {/* ── Bluetooth mode ── */}
      {mode === 'bluetooth' && (
        <>
          {error && <div className="alert alert-error">{error}</div>}

          <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
            {bleStatus === 'idle' || bleStatus === 'error' ? (
              <button className="btn btn-primary" onClick={startScan}>🔍 Start Scan</button>
            ) : bleStatus === 'finished' ? (
              <button className="btn btn-primary" onClick={startScan}>🔄 New Scan</button>
            ) : (
              <button className="btn btn-danger" onClick={stopScan}>⏹ Stop</button>
            )}
          </div>

          {bleStatus === 'scanning' && !liveData && (
            <div className="alert alert-info">
              <span className="spinner" style={{ marginRight: 8 }} />
              Waiting for patient to step on the scale…
            </div>
          )}

          {liveData && (
            <>
              <div className="measure-grid">
                <MetricCard label="Weight"      value={liveData.weight}       unit="kg" color="#2b6cb0" />
                <MetricCard label="BMI"         value={bmi}                   unit=""   color={bmiColor(bmi)} badge={bmiCategory(bmi)} extra={<BMIBar bmi={bmi} />} />
                <MetricCard label="Body Fat"    value={liveData.body_fat_pct} unit="%"  color="#e53e3e" />
                <MetricCard label="Muscle Mass" value={liveData.muscle_mass}  unit="kg" color="#38a169" />
                <MetricCard label="Body Water"  value={liveData.water_kg}     unit="kg" color="#3182ce" />
                <BmiLegend />
              </div>

              {bleStatus === 'finished' && !saved && (
                <div style={{ marginTop: 16 }}>
                  <div className="form-group">
                    <label className="form-label">Notes (optional)</label>
                    <textarea className="form-textarea" rows={2}
                      placeholder="Clinical notes for this visit…"
                      value={notes} onChange={e => setNotes(e.target.value)} />
                  </div>
                  <button className="btn btn-success" onClick={saveMeasurement} disabled={saving}>
                    {saving ? <><span className="spinner" /> Saving…</> : '💾 Save Measurement'}
                  </button>
                </div>
              )}

              {saved && <div className="alert alert-success mt-12">✅ Measurement saved to patient record.</div>}
            </>
          )}
        </>
      )}

      {/* ── Manual entry mode ── */}
      {mode === 'manual' && (
        manualSaved && manualResult ? (
          <>
            <div className="alert alert-success" style={{ marginBottom: 16 }}>✅ Measurement saved manually.</div>
            <div className="measure-grid">
              <MetricCard label="Weight"      value={manualResult.weight}       unit="kg" color="#2b6cb0" />
              <MetricCard label="BMI"         value={manualBmi}                 unit=""   color={bmiColor(manualBmi)} badge={bmiCategory(manualBmi)} extra={<BMIBar bmi={manualBmi} />} />
              <MetricCard label="Body Fat"    value={manualResult.body_fat_pct} unit="%"  color="#e53e3e" />
              <MetricCard label="Muscle Mass" value={manualResult.muscle_mass}  unit="kg" color="#38a169" />
              <MetricCard label="Body Water"  value={manualResult.water_kg}     unit="kg" color="#3182ce" />
              <BmiLegend />
            </div>
            <button className="btn btn-ghost" style={{ marginTop: 16 }} onClick={() => {
              const now = new Date();
              now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
              setManualSaved(false);
              setManualResult(null);
              setManualForm({ weight: '', body_fat_pct: '', muscle_mass: '', water_kg: '', notes: '', recorded_at: now.toISOString().slice(0, 16) });
            }}>
              + New Entry
            </button>
          </>
        ) : (
          <>
            {manualError && <div className="alert alert-error" style={{ marginBottom: 12 }}>{manualError}</div>}
            <form id="manual-measure-form" onSubmit={saveManual}>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Weight (kg) *</label>
                  <input className="form-input" type="number" step="0.1" min="20" max="300" required
                    placeholder="e.g. 85.5"
                    value={manualForm.weight}
                    onChange={e => setManualForm(f => ({ ...f, weight: e.target.value }))} />
                </div>
                <div className="form-group">
                  <label className="form-label">Body Fat (%)</label>
                  <input className="form-input" type="number" step="0.1" min="2" max="70"
                    placeholder="e.g. 28.5"
                    value={manualForm.body_fat_pct}
                    onChange={e => setManualForm(f => ({ ...f, body_fat_pct: e.target.value }))} />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Muscle Mass (kg)</label>
                  <input className="form-input" type="number" step="0.1" min="1" max="150"
                    placeholder="e.g. 35.2"
                    value={manualForm.muscle_mass}
                    onChange={e => setManualForm(f => ({ ...f, muscle_mass: e.target.value }))} />
                </div>
                <div className="form-group">
                  <label className="form-label">Body Water (kg)</label>
                  <input className="form-input" type="number" step="0.1" min="1" max="100"
                    placeholder="e.g. 42.0"
                    value={manualForm.water_kg}
                    onChange={e => setManualForm(f => ({ ...f, water_kg: e.target.value }))} />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Date & Time</label>
                  <input className="form-input" type="datetime-local"
                    value={manualForm.recorded_at}
                    onChange={e => setManualForm(f => ({ ...f, recorded_at: e.target.value }))} />
                </div>
                <div className="form-group">
                  <label className="form-label">Notes</label>
                  <input className="form-input"
                    placeholder="Clinical notes…"
                    value={manualForm.notes}
                    onChange={e => setManualForm(f => ({ ...f, notes: e.target.value }))} />
                </div>
              </div>
              <button className="btn btn-primary" type="submit" disabled={manualSaving}>
                {manualSaving ? <><span className="spinner" /> Saving…</> : '💾 Save Measurement'}
              </button>
            </form>
          </>
        )
      )}

    </div>
  );
}
