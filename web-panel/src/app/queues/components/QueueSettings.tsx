'use client';
import { useState, useEffect } from 'react';

export default function QueueSettings() {
  const [queueMode, setQueueMode] = useState<boolean>(true);
  const [loading, setLoading] = useState<boolean>(true);

  // Helper for resilient API calls
  const apiFetch = async (path: string, options?: RequestInit) => {
    const headers: Record<string, string> = {
      'x-panel-key': 'gangas2026',
      ...((options?.headers as Record<string, string>) || {}),
    };
    return fetch(path, { ...options, headers });
  };

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await apiFetch('/api/settings/queue_mode');
        if (res.ok) {
          const data = await res.json();
          setQueueMode(data.queue_mode);
        }
      } catch (e) {
        console.error("Error fetching queue mode:", e);
      }
      setLoading(false);
    };
    fetchSettings();
  }, []);

  const toggleQueueMode = async () => {
    const newValue = !queueMode;
    // Optimistic UI update
    setQueueMode(newValue);
    try {
      const res = await apiFetch('/api/settings/queue_mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newValue })
      });
      if (!res.ok) {
        // Revert on failure
        setQueueMode(!newValue);
      }
    } catch (e) {
      console.error("Error toggling queue mode:", e);
      setQueueMode(!newValue);
    }
  };

  if (loading) return null;

  return (
    <div className="bg-surface-container rounded-xl p-5 mb-6 flex justify-between items-center shadow-sm border border-outline-variant hover:border-primary/30 transition-colors">
      <div>
        <h2 className="text-on-surface font-headline-md text-headline-md flex items-center gap-2">
          <span className={`material-symbols-outlined text-[20px] ${queueMode ? 'text-primary' : 'text-on-surface-variant'}`}>
            power
          </span>
          <span>Modo Cola</span>
        </h2>
        <p className="text-xs font-body-sm text-on-surface-variant mt-1">
          {queueMode 
            ? 'Los nuevos enlaces se encolan para publicar después.'
            : 'Los nuevos enlaces se publican de inmediato.'}
        </p>
      </div>
      <button 
        onClick={toggleQueueMode}
        className={`w-14 h-8 flex items-center rounded-full p-1 transition-colors duration-300 ${queueMode ? 'bg-primary-container' : 'bg-surface-container-highest border border-outline-variant'}`}
      >
        <div 
          className={`w-6 h-6 rounded-full shadow-md transform transition-transform duration-300 ${
            queueMode ? 'translate-x-6 bg-on-primary-container' : 'translate-x-0 bg-on-surface-variant'
          }`}
        ></div>
      </button>
    </div>
  );
}
