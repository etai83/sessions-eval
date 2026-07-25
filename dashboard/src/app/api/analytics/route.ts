import { NextResponse } from 'next/server';
import { sqlite } from '@/db';

export async function GET() {
  const totalSessions = (sqlite.prepare(`SELECT COUNT(*) as count FROM sessions`).get() as any).count;

  // Top model
  const topModelRow = sqlite.prepare(`
    SELECT COALESCE(model_last, model_initial, 'Default') as model, COUNT(*) as count
    FROM sessions
    GROUP BY model
    ORDER BY count DESC
    LIMIT 1
  `).get() as any;

  // Top tool
  const topToolRow = sqlite.prepare(`
    SELECT tool_name, SUM(call_count) as total
    FROM tool_calls
    GROUP BY tool_name
    ORDER BY total DESC
    LIMIT 1
  `).get() as any;

  // Task type breakdown
  const taskTypeBreakdown = sqlite.prepare(`
    SELECT COALESCE(task_type_override, task_type) as task_type, COUNT(*) as count
    FROM sessions
    GROUP BY task_type
    ORDER BY count DESC
  `).all();

  // Top 8 tools chart data
  const topToolsData = sqlite.prepare(`
    SELECT tool_name as name, SUM(call_count) as calls
    FROM tool_calls
    GROUP BY tool_name
    ORDER BY calls DESC
    LIMIT 8
  `).all();

  // Model distribution chart data
  const modelDistData = sqlite.prepare(`
    SELECT COALESCE(model_last, model_initial, 'Default') as model, COUNT(*) as count
    FROM sessions
    GROUP BY model
    ORDER BY count DESC
  `).all();

  return NextResponse.json({
    summary: {
      totalSessions,
      topModel: topModelRow?.model || 'N/A',
      topTool: topToolRow?.tool_name || 'N/A',
      topToolCalls: topToolRow?.total || 0,
      linkedLogs: (sqlite.prepare(`SELECT COUNT(*) as count FROM sessions WHERE linked_log_path IS NOT NULL`).get() as any).count,
    },
    charts: {
      taskTypes: taskTypeBreakdown,
      topTools: topToolsData,
      models: modelDistData,
    },
  });
}
