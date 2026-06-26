import React, { useState, useEffect, useRef } from 'react';
import api from '../services/api';

const STATUS_LABELS = {
  idle:     { label: 'Scale Disconnected', color: 'gray',   icon: '⚡' },
  scanning: { label: 'Scanning…',          color: 'orange', icon: '🔍' },
  connected:{ label: 'Scale Connected',    color: 'green',  icon: '⚖️' },
  finished: { label: 'Measurement Done',   color: 'green',  icon: '✅' },
  error:    { label: 'Bluetooth Error',    color: 'red',    icon: '❌' },
};

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

function BMIBar({ bmi }) {
  if (!bmi) return null;
  const MIN = 15, MAX = 45;
  const pct = Math.min(100, Math.max(0, ((bmi - MIN) / (MAX - MIN)) * 100));
  const cat = bmiCategory(bmi);
  return (
    <div style={{ margin: '8px 0 4px' }}>
      <div style={{ position: 'relative', height: 6, background: '#e2e8f0', borderRadius: 4 }}>
        <div style={{ position: 'absolute', left: `${((18.5-MIN)/(MAX-MIN))*100}%`,
          width: `${((25-18.5)/(MAX-MIN))*100}%`, height: '100%', background: '#c6f6d5', borderRadius: 2 }} />
        <div style={{ position: 'absolute', left: `${((25-MIN)/(MAX-MIN))*100}%`,
          width: `${((30-25)/(MAX-MIN))*100}%`, height: '100%', background: '#fefcbf', borderRadius: 2 }} />
        <div style={{ position: 'absolute', left: `${pct}%`, top: -3, width: 12, height: 12,
          borderRadius: '50%', background: cat?.color || '#a0aec0', border: '2px solid #fff',
          boxShadow: '0 1px 3px rgba(0,0,0,0.3)', transform: 'translateX(-50%)' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9,
        color: '#a0aec0', marginTop: 3 }}>
        <span>15</span><span>18.5</span><span>25</span><span>30</span><span>45</span>
      </div>
    </div>
  );
}

function MetricCard({ label, value, unit, color, badge, extra }) {
  return (
    <div className="measure-card" style={{ '--metric-color': color }}>
      <div className="measure-label">{label}</div>
      <div style={{ marginTop: 8 }}>
        <span className="measure-value" style={{ color }}>{value ?? '—'}</span>
        {unit && <span className="measure-unit" style={{ marginLeft: 3 }}>{unit}</span>}
      </div>
      {badge && <div className="measure-badge" style={{ background: badge.bg, color: badge.color }}>{badge.label}</div>}
      {extra}
    </div>
  );
}

