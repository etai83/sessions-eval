'use client';

import React, { useState } from 'react';
import { AnalyticsHeader } from '@/components/AnalyticsHeader';
import { SessionsTable } from '@/components/SessionsTable';
import { SyncButton } from '@/components/SyncButton';
import { Layers } from 'lucide-react';

export default function HomePage() {
  const [refreshKey, setRefreshKey] = useState(0);

  const handleSyncComplete = () => {
    setRefreshKey(prev => prev + 1);
  };

  return (
    <main className="min-h-screen bg-slate-100 text-slate-900 pb-12">
      {/* Navbar Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-sky-600 text-white rounded-lg">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-slate-900 leading-none">Antigravity Sessions Review</h1>
              <p className="text-xs text-slate-500 mt-1">Analytics Dashboard & Log Inspector</p>
            </div>
          </div>

          {/* Sync Button */}
          <SyncButton onSyncComplete={handleSyncComplete} />
        </div>
      </header>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        <AnalyticsHeader refreshKey={refreshKey} />
        <SessionsTable refreshKey={refreshKey} />
      </div>
    </main>
  );
}
