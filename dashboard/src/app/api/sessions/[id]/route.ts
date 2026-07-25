import { NextRequest, NextResponse } from 'next/server';
import { sqlite } from '@/db';
import fs from 'fs';
import path from 'path';
import os from 'os';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const session = sqlite.prepare(`
    SELECT * FROM sessions WHERE id = ?
  `).get(id) as any;

  if (!session) {
    return NextResponse.json({ error: 'Session not found' }, { status: 404 });
  }

  const tools = sqlite.prepare(`
    SELECT tool_name, call_count FROM tool_calls WHERE session_id = ? ORDER BY call_count DESC
  `).all(id);

  // Read linked log markdown content if present
  let linkedLogMarkdown: string | null = null;
  if (session.linked_log_path) {
    const fullLogPath = path.join(os.homedir(), 'Documents', 'session-logs', session.linked_log_path);
    if (fs.existsSync(fullLogPath)) {
      try {
        linkedLogMarkdown = fs.readFileSync(fullLogPath, 'utf-8');
      } catch {
        // ignore
      }
    }
  }

  return NextResponse.json({
    session,
    tools,
    linkedLogMarkdown,
  });
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const body = await request.json();
  const { task_type_override } = body;

  const updateStmt = sqlite.prepare(`
    UPDATE sessions
    SET task_type_override = ?
    WHERE id = ?
  `);

  updateStmt.run(task_type_override !== undefined ? task_type_override : null, id);

  return NextResponse.json({ success: true, id, task_type_override });
}
