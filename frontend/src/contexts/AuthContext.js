import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('jwt_token'));
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchUser = useCallback(async (tok) => {
    if (!tok) { setLoading(false); return; }
    try {
      const res = await api.get('/auth/me', {
        headers: { Authorization: `Bearer ${tok}` },
      });
      setUser(res.data);
    } catch {
      setToken(null);
      setUser(null);
      localStorage.removeItem('jwt_token');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchUser(token); }, [token, fetchUser]);

  const login = async (username, password) => {
    const res = await api.post('/auth/login', { username, password });
    const { access_token } = res.data;
    localStorage.setItem('jwt_token', access_token);
    setToken(access_token);
    setUser({ username: res.data.username });
    return res.data;
  };

  const logout = () => {
    localStorage.removeItem('jwt_token');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ token, user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
