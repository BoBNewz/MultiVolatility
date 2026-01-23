import { useState, useEffect } from 'react';
import { DashboardLayout } from './layouts/DashboardLayout';
import { Dashboard } from './pages/Dashboard';
import { NewScan } from './pages/NewScan';
import { Results } from './pages/Results';
import { Cases } from './pages/Cases';
import { Evidences } from './pages/Evidences';
import { Login } from './pages/Login';
import { api } from './services/api';
import type { Scan } from './types';

function App() {
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem('activeTab') || 'dashboard');

  useEffect(() => {
    localStorage.setItem('activeTab', activeTab);
  }, [activeTab]);

  const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [cases, setCases] = useState<Scan[]>([]);
  const [healthStatus, setHealthStatus] = useState(false);

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
      return true;
    }
    return false;
  };

  const handleCaseClick = (caseId: string) => {
    setSelectedCaseId(caseId);
    setActiveTab('results');
  };

  const handleAddCase = (newCase: Scan) => {
    // Optimistic update, but polling will catch up
    setCases([newCase, ...cases]);
    setActiveTab('cases');
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

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <Dashboard onCaseClick={handleCaseClick} cases={cases} />;
      case 'cases':
        return <Cases
          onCaseClick={handleCaseClick}
          onNewCaseClick={() => setActiveTab('new scan')}
          cases={cases}
          onRenameCase={handleRenameCase}
          onDeleteCase={handleDeleteCase}
          onDeleteMultiple={handleDeleteMultipleCases}
        />;
      case 'evidences':
        return <Evidences />;
      case 'new scan':
        return <NewScan onStartScan={handleAddCase} />;
      case 'results':
        return <Results caseId={selectedCaseId} onBack={() => setActiveTab('cases')} />;
      default:
        return <Dashboard cases={cases} />;
    }
  };

  const handleLogout = () => {
    setIsLoggedIn(false);
    localStorage.removeItem('isLoggedIn');
  };

  if (!isLoggedIn) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <DashboardLayout activeTab={activeTab} onTabChange={setActiveTab} onLogout={handleLogout} apiStatus={healthStatus}>
      {renderContent()}
    </DashboardLayout>
  );
}

export default App;
