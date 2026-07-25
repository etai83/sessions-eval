'use client';

import React, { useEffect, useState } from 'react';
import { Tag } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const CATEGORY_COLORS: Record<string, string> = {
  'ui-frontend': '#3B82F6',
  'backend-api': '#6366F1',
  'database': '#8B5CF6',
  'git-workflow': '#EC4899',
  'testing': '#10B981',
  'devops': '#F59E0B',
  'config-setup': '#64748B',
  'docs': '#0EA5E9',
  'architecture': '#14B8A6',
  'data-analysis': '#84CC16',
  'skills-plugins': '#F43F5E',
  'general': '#94A3B8',
};

export function RequestTopics({ refreshKey }: { refreshKey?: number }) {
  const [categories, setCategories] = useState<Array<{ category: string; count: number }>>([]);
  const [totalSessions, setTotalSessions] = useState(0);

  useEffect(() => {
    fetch('/api/analytics')
      .then(res => res.json())
      .then(d => {
        if (d?.charts?.requestCategories) {
          setCategories(d.charts.requestCategories);
          const total = d.charts.requestCategories.reduce((acc: number, item: any) => acc + item.count, 0);
          setTotalSessions(total);
        }
      })
      .catch(() => {});
  }, [refreshKey]);

  if (!categories || categories.length === 0) return null;

  const chartData = categories.map(c => ({
    name: c.category,
    count: c.count,
  }));

  return (
    <div className="p-5 bg-white rounded-xl border border-slate-200 shadow-xs mb-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Tag className="w-5 h-5 text-indigo-600" />
          <h2 className="text-base font-bold text-slate-800">Common Request Topics</h2>
        </div>
        <span className="text-xs text-slate-500 bg-slate-100 px-2.5 py-1 rounded-full font-medium">
          {categories.length} Topics Identified
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-center">
        {/* Horizontal Bar Chart */}
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical" margin={{ left: 20, right: 25, top: 5, bottom: 5 }}>
              <XAxis type="number" hide />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 11, fill: '#475569' }} width={110} />
              <Tooltip
                formatter={(value: any) => [`${value} sessions`, 'Count']}
                contentStyle={{ backgroundColor: '#0F172A', borderRadius: '8px', color: '#fff', fontSize: '12px' }}
              />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={16}>
                {chartData.map((entry) => (
                  <Cell key={entry.name} fill={CATEGORY_COLORS[entry.name] || '#94A3B8'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Detailed Breakdown Table */}
        <div className="overflow-hidden border border-slate-100 rounded-lg">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-100 text-slate-500 font-semibold uppercase tracking-wider">
              <tr>
                <th className="py-2.5 px-3">Topic Category</th>
                <th className="py-2.5 px-3 text-right">Sessions</th>
                <th className="py-2.5 px-3 text-right">% Share</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-medium">
              {categories.map((c) => {
                const percentage = totalSessions > 0 ? ((c.count / totalSessions) * 100).toFixed(1) : '0';
                return (
                  <tr key={c.category} className="hover:bg-slate-50 transition-colors">
                    <td className="py-2 px-3 flex items-center gap-2 text-slate-700 capitalize">
                      <span
                        className="w-2.5 h-2.5 rounded-full inline-block shrink-0"
                        style={{ backgroundColor: CATEGORY_COLORS[c.category] || '#94A3B8' }}
                      />
                      {c.category}
                    </td>
                    <td className="py-2 px-3 text-right text-slate-900 font-semibold">{c.count}</td>
                    <td className="py-2 px-3 text-right text-slate-500">{percentage}%</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