function BmiLegend() {
  return (
    <div className="measure-card" style={{ '--metric-color': '#a0aec0',
      display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 5, padding: '12px 14px' }}>
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
}

// ── Shared result grid for Bluetooth & OCR confirmed data ────────────────────
function ResultGrid({ data, heightCm }) {
  const bmi = data.weight && heightCm
    ? parseFloat((data.weight / Math.pow(heightCm / 100, 2)).toFixed(1))
    : null;
  return (
    <div className="measure-grid">
      <MetricCard label="Weight"               value={data.weight}               unit="kg"   color="#2b6cb0" />
      <MetricCard label="BMI"                  value={bmi}                       unit=""     color={bmiColor(bmi)} badge={bmiCategory(bmi)} extra={<BMIBar bmi={bmi} />} />
      <MetricCard label="Body Fat"             value={data.body_fat_pct}         unit="%"    color="#e53e3e" />
      <MetricCard label="Muscle Mass"          value={data.muscle_mass}          unit="kg"   color="#38a169" />
      {data.water_pct  && <MetricCard label="Body Water"  value={data.water_pct}  unit="%"   color="#3182ce" />}
      {data.water_kg   && <MetricCard label="Body Water"  value={data.water_kg}   unit="kg"  color="#3182ce" />}
      {data.bmr        && <MetricCard label="BMR"          value={data.bmr}        unit="kcal" color="#d69e2e" />}
      {data.bone_mass  && <MetricCard label="Bone Mass"    value={data.bone_mass}  unit="kg"  color="#805ad5" />}
      {data.visceral_fat && <MetricCard label="Visceral Fat" value={data.visceral_fat} unit="" color="#e53e3e" />}
      {data.lean_body_mass && <MetricCard label="Lean Body Mass" value={data.lean_body_mass} unit="kg" color="#38a169" />}
      {data.fat_mass   && <MetricCard label="Fat Mass"     value={data.fat_mass}   unit="kg"  color="#e53e3e" />}
      {data.protein    && <MetricCard label="Protein"      value={data.protein}    unit="%"   color="#d69e2e" />}
      {data.skeletal_muscle_mass && <MetricCard label="Skeletal Muscle" value={data.skeletal_muscle_mass} unit="kg" color="#38a169" />}
      {data.subcutaneous_fat && <MetricCard label="Subcut. Fat" value={data.subcutaneous_fat} unit="%" color="#fc8181" />}
      {data.body_age   && <MetricCard label="Body Age"     value={data.body_age}   unit="yrs" color="#4a5568" />}
      {data.body_type  && <MetricCard label="Body Type"    value={data.body_type}  unit=""    color="#4a5568" />}
      <BmiLegend />
    </div>
  );
}

// ── OCR mode: only these fields are shown / saved ────────────────────────────
const OCR_FIELDS = [
  { key: 'body_fat_pct', label: 'Body Fat (%)',     step: '0.1', min: '2',  max: '70'  },
  { key: 'fat_mass',     label: 'Fat Mass (kg)',    step: '0.1', min: '0',  max: '150' },
  { key: 'muscle_mass',  label: 'Muscle Mass (kg)', step: '0.1', min: '1',  max: '150' },
  { key: 'water_pct',    label: 'Body Water (%)',   step: '0.1', min: '1',  max: '100' },
];

// ── Extended field form rows (shared by Manual entry) ────────────────────────
const EXTENDED_FIELDS = [
  { key: 'body_fat_pct', label: 'Body Fat (%)',      step: '0.1', min: '2', max: '70',  unit: '%'  },
  { key: 'muscle_mass',  label: 'Muscle Mass (kg)',  step: '0.1', min: '1', max: '150', unit: 'kg' },
  { key: 'water_pct',    label: 'Body Water (%)',    step: '0.1', min: '1', max: '100', unit: '%'  },
  { key: 'fat_mass',     label: 'Body Fat Mass (kg)',step: '0.1', min: '0', max: '150', unit: 'kg' },
];

function ExtendedFields({ form, onChange, cols = 2 }) {
  const rows = [];
  for (let i = 0; i < EXTENDED_FIELDS.length; i += cols) {
    rows.push(EXTENDED_FIELDS.slice(i, i + cols));
  }
  return (
    <>
      {rows.map((row, ri) => (
        <div className="form-row" key={ri}>
          {row.map(f => (
            <div className="form-group" key={f.key}>
              <label className="form-label">{f.label}</label>
              <input
                className="form-input"
                type="number"
                step={f.step}
                min={f.min}
                max={f.max}
                placeholder={`e.g. ${f.min}`}
                value={form[f.key] ?? ''}
                onChange={e => onChange(f.key, e.target.value)}
              />
            </div>
          ))}
        </div>
      ))}
    </>
  );
}

// ── Drag-and-drop / click upload area ────────────────────────────────────────
function ImageDropZone({ onFile, preview }) {
  const inputRef = useRef();
  const [dragging, setDragging] = useState(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith('image/')) onFile(file);
  };

  return (
    <div
      onClick={() => inputRef.current.click()}
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      style={{
        border: `2px dashed ${dragging ? '#3182ce' : '#cbd5e0'}`,
        borderRadius: 10,
        padding: 24,
        textAlign: 'center',
        cursor: 'pointer',
        background: dragging ? '#ebf8ff' : '#f7fafc',
        transition: 'all 0.2s',
        marginBottom: 16,
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={e => { if (e.target.files[0]) onFile(e.target.files[0]); }}
      />
      {preview ? (
        <img src={preview} alt="Scale screenshot" style={{ maxWidth: '100%', maxHeight: 320, borderRadius: 8 }} />
      ) : (
        <>
          <div style={{ fontSize: 40, marginBottom: 8 }}>📷</div>
          <div style={{ color: '#4a5568', fontWeight: 600 }}>Drop screenshot here or click to upload</div>
          <div style={{ color: '#a0aec0', fontSize: 12, marginTop: 4 }}>Supports PNG, JPG, WEBP</div>
        </>
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function MeasurementPanel({ patient, socket, onMeasurementReady }) {
  // ── Bluetooth state ──
  const [bleStatus, setBleStatus] = useState('idle');
  const [liveData, setLiveData]   = useState(null);
  const [bleSaving, setBleSaving] = useState(false);
  const [bleSaved, setBleSaved]   = useState(false);
  const [bleNotes, setBleNotes]   = useState('');
  const [bleError, setBleError]   = useState('');

  // ── OCR state ──
  const [ocrFile, setOcrFile]         = useState(null);
  const [ocrPreview, setOcrPreview]   = useState(null);
  const [ocrAnalyzing, setOcrAnalyzing] = useState(false);
  const [ocrFields, setOcrFields]     = useState(null);   // extracted + editable
  const [ocrNotes, setOcrNotes]       = useState('');
  const [ocrRecordedAt, setOcrRecordedAt] = useState(() => {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    return now.toISOString().slice(0, 16);
  });
  const [ocrSaving, setOcrSaving]     = useState(false);
  const [ocrSaved, setOcrSaved]       = useState(false);
  const [ocrSavedData, setOcrSavedData] = useState(null);
  const [ocrError, setOcrError]       = useState('');

  // ── Manual state ──
  const emptyManual = () => {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    return {
      weight: '', body_fat_pct: '', muscle_mass: '', water_pct: '',
      fat_mass: '', lean_body_mass: '', bmr: '', bone_mass: '',
      visceral_fat: '', protein: '', skeletal_muscle_mass: '',
      subcutaneous_fat: '', body_age: '', body_type: '',
      notes: '', recorded_at: now.toISOString().slice(0, 16),
    };
  };
  const [manualForm, setManualForm]   = useState(emptyManual);
  const [manualSaving, setManualSaving] = useState(false);
  const [manualError, setManualError] = useState('');
  const [manualSaved, setManualSaved] = useState(false);
  const [manualResult, setManualResult] = useState(null);

  const [mode, setMode] = useState('bluetooth');

  // ── Bluetooth socket listeners ──
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

  // ── Bluetooth actions ──
  const startScan = async () => {
    setBleError(''); setBleSaved(false); setLiveData(null);
    try {
      await api.post('/bluetooth/start', {
        patient_id: patient.id, height_cm: patient.height_cm,
        age: patient.age, is_male: patient.is_male,
      });
      setBleStatus('scanning');
    } catch {
      setBleError('Failed to start Bluetooth scan. Is the backend running?');
    }
  };

  const stopScan = async () => {
    try { await api.post('/bluetooth/stop'); setBleStatus('idle'); } catch {}
  };

  const saveBle = async () => {
    if (!liveData) return;
    setBleSaving(true); setBleError('');
    try {
      const res = await api.post(`/patients/${patient.id}/measurements`, {
        weight: liveData.weight, impedance: liveData.impedance,
        notes: bleNotes, input_method: 'bluetooth',
      });
      setBleSaved(true);
      if (onMeasurementReady) onMeasurementReady(res.data);
    } catch (e) {
      setBleError(e.response?.data?.error || 'Failed to save measurement.');
    } finally {
      setBleSaving(false);
    }
  };

  // ── OCR actions ──
  const handleOcrFile = (file) => {
    setOcrFile(file);
    setOcrFields(null);
    setOcrSaved(false);
    setOcrError('');
    const reader = new FileReader();
    reader.onload = (e) => setOcrPreview(e.target.result);
    reader.readAsDataURL(file);
  };

  const analyzeImage = async () => {
    if (!ocrFile) return;
    setOcrAnalyzing(true); setOcrError('');
    try {
      const formData = new FormData();
      formData.append('image', ocrFile);
      const res = await api.post('/ocr/analyze', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const data = res.data;
      // Populate only the OCR fields (BMI is computed server-side)
      const fields = {};
      OCR_FIELDS.forEach(f => {
        fields[f.key] = data[f.key] !== undefined ? String(data[f.key]) : '';
      });
      if (data.weight !== undefined) fields.weight = String(data.weight);
      setOcrFields(fields);
    } catch (e) {
      setOcrError(e.response?.data?.error || 'OCR analysis failed. Check that pytesseract is installed.');
    } finally {
      setOcrAnalyzing(false);
    }
  };

  const saveOcr = async (e) => {
    e.preventDefault();
    if (!ocrFields?.weight) {
      setOcrError('Weight is required.');
      return;
    }
    setOcrSaving(true); setOcrError('');
    try {
      const payload = { input_method: 'ocr', notes: ocrNotes, recorded_at: ocrRecordedAt };
      OCR_FIELDS.forEach(f => {
        const v = ocrFields[f.key];
        if (v !== '' && v !== null && v !== undefined) {
          payload[f.key] = parseFloat(v);
        }
      });
      if (ocrFields.weight) payload.weight = parseFloat(ocrFields.weight);
      const res = await api.post(`/patients/${patient.id}/measurements`, payload);
      setOcrSaved(true);
      setOcrSavedData({ ...payload });
      if (onMeasurementReady) onMeasurementReady(res.data);
    } catch (err) {
      setOcrError(err.response?.data?.error || 'Failed to save measurement.');
    } finally {
      setOcrSaving(false);
    }
  };

  const resetOcr = () => {
    setOcrFile(null); setOcrPreview(null); setOcrFields(null);
    setOcrSaved(false); setOcrSavedData(null); setOcrError('');
    setOcrNotes('');
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    setOcrRecordedAt(now.toISOString().slice(0, 16));
  };

  // ── Manual actions ──
  const saveManual = async (e) => {
    e.preventDefault();
    setManualSaving(true); setManualError('');
    try {
      const payload = { input_method: 'manual' };
      if (manualForm.weight)      payload.weight       = parseFloat(manualForm.weight);
      if (manualForm.recorded_at) payload.recorded_at  = manualForm.recorded_at;
      if (manualForm.notes)       payload.notes        = manualForm.notes;
      if (manualForm.body_type)   payload.body_type    = manualForm.body_type;
      EXTENDED_FIELDS.forEach(f => {
        const v = manualForm[f.key];
        if (v !== '' && v !== null && v !== undefined) {
          payload[f.key] = f.isInt ? parseInt(v) : parseFloat(v);
        }
      });
      const res = await api.post(`/patients/${patient.id}/measurements`, payload);
      setManualResult({ ...payload });
      setManualSaved(true);
      if (onMeasurementReady) onMeasurementReady(res.data);
    } catch (err) {
      setManualError(err.response?.data?.error || 'Failed to save measurement.');
    } finally {
      setManualSaving(false);
    }
  };

  const st = STATUS_LABELS[bleStatus] || STATUS_LABELS.idle;
  const bleBmi = liveData?.weight && patient.height_cm
    ? parseFloat((liveData.weight / Math.pow(patient.height_cm / 100, 2)).toFixed(1))
    : null;

  return (
    <div className="card" style={{ marginBottom: 20 }}>

      {/* ── Mode toggle ── */}
      <div className="flex-between mb-16">
        <span className="card-title" style={{ marginBottom: 0 }}>⚖️ Measurement</span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            className={`btn btn-sm ${mode === 'bluetooth' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setMode('bluetooth')}
          >📡 Bluetooth Scale</button>
          <button
            className={`btn btn-sm ${mode === 'ocr' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setMode('ocr')}
          >📷 OCR / Photo</button>
          <button
            className={`btn btn-sm ${mode === 'manual' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => setMode('manual')}
          >✏️ Manual Entry</button>
          {mode === 'bluetooth' && (
            <div className="ble-status" style={{ marginLeft: 8 }}>
              <span className={`status-dot ${st.color}`} />
              {st.icon} {st.label}
            </div>
          )}
        </div>
      </div>

      {/* ══════════════════ BLUETOOTH MODE ══════════════════ */}
      {mode === 'bluetooth' && (
        <>
          {bleError && <div className="alert alert-error">{bleError}</div>}
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
                <MetricCard label="BMI"         value={bleBmi}                unit=""   color={bmiColor(bleBmi)} badge={bmiCategory(bleBmi)} extra={<BMIBar bmi={bleBmi} />} />
                <MetricCard label="Body Fat"    value={liveData.body_fat_pct} unit="%"  color="#e53e3e" />
                <MetricCard label="Muscle Mass" value={liveData.muscle_mass}  unit="kg" color="#38a169" />
                <MetricCard label="Body Water"  value={liveData.water_kg}     unit="kg" color="#3182ce" />
                <BmiLegend />
              </div>

              {bleStatus === 'finished' && !bleSaved && (
                <div style={{ marginTop: 16 }}>
                  <div className="form-group">
                    <label className="form-label">Notes (optional)</label>
                    <textarea className="form-textarea" rows={2}
                      placeholder="Clinical notes for this visit…"
                      value={bleNotes} onChange={e => setBleNotes(e.target.value)} />
                  </div>
                  <button className="btn btn-success" onClick={saveBle} disabled={bleSaving}>
                    {bleSaving ? <><span className="spinner" /> Saving…</> : '💾 Save Measurement'}
                  </button>
                </div>
              )}
              {bleSaved && <div className="alert alert-success mt-12">✅ Measurement saved to patient record.</div>}
            </>
          )}
        </>
      )}

      {/* ══════════════════ OCR MODE ══════════════════ */}
      {mode === 'ocr' && (
        ocrSaved && ocrSavedData ? (
          <>
            <div className="alert alert-success" style={{ marginBottom: 16 }}>✅ Measurement saved from screenshot.</div>
            <ResultGrid data={ocrSavedData} heightCm={patient.height_cm} />
            <button className="btn btn-ghost" style={{ marginTop: 16 }} onClick={resetOcr}>
              📷 Scan Another Screenshot
            </button>
          </>
        ) : (
          <>
            {ocrError && <div className="alert alert-error" style={{ marginBottom: 12 }}>{ocrError}</div>}

            <div style={{ marginBottom: 8, color: '#4a5568', fontSize: 13 }}>
              Upload a screenshot from your smart scale app (Eufy, Renpho, etc.).
              The OCR engine will extract all measurement values automatically.
            </div>

            <ImageDropZone onFile={handleOcrFile} preview={ocrPreview} />

            {ocrFile && !ocrFields && (
              <button
                className="btn btn-primary"
                onClick={analyzeImage}
                disabled={ocrAnalyzing}
                style={{ marginBottom: 16 }}
              >
                {ocrAnalyzing
                  ? <><span className="spinner" /> Analyzing…</>
                  : '🔍 Extract Measurements'}
              </button>
            )}

            {ocrFile && ocrPreview && ocrFields && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={analyzeImage}
                disabled={ocrAnalyzing}
                style={{ marginBottom: 12, marginLeft: 8 }}
              >
                🔄 Re-analyze
              </button>
            )}

            {ocrFields && (
              <form onSubmit={saveOcr}>
                <div style={{ background: '#fffbeb', border: '1px solid #f6e05e',
                  borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 13 }}>
                  ✏️ Review the extracted values below and correct any errors before saving.
                </div>

                {/* Weight (required) */}
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Weight (kg) *</label>
                    <input className="form-input" type="number" step="0.1" min="20" max="300" required
                      value={ocrFields.weight ?? ''}
                      onChange={e => setOcrFields(f => ({ ...f, weight: e.target.value }))} />
                  </div>
                </div>

                {/* OCR fields: Body Fat, Fat Mass, Muscle Mass, Body Water */}
                <div className="form-row">
                  {OCR_FIELDS.slice(0, 2).map(f => (
                    <div className="form-group" key={f.key}>
                      <label className="form-label">{f.label}</label>
                      <input className="form-input" type="number" step={f.step} min={f.min} max={f.max}
                        placeholder={`e.g. ${f.min}`}
                        value={ocrFields[f.key] ?? ''}
                        onChange={e => setOcrFields(prev => ({ ...prev, [f.key]: e.target.value }))} />
                    </div>
                  ))}
                </div>
                <div className="form-row">
                  {OCR_FIELDS.slice(2, 4).map(f => (
                    <div className="form-group" key={f.key}>
                      <label className="form-label">{f.label}</label>
                      <input className="form-input" type="number" step={f.step} min={f.min} max={f.max}
                        placeholder={`e.g. ${f.min}`}
                        value={ocrFields[f.key] ?? ''}
                        onChange={e => setOcrFields(prev => ({ ...prev, [f.key]: e.target.value }))} />
                    </div>
                  ))}
                </div>

                {/* Date & Time */}
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Date & Time</label>
                    <input className="form-input" type="datetime-local"
                      value={ocrRecordedAt}
                      onChange={e => setOcrRecordedAt(e.target.value)} />
                  </div>
                </div>

                <div className="form-group">
                  <label className="form-label">Notes</label>
                  <textarea className="form-textarea" rows={2}
                    placeholder="Clinical notes…"
                    value={ocrNotes}
                    onChange={e => setOcrNotes(e.target.value)} />
                </div>

                <button className="btn btn-success" type="submit" disabled={ocrSaving}>
                  {ocrSaving ? <><span className="spinner" /> Saving…</> : '💾 Save Measurement'}
                </button>
              </form>
            )}
          </>
        )
      )}

      {/* ══════════════════ MANUAL MODE ══════════════════ */}
      {mode === 'manual' && (
        manualSaved && manualResult ? (
          <>
            <div className="alert alert-success" style={{ marginBottom: 16 }}>✅ Measurement saved manually.</div>
            <ResultGrid data={manualResult} heightCm={patient.height_cm} />
            <button className="btn btn-ghost" style={{ marginTop: 16 }} onClick={() => {
              setManualSaved(false); setManualResult(null); setManualForm(emptyManual());
            }}>
              + New Entry
            </button>
          </>
        ) : (
          <>
            {manualError && <div className="alert alert-error" style={{ marginBottom: 12 }}>{manualError}</div>}
            <form id="manual-measure-form" onSubmit={saveManual}>

              {/* Weight (required) */}
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Weight (kg) *</label>
                  <input className="form-input" type="number" step="0.1" min="20" max="300" required
                    placeholder="e.g. 85.5"
                    value={manualForm.weight}
                    onChange={e => setManualForm(f => ({ ...f, weight: e.target.value }))} />
                </div>
              </div>

              {/* All extended fields */}
              <ExtendedFields
                form={manualForm}
                onChange={(key, val) => setManualForm(f => ({ ...f, [key]: val }))}
              />

              {/* Date & Time */}
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">Date & Time</label>
                  <input className="form-input" type="datetime-local"
                    value={manualForm.recorded_at}
                    onChange={e => setManualForm(f => ({ ...f, recorded_at: e.target.value }))} />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">Notes</label>
                <input className="form-input" placeholder="Clinical notes…"
                  value={manualForm.notes}
                  onChange={e => setManualForm(f => ({ ...f, notes: e.target.value }))} />
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
