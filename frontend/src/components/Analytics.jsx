import React, { useState, useEffect, useCallback } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, ResponsiveContainer, Legend,
} from 'recharts';
import api from '../services/api';
import ErrorBoundary from './ErrorBoundary';

const PIE_COLORS = ['#48bb78', '#fc8181', '#f6ad55'];

export default function Analytics() {
  const [summary, setSummary] = useState(null);
  const [inactive, setInactive] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [summaryRes, inactiveRes] = await Promise.all([
        api.get('/analytics/summary'),
        api.get('/patients/inactive'),
      ]);
      setSummary(summaryRes.data);
      setInactive(inactiveRes.data);
    } catch {
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="flex-center" style={{ height: 300 }}><span className="spinner" /></div>;

  const s = summary || {};
  const overdue = inactive.length;
  const healthy = Math.max(0, (s.active_patients || 0) - overdue);

  const statusData = [
    { name: 'Active & on track', value: healthy },
    { name: 'Overdue (3+ wks)', value: overdue },
    { name: 'Inactive / Archived', value: (s.total_patients || 0) - (s.active_patients || 0) },
  ];

  const lossData = s.top_losers || [];
  const avgLoss = s.average_weight_loss_kg;

  return (
    <ErrorBoundary>
      <div className="kpi-grid" style={{ marginBottom: 24 }}>
        <div className="kpi-card">
          <div className="kpi-icon">👥</div>
          <div className="kpi-label">Total Patients</div>
          <div className="kpi-value">{s.total_patients ?? '—'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">✅</div>
          <div className="kpi-label">Active Patients</div>
          <div className="kpi-value" style={{ color: 'var(--green)' }}>{s.active_patients ?? '—'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">📲</div>
          <div className="kpi-label">Bale Connected</div>
          <div className="kpi-value" style={{ color: 'var(--blue)' }}>{s.patients_with_bale ?? '—'}</div>
          <div className="kpi-sub">{s.active_patients ? Math.round((s.patients_with_bale || 0) / s.active_patients * 100) : 0}% of active</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-icon">⚖️</div>
          <div className="kpi-label">Avg. Weight Loss</div>
          <div className="kpi-value" style={{ color: 'var(--green)' }}>{avgLoss ?? '—'}</div>
          <div className="kpi-sub">kg per patient</div>
        </div>
      </div>

      <div className="grid-2" style={{ gap: 20, marginBottom: 20 }}>
        <div className="card">
          <div className="card-title">Patient Status Distribution</div>
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={statusData}
                  cx="50%"
                  cy="50%"
                  innerRadius={55}
                  outerRadius={90}
                  paddingAngle={3}
                  dataKey="value"
                  label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  labelLine={false}
                >
                  {statusData.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <div className="card-title">Top Weight Loss by Patient</div>
          {lossData.length === 0 ? (
            <div className="empty-state" style={{ padding: '20px 0' }}>
              <p>No multi-visit patient data yet.</p>
            </div>
          ) : (
            <div style={{ height: 240 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={lossData} margin={{ top: 0, right: 10, left: -15, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--gray-200)" />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} unit=" kg" />
                  <Tooltip formatter={(v) => [`${v} kg`, 'Weight Loss']} />
                  <Bar dataKey="loss" fill="var(--green)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="card-title">⚠ Patients Requiring Attention</div>
        {inactive.length === 0 ? (
          <div className="empty-state" style={{ padding: '20px 0' }}>
            <div style={{ fontSize: 28 }}>🎉</div>
            <p>All patients are on track! No overdue visits.</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Age</th>
                  <th>Last Visit</th>
                  <th>Days Inactive</th>
                  <th>Bale Status</th>
                </tr>
              </thead>
              <tbody>
                {inactive.map(p => (
                  <tr key={p.id}>
                    <td><strong>{p.name}</strong></td>
                    <td>{p.age}</td>
                    <td>{p.last_visit ? new Date(p.last_visit).toLocaleDateString() : 'Never'}</td>
                    <td>
                      <span className={`badge ${p.days_inactive > 42 ? 'badge-red' : 'badge-orange'}`}>
                        {p.days_inactive ?? 'N/A'} days
                      </span>
                    </td>
                    <td>
                      {p.bale_chat_id
                        ? <span className="badge badge-green">Linked</span>
                        : <span className="badge badge-red">No Bale</span>
                      }
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </ErrorBoundary>
  );
}
