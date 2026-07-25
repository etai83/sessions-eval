'use client';

import React, { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { ArrowLeft, FileText, Wrench, ListTree, CheckCircle2, ChevronDown, ChevronRight, Cpu, Clock, Terminal } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';

export default function SessionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [data, setData] = useState<any>(null);
  const [transcript, setTranscript] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingTranscript, setLoadingTranscript] = useState(false);
  const [activeTab, setActiveTab] = useState<'log' | 'tools' | 'timeline'>('log');
  const [expandedSteps, setExpandedSteps] = useState<Record<number, boolean>>({});

  useEffect(() => {
    fetch(`/api/sessions/${id}`)
      .then(res => res.json())
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (activeTab === 'timeline' && transcript.length === 0) {
      setLoadingTranscript(true);
      fetch(`/api/sessions/${id}/transcript`)
        .then(res => res.json())
        .then(d => {
          setTranscript(d.steps || []);
          setLoadingTranscript(false);
        })
        .catch(() => setLoadingTranscript(false));
    }
  }, [activeTab, id, transcript.length]);

  const handleOverrideTaskType = async (newType: string) => {
    try {
      await fetch(`/api/sessions/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_type_override: newType === 'AUTO' ? null : newType }),
      });
      const updated = await (await fetch(`/api/sessions/${id}`)).json();
      setData(updated);
    } catch {
      // ignore
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-100 p-8 flex items-center justify-center text-slate-500">
        Loading session details...
      </div>
    );
  }

  if (!data || !data.session) {
    return (
      <div className="min-h-screen bg-slate-100 p-8 text-center">
        <h1 className="text-xl font-bold text-slate-800">Session Not Found</h1>
        <Link href="/" className="mt-4 inline-flex items-center gap-2 text-sky-600 font-semibold hover:underline">
          <ArrowLeft className="w-4 h-4" /> Back to Dashboard
        </Link>
      </div>
    );
  }

  const { session, tools, linkedLogMarkdown } = data;
  const effectiveType = session.task_type_override || session.task_type;

  return (
    <main className="min-h-screen bg-slate-100 text-slate-900 pb-12">
      {/* Top Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center gap-4 mb-2">
            <Link href="/" className="p-2 text-slate-500 hover:bg-slate-100 rounded-lg transition-colors">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm font-bold text-sky-600">{session.id}</span>
                <span className="px-2 py-0.5 text-[10px] uppercase font-bold rounded bg-slate-100 text-slate-600">
                  {session.source_brain}
                </span>
                {session.linked_log_path && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                    <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Linked Log
                  </span>
                )}
              </div>
              <h1 className="text-base font-semibold text-slate-800 mt-1">{session.first_prompt}</h1>
            </div>
          </div>

          {/* Badges Bar */}
          <div className="flex flex-wrap items-center gap-4 pt-3 border-t border-slate-100 text-xs text-slate-500">
            <div className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-slate-400" />
              <span>{session.date_start} {session.date_end && session.date_end !== session.date_start ? `→ ${session.date_end}` : ''}</span>
            </div>

            <div className="flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-slate-400" />
              <span className="font-medium text-slate-700">{session.model_last || session.model_initial || 'Default'}</span>
              {session.thinking_level && <span className="text-[10px] text-slate-400">({session.thinking_level} Thinking)</span>}
            </div>

            <div className="flex items-center gap-1.5">
              <span className="font-medium">Task Type:</span>
              <select
                value={effectiveType}
                onChange={(e) => handleOverrideTaskType(e.target.value)}
                className="text-xs px-2.5 py-0.5 font-semibold rounded-full bg-slate-100 border border-slate-200 focus:outline-none cursor-pointer"
              >
                {['feature', 'debug', 'refactor', 'research', 'config', 'setup'].map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </header>

      {/* Main Tabs Container */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        <div className="flex border-b border-slate-200 gap-2 mb-6">
          <button
            onClick={() => setActiveTab('log')}
            className={`flex items-center gap-2 px-4 py-2.5 font-semibold text-sm border-b-2 transition-colors ${activeTab === 'log' ? 'border-sky-600 text-sky-600 bg-white rounded-t-lg' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
          >
            <FileText className="w-4 h-4" /> Outcome & Session Log
          </button>
          <button
            onClick={() => setActiveTab('tools')}
            className={`flex items-center gap-2 px-4 py-2.5 font-semibold text-sm border-b-2 transition-colors ${activeTab === 'tools' ? 'border-sky-600 text-sky-600 bg-white rounded-t-lg' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
          >
            <Wrench className="w-4 h-4" /> Tool Analytics ({tools.length})
          </button>
          <button
            onClick={() => setActiveTab('timeline')}
            className={`flex items-center gap-2 px-4 py-2.5 font-semibold text-sm border-b-2 transition-colors ${activeTab === 'timeline' ? 'border-sky-600 text-sky-600 bg-white rounded-t-lg' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
          >
            <ListTree className="w-4 h-4" /> Transcript Timeline ({session.total_steps} steps)
          </button>
        </div>

        {/* Tab 1: Outcome & Session Log */}
        {activeTab === 'log' && (
          <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs">
            {linkedLogMarkdown ? (
              <article className="prose prose-slate max-w-none prose-sm font-sans">
                <pre className="whitespace-pre-wrap font-sans text-sm text-slate-800 leading-relaxed">{linkedLogMarkdown}</pre>
              </article>
            ) : (
              <div className="py-12 text-center text-slate-400">
                <FileText className="w-12 h-12 mx-auto mb-3 text-slate-300" />
                <p className="font-semibold text-slate-600">No Linked Session Log</p>
                <p className="text-xs mt-1">This conversation does not have an attached human-authored Markdown log file in <code>~/Documents/session-logs</code>.</p>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Tool Analytics */}
        {activeTab === 'tools' && (
          <div className="space-y-6">
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs">
              <h3 className="text-sm font-semibold text-slate-700 mb-4">Tool Execution Frequency</h3>
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={tools} layout="vertical" margin={{ left: 20, right: 20 }}>
                    <XAxis type="number" />
                    <YAxis dataKey="tool_name" type="category" tick={{ fontSize: 12 }} width={140} />
                    <Tooltip />
                    <Bar dataKey="call_count" fill="#6366F1" radius={[0, 4, 4, 0]} barSize={18} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 border-b border-slate-200 text-xs text-slate-500 font-semibold uppercase">
                  <tr>
                    <th className="py-3 px-4">Tool Name</th>
                    <th className="py-3 px-4 text-right">Invocations</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {tools.map((t: any) => (
                    <tr key={t.tool_name}>
                      <td className="py-2.5 px-4 font-mono text-xs font-semibold text-slate-800">{t.tool_name}</td>
                      <td className="py-2.5 px-4 text-right font-mono text-xs text-slate-600">{t.call_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab 3: Transcript Timeline */}
        {activeTab === 'timeline' && (
          <div className="space-y-3">
            {loadingTranscript ? (
              <div className="p-8 text-center text-slate-400 bg-white rounded-xl border border-slate-200">
                Loading transcript timeline...
              </div>
            ) : transcript.length === 0 ? (
              <div className="p-8 text-center text-slate-400 bg-white rounded-xl border border-slate-200">
                No transcript steps available.
              </div>
            ) : (
              transcript.map((step, idx) => {
                const isUser = step.type === 'USER_INPUT' || step.type === 'USER_EXPLICIT' || step.source === 'USER_EXPLICIT';
                const isPlanner = step.type === 'PLANNER_RESPONSE';
                const hasTools = Array.isArray(step.tool_calls) && step.tool_calls.length > 0;
                const isExpanded = expandedSteps[idx];

                return (
                  <div
                    key={idx}
                    className={`rounded-xl border p-4 transition-colors ${isUser ? 'bg-sky-50/60 border-sky-200' : isPlanner ? 'bg-purple-50/40 border-purple-200' : 'bg-white border-slate-200'}`}
                  >
                    <div
                      className="flex items-center justify-between cursor-pointer select-none"
                      onClick={() => setExpandedSteps(prev => ({ ...prev, [idx]: !prev[idx] }))}
                    >
                      <div className="flex items-center gap-2">
                        {isExpanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                        <span className="font-mono text-xs font-bold text-slate-500">#{step.step_index ?? idx}</span>
                        <span className={`text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded ${isUser ? 'bg-sky-200 text-sky-800' : isPlanner ? 'bg-purple-200 text-purple-800' : 'bg-slate-200 text-slate-700'}`}>
                          {step.type || step.source || 'Step'}
                        </span>
                        {hasTools && (
                          <span className="text-xs font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200">
                            {step.tool_calls.length} Tool Call(s)
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] font-mono text-slate-400">{step.created_at || ''}</span>
                    </div>

                    {/* Step Preview & Expanded View */}
                    <div className="mt-2 text-xs">
                      {!isExpanded ? (
                        <p className="text-slate-600 line-clamp-2 font-mono">
                          {step.content || step.thinking || (hasTools ? `Executed ${step.tool_calls.map((t: any) => t.name).join(', ')}` : '')}
                        </p>
                      ) : (
                        <div className="space-y-3 pt-2 border-t border-slate-200/60">
                          {step.content && (
                            <div>
                              <div className="font-semibold text-slate-500 mb-1">Content:</div>
                              <pre className="p-3 bg-slate-900 text-slate-100 rounded-lg whitespace-pre-wrap font-mono text-[11px] overflow-x-auto">
                                {step.content}
                              </pre>
                            </div>
                          )}

                          {step.thinking && (
                            <div>
                              <div className="font-semibold text-purple-700 mb-1">Thinking Process:</div>
                              <pre className="p-3 bg-purple-950 text-purple-100 rounded-lg whitespace-pre-wrap font-mono text-[11px] overflow-x-auto">
                                {step.thinking}
                              </pre>
                            </div>
                          )}

                          {hasTools && (
                            <div>
                              <div className="font-semibold text-slate-500 mb-1">Tool Executions:</div>
                              <div className="space-y-2">
                                {step.tool_calls.map((tc: any, tIdx: number) => (
                                  <div key={tIdx} className="p-3 bg-slate-800 text-slate-100 rounded-lg font-mono text-[11px]">
                                    <div className="font-bold text-amber-400 mb-1">Tool: {tc.name}</div>
                                    <pre className="whitespace-pre-wrap text-slate-300">
                                      {JSON.stringify(tc.args || {}, null, 2)}
                                    </pre>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
    </main>
  );
}
