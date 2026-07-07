import React, { useState, useEffect } from 'react';
import api from '../services/api';

const ITEM_STYLE = (active) => ({
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  cursor: 'pointer',
  padding: '10px 16px',
  background: active ? '#ebf8ff' : '#fff',
  border: `2px solid ${active ? '#3182ce' : '#e2e8f0'}`,
  borderRadius: 10,
  transition: 'all 0.15s',
  userSelect: 'none',
  fontSize: 14,
  fontWeight: active ? 600 : 400,
  color: active ? '#2b6cb0' : '#4a5568',
});

export default function ReportModal({ patient, measurements, onClose }) {
  const [templates, setTemplates]       = useState([]);
  const [selectedTpl, setSelectedTpl]   = useState(null);
  const [customPrompt, setCustomPrompt] = useState('');
  const [reportKind, setReportKind]     = useState('standard'); // 'standard' | 'forecast'
  const [sendItems, setSendItems]       = useState({
    summary: measurements.length >= 1,
    table:   true,
    chart:   measurements.length >= 2,
    report:  true,
  });
  const [generating, setGenerating] = useState(false);
  const [sending, setSending]       = useState(false);
  const [report, setReport]         = useState(null);
  const [editedText, setEditedText] = useState('');
  const [error, setError]           = useState('');
  const [success, setSuccess]       = useState('');
  const [step, setStep]             = useState('compose');

  useEffect(() => {
    api.get('/messaging/templates').then(r => {
      setTemplates(r.data);
      if (r.data.length > 0) setSelectedTpl(r.data[0]);
    }).catch(() => {});
  }, []);

  const usingCustomPrompt   = customPrompt.trim().length > 0;
  const isFirstVisitPreset  = !usingCustomPrompt && selectedTpl?.id === 'first_visit';
  const effectivePrompt = customPrompt.trim() || selectedTpl?.text || '';
  const canGenerate     = sendItems.summary || sendItems.table || sendItems.chart || sendItems.report;
  const promptNeeded    = reportKind === 'standard' && sendItems.report && !effectivePrompt && !isFirstVisitPreset;

  const selectKind = (kind) => {
    setReportKind(kind);
    if (kind === 'forecast') {
      setSendItems({ summary: false, table: false, chart: true, report: true });
    } else {
      setSendItems({
        summary: measurements.length >= 1,
        table:   true,
        chart:   measurements.length >= 2,
        report:  true,
      });
    }
  };

  const generate = async () => {
    if (promptNeeded) { setError('Please select a template or write a custom prompt.'); return; }
    setError('');
    setGenerating(true);
    try {
      const res = await api.post('/messaging/generate-report', {
        patient_id:      patient.id,
        report_type:     reportKind,
        prompt:          reportKind === 'standard' && sendItems.report ? effectivePrompt : '',
        template_id:     reportKind === 'standard' && sendItems.report && !usingCustomPrompt
                            ? selectedTpl?.id : null,
        include_summary: sendItems.summary,
        include_chart:   sendItems.chart,
        include_table:   sendItems.table,
        include_report:  sendItems.report,
      }, { timeout: 120000 });
      setReport(res.data);
      setEditedText(res.data.report_text || '');
      setStep('preview');
    } catch (e) {
      const err = e.response?.data;
      if (err?.retry) {
        setError('AI service temporarily unavailable. Please retry.');
      } else {
        setError(err?.error || 'Failed to generate report.');
      }
    } finally {
      setGenerating(false);
    }
  };

  const send = async () => {
    setSending(true);
    setError('');
    try {
      const res = await api.post('/messaging/send', {
        patient_id:    patient.id,
        report_type:   reportKind,
        message:       editedText,
        summary_base64: report?.summary_base64 || null,
        chart_base64:  report?.chart_base64  || null,
        table_base64:  report?.table_base64  || null,
        send_summary:  sendItems.summary && !!report?.summary_base64,
        send_report:   sendItems.report  && !!editedText,
        send_chart:    sendItems.chart   && !!report?.chart_base64,
        send_table:    sendItems.table   && !!report?.table_base64,
      });
      const { sent, failed } = res.data;
      const labels = { summary: 'Summary Card', table: 'Table', chart: 'Chart', report: 'Report' };
      const sentStr   = sent.map(s => labels[s]).join(', ');
      const failedStr = failed.length ? ` (failed: ${failed.map(f => labels[f]).join(', ')})` : '';
      setSuccess(`✅ Sent successfully: ${sentStr}${failedStr}`);
      setTimeout(onClose, 2800);
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to send. Check your bot token and patient chat ID.');
    } finally {
      setSending(false);
    }
  };

  const toggle = (key) => setSendItems(s => ({ ...s, [key]: !s[key] }));

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal modal-lg" onClick={e => e.stopPropagation()} style={{ maxWidth: 760 }}>

        {/* Header */}
        <div className="modal-header" style={{
          background: 'linear-gradient(135deg, #1a365d 0%, #2b6cb0 100%)',
          color: '#fff',
          borderRadius: 'var(--radius) var(--radius) 0 0',
        }}>
          <div>
            <h2 style={{ color: '#fff', marginBottom: 2 }}>📊 Report & Send — {patient.name}</h2>
            <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.75)' }}>
              Bale Chat ID: {patient.bale_chat_id || '(not linked)'}
            </div>
          </div>
          <button className="modal-close"
            style={{ color: '#fff', background: 'rgba(255,255,255,0.15)',
              border: 'none', borderRadius: '50%', width: 32, height: 32 }}
            onClick={onClose}>×</button>
        </div>

        <div className="modal-body">
          {error && (
            <div className="alert alert-error" style={{ marginBottom: 16 }}>
              ⚠ {error}
              {error.includes('retry') && (
                <button className="btn btn-sm btn-warning" style={{ marginLeft: 10 }}
                  onClick={generate}>🔄 Retry</button>
              )}
            </div>
          )}
          {success && <div className="alert alert-success" style={{ marginBottom: 16 }}>{success}</div>}

          {step === 'compose' ? (
            <>
              {/* Report kind tabs */}
              <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
                <label style={ITEM_STYLE(reportKind === 'standard')} onClick={() => selectKind('standard')}>
                  <span style={{ fontSize: 18 }}>📈</span>
                  Standard Report
                </label>
                <label style={{
                  ...ITEM_STYLE(reportKind === 'forecast'),
                  opacity: measurements.length < 2 ? 0.5 : 1,
                  cursor: measurements.length < 2 ? 'not-allowed' : 'pointer',
                }} onClick={() => measurements.length >= 2 && selectKind('forecast')}>
                  <span style={{ fontSize: 18 }}>🔮</span>
                  6-Month Forecast
                  {measurements.length < 2 &&
                    <span style={{ color: '#a0aec0', fontSize: 11 }}>(2+ visits needed)</span>}
                </label>
              </div>

              {reportKind === 'forecast' ? (
                <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0',
                  borderRadius: 12, padding: '16px 20px', marginBottom: 20, fontSize: 13,
                  color: '#4a5568', lineHeight: 1.7 }}>
                  <div style={{ fontWeight: 700, marginBottom: 6, color: '#1a202c', fontSize: 14 }}>
                    🔮 6-Month Forecast Plan
                  </div>
                  Generates a chart projecting the next 6 months under three scenarios (optimistic,
                  normal, cautious), computed from this patient's actual measurement trend, plus an
                  AI-written paragraph (Persian) explaining the goal and how to reach it.
                </div>
              ) : (
              <>
              {/* Select what to send */}
              <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0',
                borderRadius: 12, padding: '16px 20px', marginBottom: 20 }}>
                <div style={{ fontWeight: 700, marginBottom: 12, color: '#1a202c', fontSize: 14 }}>
                  Select content to send
                </div>
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                  <label style={{
                    ...ITEM_STYLE(sendItems.summary),
                    opacity: measurements.length < 1 ? 0.5 : 1,
                  }}>
                    <input type="checkbox" checked={sendItems.summary}
                      onChange={() => measurements.length >= 1 && toggle('summary')}
                      style={{ display: 'none' }} disabled={measurements.length < 1} />
                    <span style={{ fontSize: 18 }}>📊</span>
                    Metric Summary Card
                    <span style={{ fontSize: 11, color: '#718096' }}>(Persian image)</span>
                  </label>
                  <label style={ITEM_STYLE(sendItems.table)}>
                    <input type="checkbox" checked={sendItems.table}
                      onChange={() => toggle('table')} style={{ display: 'none' }} />
                    <span style={{ fontSize: 18 }}>📋</span>
                    Measurement Table
                    <span style={{ fontSize: 11, color: '#718096' }}>(Persian image)</span>
                  </label>
                  <label style={{
                    ...ITEM_STYLE(sendItems.chart),
                    opacity: measurements.length < 2 ? 0.5 : 1,
                  }}>
                    <input type="checkbox" checked={sendItems.chart}
                      onChange={() => measurements.length >= 2 && toggle('chart')}
                      style={{ display: 'none' }} disabled={measurements.length < 2} />
                    <span style={{ fontSize: 18 }}>📈</span>
                    Progress Chart
                    {measurements.length < 2
                      ? <span style={{ color: '#a0aec0', fontSize: 11 }}>(2+ visits needed)</span>
                      : <span style={{ fontSize: 11, color: '#718096' }}>(Persian image)</span>}
                  </label>
                  <label style={ITEM_STYLE(sendItems.report)}>
                    <input type="checkbox" checked={sendItems.report}
                      onChange={() => toggle('report')} style={{ display: 'none' }} />
                    <span style={{ fontSize: 18 }}>🤖</span>
                    AI Report
                    <span style={{ fontSize: 11, color: '#718096' }}>(Persian text)</span>
                  </label>
                </div>
              </div>

              {/* Prompt section */}
              {sendItems.report && (
                <>
                  <div className="form-group">
                    <label className="form-label">Report Template</label>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                      {templates.filter(t => t.id !== 'forecast_plan').map(t => (
                        <button key={t.id}
                          className={`btn btn-sm ${selectedTpl?.id === t.id && !customPrompt ? 'btn-primary' : 'btn-ghost'}`}
                          onClick={() => { setSelectedTpl(t); setCustomPrompt(''); }}>
                          {t.label}
                        </button>
                      ))}
                    </div>
                    {selectedTpl && !customPrompt && (
                      <div style={{ fontSize: 12, color: '#4a5568', background: '#f7fafc',
                        padding: '10px 14px', borderRadius: 8,
                        borderLeft: '3px solid #3182ce', lineHeight: 1.6 }}>
                        {selectedTpl.description}
                      </div>
                    )}
                  </div>

                  <div className="form-group">
                    <label className="form-label">
                      Custom Prompt <span className="text-muted">(optional — overrides template above)</span>
                    </label>
                    <textarea className="form-textarea" rows={3}
                      placeholder="Write your custom instructions here, or leave blank to use the selected template…"
                      value={customPrompt}
                      onChange={e => setCustomPrompt(e.target.value)} />
                  </div>
                </>
              )}
              </>
              )}
            </>
          ) : (
            /* Preview step */
            <>
              {report?.summary_base64 && sendItems.summary && (
                <div style={{ marginBottom: 24 }}>
                  <div style={{ fontWeight: 700, color: '#2d3748', marginBottom: 8,
                    fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                    📊 Metric Summary Card <span style={{ fontWeight: 400, fontSize: 12, color: '#718096' }}>(sent in Persian)</span>
                  </div>
                  <img src={`data:image/png;base64,${report.summary_base64}`}
                    alt="Metric summary card"
                    style={{ maxWidth: '100%', borderRadius: 10,
                      border: '1px solid #e2e8f0',
                      boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }} />
                </div>
              )}

              {report?.table_base64 && sendItems.table && (
                <div style={{ marginBottom: 24 }}>
                  <div style={{ fontWeight: 700, color: '#2d3748', marginBottom: 8,
                    fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                    📋 Measurement Table <span style={{ fontWeight: 400, fontSize: 12, color: '#718096' }}>(sent in Persian)</span>
                  </div>
                  <img src={`data:image/png;base64,${report.table_base64}`}
                    alt="Measurement table"
                    style={{ maxWidth: '100%', borderRadius: 10,
                      border: '1px solid #e2e8f0',
                      boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }} />
                </div>
              )}

              {report?.chart_base64 && sendItems.chart && (
                <div style={{ marginBottom: 24 }}>
                  <div style={{ fontWeight: 700, color: '#2d3748', marginBottom: 8,
                    fontSize: 14, display: 'flex', alignItems: 'center', gap: 6 }}>
                    {reportKind === 'forecast'
                      ? <>🔮 6-Month Weight Forecast <span style={{ fontWeight: 400, fontSize: 12, color: '#718096' }}>(sent in Persian)</span></>
                      : <>📈 Progress Chart <span style={{ fontWeight: 400, fontSize: 12, color: '#718096' }}>(sent in Persian)</span></>}
                  </div>
                  <img src={`data:image/png;base64,${report.chart_base64}`}
                    alt={reportKind === 'forecast' ? '6-month weight forecast chart' : 'Progress chart'}
                    style={{ maxWidth: '100%', borderRadius: 10,
                      border: '1px solid #e2e8f0',
                      boxShadow: '0 4px 16px rgba(0,0,0,0.08)' }} />
                </div>
              )}

              {sendItems.report && (
                <div className="form-group">
                  <label className="form-label">
                    {reportKind === 'forecast' ? 'Goal & Forecast Explanation' : 'AI Report Text'}{' '}
                    <span className="text-muted" style={{ fontWeight: 400 }}>
                      (editable before sending — sent in Persian)
                    </span>
                  </label>
                  <textarea className="form-textarea" rows={12}
                    value={editedText}
                    onChange={e => setEditedText(e.target.value)}
                    style={{
                      fontFamily: 'Tahoma, Vazir, sans-serif',
                      direction: 'rtl',
                      lineHeight: 1.9,
                      fontSize: 14,
                      background: '#fafbfc',
                    }} />
                </div>
              )}

              <div style={{ background: '#ebf8ff', border: '1px solid #90cdf4',
                borderRadius: 10, padding: '12px 16px', fontSize: 13, color: '#2b6cb0' }}>
                📲 Will be sent to <strong>{patient.name}</strong> via Bale (Chat ID: {patient.bale_chat_id})
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="modal-footer">
          <button className="btn btn-ghost"
            onClick={step === 'compose' ? onClose : () => setStep('compose')}>
            {step === 'compose' ? 'Cancel' : '← Back'}
          </button>

          {step === 'compose' ? (
            <button className="btn btn-primary" style={{ minWidth: 160 }}
              onClick={generate}
              disabled={generating || !canGenerate || promptNeeded}>
              {generating
                ? <><span className="spinner" /> Generating…</>
                : '✨ Generate Preview'}
            </button>
          ) : (
            <button className="btn btn-success" style={{ minWidth: 160 }}
              onClick={send}
              disabled={sending || !!success}>
              {sending
                ? <><span className="spinner" /> Sending…</>
                : '📤 Send via Bale'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
