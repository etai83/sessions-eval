import fs from 'fs';
import path from 'path';
import os from 'os';
import { sqlite } from '../db';

const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

const CONVERSATION_ID_RE = new RegExp(
  '\\*\\*Conversation ID:\\*\\*\\s*`?(?<id>' + UUID_RE.source + ')`?' +
  '|\\*\\*Conversation ID\\*\\*\\s*:\\s*`?(?<id2>' + UUID_RE.source + ')`?',
  'i'
);

const SESSION_ID_META_RE = new RegExp(
  '^\\s*(?:[-*]\\s*)?(?:' +
  '\\*\\*Session ID:\\*\\*\\s*`?(?<id>' + UUID_RE.source + ')`?' +
  '|\\*\\*Session ID\\*\\*\\s*:\\s*`?(?<id2>' + UUID_RE.source + ')`?' +
  ')\\s*$',
  'im'
);

const BRAIN_PATH_RE = new RegExp(
  '(?:file://)?[^\\s\\)"\']*?/\\.gemini/antigravity(?:-ide)?/brain/' +
  '(?<id>' + UUID_RE.source + ')',
  'i'
);

const OUTCOME_HEADINGS = [
  'Results / Outcomes',
  'Results Observed',
  'Outcomes',
  'Results',
  'Result',
];

export function extractConversationLink(text: string): { cid: string; reason: string } | null {
  let m = CONVERSATION_ID_RE.exec(text);
  if (m && m.groups) {
    const cid = (m.groups.id || m.groups.id2 || '').toLowerCase();
    if (cid) return { cid, reason: 'conversation_id' };
  }

  m = SESSION_ID_META_RE.exec(text);
  if (m && m.groups) {
    const cid = (m.groups.id || m.groups.id2 || '').toLowerCase();
    if (cid) return { cid, reason: 'session_id' };
  }

  m = BRAIN_PATH_RE.exec(text);
  if (m && m.groups) {
    const cid = (m.groups.id || '').toLowerCase();
    if (cid) return { cid, reason: 'brain_path' };
  }

  return null;
}

export function extractOutcomeSnippet(text: string): string | null {
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const match = line.match(/^#{1,6}\s+(.+?)\s*$/);
    if (!match) continue;
    const headingTitle = match[1].trim();
    if (OUTCOME_HEADINGS.some(h => headingTitle.toLowerCase().includes(h.toLowerCase()))) {
      const level = line.match(/^#{1,6}/)?.[0].length || 1;
      const bodyLines: string[] = [];
      for (let j = i + 1; j < lines.length; j++) {
        const nextMatch = lines[j].match(/^#{1,6}\s+(.+?)\s*$/);
        if (nextMatch) {
          const nextLevel = lines[j].match(/^#{1,6}/)?.[0].length || 1;
          if (nextLevel <= level) break;
        }
        bodyLines.push(lines[j]);
      }
      const rawBody = bodyLines.join('\n').replace(/\s+/g, ' ').trim();
      if (rawBody) {
        return rawBody.length > 180 ? rawBody.slice(0, 179) + '…' : rawBody;
      }
    }
  }
  return null;
}

export function runSessionLogsIngester(): { totalLogs: number; linkedLogs: number } {
  const logsDir = path.join(os.homedir(), 'Documents', 'session-logs');
  if (!fs.existsSync(logsDir)) {
    return { totalLogs: 0, linkedLogs: 0 };
  }

  const updateSessionLink = sqlite.prepare(`
    UPDATE sessions
    SET linked_log_path = ?, outcome_snippet = ?
    WHERE id = ?
  `);

  let totalLogs = 0;
  let linkedLogs = 0;

  function scanDir(dirPath: string) {
    const entries = fs.readdirSync(dirPath, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dirPath, entry.name);
      if (entry.isDirectory()) {
        scanDir(fullPath);
      } else if (entry.isFile() && entry.name.endsWith('.md')) {
        totalLogs++;
        try {
          const text = fs.readFileSync(fullPath, 'utf-8');
          const link = extractConversationLink(text);
          const outcome = extractOutcomeSnippet(text);
          const relPath = path.relative(logsDir, fullPath).replace(/\\/g, '/');

          if (link) {
            const info = updateSessionLink.run(relPath, outcome, link.cid);
            if (info.changes > 0) {
              linkedLogs++;
            }
          }
        } catch {
          // ignore read errors
        }
      }
    }
  }

  scanDir(logsDir);
  return { totalLogs, linkedLogs };
}
