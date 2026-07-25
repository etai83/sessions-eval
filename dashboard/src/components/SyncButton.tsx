'use client';

import React, { useState } from 'react';
import { RefreshCw, CheckCircle2 } from 'lucide-react';

interface SyncButtonProps {
  onSyncComplete?: () => void;
}

export function SyncButton({ onSyncComplete }: SyncButtonProps) {
  const [syncing, setSyncing] = useState(false);
  const [syncedMessage, setSyncedMessage] = useState<string | null>(null);

  const handleSync = async () => {
    if (syncing) return;
    setSyncing(true);
    setSyncedMessage(null);
    try {
      const res = await fetch('/api/sync', { method: 'POST' });
      const json = await res.json();
      if (json.success) {
        setSyncedMessage(`Synced! ${json.conversationsIndexed} updated.`);
        if (onSyncComplete) {
          onSyncComplete();
        }
        setTimeout(() => setSyncedMessage(null), 4000);
      }
    } catch {
      // ignore error
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      {syncedMessage && (
        <span className="text-xs text-emerald-600 font-medium flex items-center gap-1 animate-fade-in">
          <CheckCircle2 className="w-3.5 h-3.5" />
          {syncedMessage}
        </span>
      )}
      <button
        onClick={handleSync}
        disabled={syncing}
        className="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold bg-sky-600 hover:bg-sky-700 text-white rounded-lg transition-colors disabled:opacity-50 shadow-xs cursor-pointer"
      >
        <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
        {syncing ? 'Syncing Sessions...' : 'Sync Latest Sessions'}
      </button>
    </div>
  );
}
