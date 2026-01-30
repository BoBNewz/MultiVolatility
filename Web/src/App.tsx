import { useState, useEffect, useRef } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { DashboardLayout } from './layouts/DashboardLayout';
import { Dashboard } from './pages/Dashboard';
import { NewScan } from './pages/NewScan';
import { Results } from './pages/Results';
import { Cases } from './pages/Cases';
import { Evidences } from './pages/Evidences';
import { Login } from './pages/Login';
import { Symbols } from './pages/Symbols';
import { api } from './services/api';
import type { Scan } from './types';
import { Toaster, toast } from 'react-hot-toast';

function App() {
  const navigate = useNavigate();
  const location = useLocation();

  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(() => localStorage.getItem('selectedCaseId'));

  useEffect(() => {
    if (selectedCaseId) {
      localStorage.setItem('selectedCaseId', selectedCaseId);
    } else {
      localStorage.removeItem('selectedCaseId');
    }
  }, [selectedCaseId]);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [cases, setCases] = useState<Scan[]>([]);
  const [healthStatus, setHealthStatus] = useState(false);
  const seenModulesRef = useRef<Record<string, Set<string>>>({});

  // ...

  useEffect(() => {
    const auth = localStorage.getItem('isLoggedIn');
    if (auth === 'true') {
      setIsLoggedIn(true);
    }
  }, []);

  // Real Data Polling
  useEffect(() => {
    if (!isLoggedIn) return;

    const fetchStatus = async () => {
      const isHealthy = await api.checkHealth();
      setHealthStatus(isHealthy);

      if (isHealthy) {
        const data = await api.getScans();
        setCases(data);

        // Check for new modules in running scans
        const runningScans = data.filter(c => c.status === 'running');
        for (const scan of runningScans) {
          try {
            const currentModules = await api.getScanModules(scan.id);

            // Initialize if first time seeing this scan in this session
            if (!seenModulesRef.current[scan.id]) {
              seenModulesRef.current[scan.id] = new Set(currentModules);
              continue;
            }

            const seenSet = seenModulesRef.current[scan.id];
            const newModules = currentModules.filter(m => !seenSet.has(m));

            newModules.forEach(m => {
              toast.success(`Module ${m} ready for case ${scan.name}`, {
                duration: 5000,
                position: 'bottom-right',
                style: {
                  background: '#1e1e2d',
                  color: '#fff',
                  border: '1px solid rgba(16, 185, 129, 0.2)'
                },
                icon: '✅'
              });
              seenSet.add(m);
            });
          } catch (e) {
            console.error("Failed to check modules for scan", scan.id, e);
          }
        }
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 10000); // Poll every 5s
    return () => clearInterval(interval);
  }, [isLoggedIn]);

  const handleLogin = (password: string) => {
    const envPassword = import.meta.env.VITE_APP_PASSWORD;
    if (password === envPassword) {
      setIsLoggedIn(true);
      localStorage.setItem('isLoggedIn', 'true');
      navigate('/dashboard');
      return true;
    }
    return false;
  };

  const handleCaseClick = (caseId: string) => {
    setSelectedCaseId(caseId);
    navigate(`/results/${caseId}`);
  };

  const handleAddCase = (newCase: Scan) => {
    setCases([newCase, ...cases]);
    navigate('/cases');
  };

  const handleRenameCase = (id: string, newName: string) => {
    setCases(cases.map(c => c.id === id ? { ...c, name: newName } : c));
  };

  const handleDeleteCase = (id: string) => {
    setCases(cases.filter(c => c.id !== id));
  };

  const handleDeleteMultipleCases = (ids: string[]) => {
    setCases(cases.filter(c => !ids.includes(c.id)));
  };

  const handleLogout = () => {
    setIsLoggedIn(false);
    localStorage.removeItem('isLoggedIn');
    navigate('/login');
  };

  // Determine active tab from location
  const getActiveTab = () => {
    const path = location.pathname;
    if (path.startsWith('/dashboard')) return 'dashboard';
    if (path.startsWith('/cases')) return 'cases';
    if (path.startsWith('/evidences')) return 'evidences';
    if (path.startsWith('/symbols')) return 'symbols';
    if (path.startsWith('/scan/new')) return 'new scan';
    if (path.startsWith('/results')) return 'results';
    return 'dashboard';
  };

  const handleTabChange = (tab: string) => {
    switch (tab) {
      case 'dashboard': navigate('/dashboard'); break;
      case 'cases': navigate('/cases'); break;
      case 'evidences': navigate('/evidences'); break;
      case 'symbols': navigate('/symbols'); break;
      case 'new scan': navigate('/scan/new'); break;
      default: navigate('/dashboard');
    }
  };

  return (
    <>
      <Toaster position="bottom-right" toastOptions={{
        style: {
          background: '#1e1e2d',
          color: '#fff',
          border: '1px solid rgba(255,255,255,0.1)'
        }
      }} />

      <Routes>
        <Route path="/login" element={
          isLoggedIn ? <Navigate to="/dashboard" replace /> : <Login onLogin={handleLogin} />
        } />

        {/* Protected Routes */}
        <Route path="/" element={
          isLoggedIn ? <Navigate to="/dashboard" replace /> : <Navigate to="/login" replace />
        } />

        <Route path="/*" element={
          !isLoggedIn ? <Navigate to="/login" replace /> : (
            <DashboardLayout
              activeTab={getActiveTab()}
              onTabChange={handleTabChange}
              onLogout={handleLogout}
              apiStatus={healthStatus}
            >
              <Routes>
                <Route path="dashboard" element={<Dashboard onCaseClick={handleCaseClick} cases={cases} onNavigate={handleTabChange} />} />
                <Route path="cases" element={
                  <Cases
                    onCaseClick={handleCaseClick}
                    onNewCaseClick={() => navigate('/scan/new')}
                    cases={cases}
                    onRenameCase={handleRenameCase}
                    onDeleteCase={handleDeleteCase}
                    onDeleteMultiple={handleDeleteMultipleCases}
                  />
                } />
                <Route path="evidences" element={<Evidences />} />
                <Route path="symbols" element={<Symbols />} />
                <Route path="scan/new" element={<NewScan onStartScan={handleAddCase} />} />
                <Route path="results/:caseId" element={<Results onBack={() => navigate('/cases')} />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
              </Routes>
            </DashboardLayout>
          )
        } />
      </Routes>
    </>
  );
}

export default App;
