import { NextRequest, NextResponse } from 'next/server';
import { sqlite } from '@/db';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get('q') || '';
  const model = searchParams.get('model') || '';
  const thinking = searchParams.get('thinking') || '';
  const taskType = searchParams.get('task_type') || '';
  const category = searchParams.get('category') || '';
  const source = searchParams.get('source') || '';
  const page = parseInt(searchParams.get('page') || '1', 10);
  const pageSize = parseInt(searchParams.get('pageSize') || '20', 10);

  let whereClauses: string[] = [];
  let params: any[] = [];

  if (query) {
    whereClauses.push('(id LIKE ? OR first_prompt LIKE ? OR outcome_snippet LIKE ?)');
    const qStr = `%${query}%`;
    params.push(qStr, qStr, qStr);
  }

  if (model) {
    whereClauses.push('(model_initial = ? OR model_last = ?)');
    params.push(model, model);
  }

  if (thinking) {
    whereClauses.push('thinking_level = ?');
    params.push(thinking);
  }

  if (taskType) {
    whereClauses.push('(COALESCE(task_type_override, task_type) = ?)');
    params.push(taskType);
  }

  if (category) {
    whereClauses.push('COALESCE(request_category, "general") = ?');
    params.push(category);
  }

  if (source) {
    whereClauses.push('source_brain = ?');
    params.push(source);
  }

  const whereSql = whereClauses.length > 0 ? `WHERE ${whereClauses.join(' AND ')}` : '';

  // Get total count
  const countStmt = sqlite.prepare(`SELECT COUNT(*) as total FROM sessions ${whereSql}`);
  const total = (countStmt.get(...params) as { total: number }).total;

  // Get paginated rows
  const offset = (page - 1) * pageSize;
  const sql = `
    SELECT 
      id, source_brain, first_prompt, model_initial, model_last, thinking_level,
      task_type, task_type_override, request_category, total_steps, user_request_count, date_start, date_end,
      linked_log_path, outcome_snippet, indexed_at,
      (SELECT COUNT(*) FROM tool_calls WHERE session_id = sessions.id) as tool_count
    FROM sessions
    ${whereSql}
    ORDER BY date_start DESC, id DESC
    LIMIT ? OFFSET ?
  `;

  const rows = sqlite.prepare(sql).all(...params, pageSize, offset);

  // Filter options metadata
  const models = (sqlite.prepare(`SELECT DISTINCT model_last FROM sessions WHERE model_last IS NOT NULL`).all() as any[]).map(r => r.model_last);
  const thinkingLevels = ['Low', 'Medium', 'High'];
  const taskTypes = ['feature', 'debug', 'refactor', 'research', 'config', 'setup'];
  const requestCategories = (sqlite.prepare(`SELECT DISTINCT COALESCE(request_category, 'general') as category FROM sessions`).all() as any[]).map(r => r.category);
  const sources = ['cli', 'ide'];

  return NextResponse.json({
    sessions: rows,
    pagination: {
      page,
      pageSize,
      total,
      totalPages: Math.ceil(total / pageSize),
    },
    filterOptions: {
      models,
      thinkingLevels,
      taskTypes,
      requestCategories,
      sources,
    },
  });
}
