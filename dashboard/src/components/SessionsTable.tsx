'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { Search, Filter, RefreshCw, FileText, CheckCircle2, ChevronLeft, ChevronRight, Download } from 'lucide-react';

export interface SessionRow {
  id: string;
  source_brain: 'cli' | 'ide';
  first_prompt: string;
  model_initial: string | null;
  model_last: string | null;
  thinking_level: string | null;
  task_type: string;
  task_type_override: string | null;
  total_steps: number;
  user_request_count: number;
  date_start: string | null;
  date_end: string | null;
  linked_log_path: string | null;
  outcome_snippet: string | null;
  tool_count: number;
}

export function SessionsTable({ refreshKey }: { refreshKey?: number }) {
  const [data, setData] = useState<SessionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState('');
  const [model, setModel] = useState('');
  const [thinking, setThinking] = useState('');
  const [taskType, setTaskType] = useState('');
  const [source, setSource] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalRecords, setTotalRecords] = useState(0);

  const [options, setOptions] = useState<{
    models: string[];
    thinkingLevels: string[];
    taskTypes: string[];
    sources: string[];
  }>({ models: [], thinkingLevels: [], taskTypes: [], sources: [] });

  const handleDownloadJSON = () => {
    const jsonString = `data:text/json;charset=utf-8,${encodeURIComponent(JSON.stringify(data, null, 2))}`;
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', jsonString);
    downloadAnchor.setAttribute('download', `sessions_filtered_export.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        q: query,
        model,
        thinking,
        task_type: taskType,
        source,
        page: String(page),
        pageSize: '15',
      });
      const res = await fetch(`/api/sessions?${params.toString()}`);
      const json = await res.json();
      setData(json.sessions || []);
      setTotalPages(json.pagination?.totalPages || 1);
      setTotalRecords(json.pagination?.total || 0);
      if (json.filterOptions) {
        setOptions(json.filterOptions);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, [query, model, thinking, taskType, source, page, refreshKey]);

  const handleOverrideTaskType = async (sessionId: string, newType: string) => {
    try {
      await fetch(`/api/sessions/${sessionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_type_override: newType === 'AUTO' ? null : newType }),
      });
      fetchSessions();
    } catch {
      // ignore
    }
  };

  const getTaskTypeBadgeColor = (type: string) => {
    switch (type) {
      case 'debug': return 'bg-rose-100 text-rose-800 border-rose-200';
      case 'feature': return 'bg-emerald-100 text-emerald-800 border-emerald-200';
      case 'refactor': return 'bg-amber-100 text-amber-800 border-amber-200';
      case 'research': return 'bg-sky-100 text-sky-800 border-sky-200';
      case 'config': return 'bg-purple-100 text-purple-800 border-purple-200';
      default: return 'bg-slate-100 text-slate-800 border-slate-200';
    }
  };

  return (
    <div className="space-y-4">
      {/* Search and Filters Bar */}
      <div className="flex flex-wrap items-center gap-3 p-4 bg-white rounded-xl border border-slate-200 shadow-xs">
        <div className="relative flex-1 min-w-[240px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search prompts or Conversation IDs..."
            value={query}
            onChange={(e) => { setQuery(e.target.value); setPage(1); }}
            className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-sky-500 focus:bg-white"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Model Filter */}
          <select
            value={model}
            onChange={(e) => { setModel(e.target.value); setPage(1); }}
            className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none"
          >
            <option value="">All Models</option>
            {options.models.map(m => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>

          {/* Thinking Level Filter */}
          <select
            value={thinking}
            onChange={(e) => { setThinking(e.target.value); setPage(1); }}
            className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none"
          >
            <option value="">All Thinking Levels</option>
            {options.thinkingLevels.map(t => (
              <option key={t} value={t}>{t} Thinking</option>
            ))}
          </select>

          {/* Task Type Filter */}
          <select
            value={taskType}
            onChange={(e) => { setTaskType(e.target.value); setPage(1); }}
            className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none"
          >
            <option value="">All Task Types</option>
            {options.taskTypes.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>

          {/* Source Filter */}
          <select
            value={source}
            onChange={(e) => { setSource(e.target.value); setPage(1); }}
            className="px-3 py-2 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg focus:outline-none"
          >
            <option value="">All Sources</option>
            <option value="cli">CLI</option>
            <option value="ide">IDE</option>
          </select>

          {/* Export JSON Button */}
          <button
            onClick={handleDownloadJSON}
            title="Download currently filtered sessions as JSON"
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-sky-700 bg-sky-50 border border-sky-200 rounded-lg hover:bg-sky-100 transition-colors cursor-pointer ml-auto"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export JSON</span>
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-600">
            <thead className="bg-slate-50 text-slate-700 font-semibold border-b border-slate-200 text-xs uppercase tracking-wider">
              <tr>
                <th className="py-3 px-4">Date</th>
                <th className="py-3 px-4">Conversation ID</th>
                <th className="py-3 px-4">Task Type</th>
                <th className="py-3 px-4">Model & Thinking</th>
                <th className="py-3 px-4">First Prompt / Request</th>
                <th className="py-3 px-4 text-center">Steps</th>
                <th className="py-3 px-4 text-center">Tools</th>
                <th className="py-3 px-4 text-center">Log</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-400">Loading conversations...</td>
                </tr>
              ) : data.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-slate-400">No matching conversations found.</td>
                </tr>
              ) : (
                data.map((row) => {
                  const effectiveType = row.task_type_override || row.task_type;
                  return (
                    <tr key={row.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3 px-4 whitespace-nowrap text-xs font-mono text-slate-500">
                        {row.date_start || '—'}
                      </td>

                      <td className="py-3 px-4 whitespace-nowrap">
                        <Link href={`/sessions/${row.id}`} className="font-mono text-xs font-semibold text-sky-600 hover:text-sky-800 hover:underline">
                          {row.id.slice(0, 8)}
                        </Link>
                        <span className="ml-1.5 px-1.5 py-0.5 text-[10px] uppercase font-bold rounded bg-slate-100 text-slate-500">
                          {row.source_brain}
                        </span>
                      </td>

                      <td className="py-3 px-4 whitespace-nowrap">
                        <select
                          value={effectiveType}
                          onChange={(e) => handleOverrideTaskType(row.id, e.target.value)}
                          className={`text-xs px-2 py-1 font-semibold rounded-full border border-transparent hover:border-slate-300 focus:outline-none cursor-pointer ${getTaskTypeBadgeColor(effectiveType)}`}
                        >
                          {options.taskTypes.map(t => (
                            <option key={t} value={t}>{t}</option>
                          ))}
                        </select>
                        {row.task_type_override && (
                          <span className="ml-1 text-[10px] text-amber-600 font-bold" title="Manually Overridden">*</span>
                        )}
                      </td>

                      <td className="py-3 px-4 whitespace-nowrap text-xs">
                        <div className="font-medium text-slate-800">{row.model_last || row.model_initial || 'Default'}</div>
                        {row.thinking_level && (
                          <div className="text-[10px] text-slate-400 font-medium">{row.thinking_level} Thinking</div>
                        )}
                      </td>

                      <td className="py-3 px-4 max-w-md truncate text-xs text-slate-700" title={row.first_prompt}>
                        <Link href={`/sessions/${row.id}`} className="hover:text-sky-600">
                          {row.first_prompt}
                        </Link>
                      </td>

                      <td className="py-3 px-4 whitespace-nowrap text-center text-xs font-semibold text-slate-600">
                        {row.total_steps}
                      </td>

                      <td className="py-3 px-4 whitespace-nowrap text-center text-xs font-semibold text-slate-600">
                        {row.tool_count}
                      </td>

                      <td className="py-3 px-4 whitespace-nowrap text-center">
                        {row.linked_log_path ? (
                          <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full" title={row.outcome_snippet || 'Linked Session Log'}>
                            <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Log
                          </span>
                        ) : (
                          <span className="text-xs text-slate-400">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Footer */}
        <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-t border-slate-200 text-xs text-slate-500">
          <div>
            Showing <span className="font-semibold text-slate-700">{data.length}</span> of <span className="font-semibold text-slate-700">{totalRecords}</span> conversations
          </div>
          <div className="flex items-center gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage(p => p - 1)}
              className="p-1 rounded border border-slate-200 bg-white disabled:opacity-40 hover:bg-slate-100"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className="font-medium">
              Page {page} of {totalPages}
            </span>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage(p => p + 1)}
              className="p-1 rounded border border-slate-200 bg-white disabled:opacity-40 hover:bg-slate-100"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
