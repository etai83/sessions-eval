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
  const session = sqlite.prepare(`SELECT source_brain FROM sessions WHERE id = ?`).get(id) as any;

  if (!session) {
    return NextResponse.json({ error: 'Session not found' }, { status: 404 });
  }

  const homeDir = os.homedir();
  const rootDir = session.source_brain === 'ide'
    ? path.join(homeDir, '.gemini/antigravity-ide/brain', id)
    : path.join(homeDir, '.gemini/antigravity/brain', id);

  const logsDir = path.join(rootDir, '.system_generated', 'logs');
  const fullTranscript = path.join(logsDir, 'transcript_full.jsonl');
  const compactTranscript = path.join(logsDir, 'transcript.jsonl');

  const targetFile = fs.existsSync(fullTranscript) ? fullTranscript : (fs.existsSync(compactTranscript) ? compactTranscript : null);

  if (!targetFile) {
    return NextResponse.json({ steps: [] });
  }

  const steps: any[] = [];
  try {
    const lines = fs.readFileSync(targetFile, 'utf-8').split('\n');
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const obj = JSON.parse(line);
        steps.push(obj);
      } catch {
        // ignore
      }
    }
  } catch {
    // ignore
  }

  return NextResponse.json({ steps });
}
