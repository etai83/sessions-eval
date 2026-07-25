import fs from 'fs';
import path from 'path';
import os from 'os';
import { db, sqlite } from '../db';
import { sessions, toolCalls } from '../db/schema';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MODEL_SETTING_RE = /The user changed setting `?Model Selection`? from .*? to (.*?)(?:\s*\((High|Medium|Low|Thinking)\))?\s*\.\s*(?:No need|<\/USER_SETTINGS_CHANGE>|$)/i;

export interface ExtractedMetadata {
  firstPrompt: string;
  totalSteps: number;
  userRequestCount: number;
  dateStart: string;
  dateEnd: string;
  modelInitial: string | null;
  modelLast: string | null;
  thinkingLevel: string | null;
  toolCallCounts: Record<string, number>;
}

export function parseTranscript(filePath: string): ExtractedMetadata {
  let firstPrompt = '';
  let totalSteps = 0;
  let userRequestCount = 0;
  let dateStart = '';
  let dateEnd = '';
  let modelInitial: string | null = null;
  let modelLast: string | null = null;
  let thinkingLevel: string | null = null;
  const toolCallCounts: Record<string, number> = {};

  try {
    const fileContent = fs.readFileSync(filePath, 'utf-8');
    const lines = fileContent.split('\n');

    for (const line of lines) {
      if (!line.trim()) continue;
      totalSteps++;
      try {
        const obj = JSON.parse(line);
        const ts = obj.created_at ? String(obj.created_at).slice(0, 10) : '';
        if (ts) {
          if (!dateStart || ts < dateStart) dateStart = ts;
          if (!dateEnd || ts > dateEnd) dateEnd = ts;
        }

        const type = String(obj.type || '');
        const source = String(obj.source || '');
        const content = String(obj.content || '');

        // Extract settings changes (Model & Thinking level)
        if (content.includes('USER_SETTINGS_CHANGE') || content.includes('Model Selection')) {
          const match = MODEL_SETTING_RE.exec(content);
          if (match) {
            const rawModel = match[1].trim();
            const rawThinking = match[2] ? match[2].trim() : null;
            if (rawModel) {
              if (!modelInitial) modelInitial = rawModel;
              modelLast = rawModel;
              if (rawThinking) thinkingLevel = rawThinking;
            }
          }
        }

        // Extract User Input / Prompts
        if (type === 'USER_INPUT' || type === 'USER_EXPLICIT' || source === 'USER_EXPLICIT' || source === 'USER_INPUT') {
          userRequestCount++;
          if (!firstPrompt && content) {
            const clean = content.replace(/<\/?USER_REQUEST>/gi, '').trim();
            if (clean) {
              const firstLine = clean.split('\n')[0].replace(/\s+/g, ' ').trim();
              firstPrompt = firstLine.length > 200 ? firstLine.slice(0, 199) + '…' : firstLine;
            }
          }
        }

        // Aggregate Tool Calls
        if (Array.isArray(obj.tool_calls) && obj.tool_calls.length > 0) {
          for (const tc of obj.tool_calls) {
            if (tc && typeof tc === 'object' && tc.name) {
              const name = String(tc.name).toLowerCase();
              toolCallCounts[name] = (toolCallCounts[name] || 0) + 1;
            }
          }
        } else if (type && !['USER_INPUT', 'USER_EXPLICIT', 'PLANNER_RESPONSE', 'RAW', 'CONVERSATION_HISTORY', 'CHECKPOINT'].includes(type)) {
          const name = type.toLowerCase();
          toolCallCounts[name] = (toolCallCounts[name] || 0) + 1;
        }

      } catch {
        // Skip malformed json lines
      }
    }
  } catch {
    // Return defaults if file read fails
  }

  // Fallback default for sessions without explicit setting change tags
  if (!modelLast) {
    modelLast = 'Gemini 3.5 Flash';
    modelInitial = 'Gemini 3.5 Flash';
    thinkingLevel = 'Default';
  }

  return {
    firstPrompt: firstPrompt || 'Untitled Conversation',
    totalSteps,
    userRequestCount,
    dateStart,
    dateEnd,
    modelInitial,
    modelLast,
    thinkingLevel,
    toolCallCounts,
  };
}

export function runIndexer(options: { force?: boolean } = {}): { conversationsIndexed: number; toolCallsIndexed: number } {
  const homeDir = os.homedir();
  const brainRoots = [
    { path: path.join(homeDir, '.gemini/antigravity/brain'), source: 'cli' },
    { path: path.join(homeDir, '.gemini/antigravity-ide/brain'), source: 'ide' },
  ];

  let conversationsIndexed = 0;
  let toolCallsIndexed = 0;

  // Prepare SQLite statements for fast batch insertion
  const upsertSession = sqlite.prepare(`
    INSERT INTO sessions (
      id, source_brain, first_prompt, model_initial, model_last, thinking_level,
      task_type, request_category, total_steps, user_request_count, date_start, date_end, indexed_at
    ) VALUES (
      @id, @source_brain, @first_prompt, @model_initial, @model_last, @thinking_level,
      @task_type, @request_category, @total_steps, @user_request_count, @date_start, @date_end, @indexed_at
    )
    ON CONFLICT(id) DO UPDATE SET
      first_prompt = excluded.first_prompt,
      model_initial = excluded.model_initial,
      model_last = excluded.model_last,
      thinking_level = excluded.thinking_level,
      total_steps = excluded.total_steps,
      user_request_count = excluded.user_request_count,
      date_start = excluded.date_start,
      date_end = excluded.date_end,
      indexed_at = excluded.indexed_at
  `);

  const deleteToolCalls = sqlite.prepare(`DELETE FROM tool_calls WHERE session_id = ?`);
  const insertToolCall = sqlite.prepare(`INSERT INTO tool_calls (session_id, tool_name, call_count) VALUES (?, ?, ?)`);

  for (const { path: rootPath, source } of brainRoots) {
    if (!fs.existsSync(rootPath)) continue;
    const entries = fs.readdirSync(rootPath, { withFileTypes: true });

    for (const entry of entries) {
      if (!entry.isDirectory() || !UUID_RE.test(entry.name)) continue;
      const cid = entry.name.toLowerCase();
      const logsDir = path.join(rootPath, entry.name, '.system_generated', 'logs');
      const fullTranscript = path.join(logsDir, 'transcript_full.jsonl');
      const compactTranscript = path.join(logsDir, 'transcript.jsonl');

      const targetFile = fs.existsSync(fullTranscript) ? fullTranscript : (fs.existsSync(compactTranscript) ? compactTranscript : null);
      if (!targetFile) continue;

      const stat = fs.statSync(targetFile);
      const mtimeIso = new Date(stat.mtimeMs).toISOString();

      if (!options.force) {
        const existing = sqlite.prepare(`SELECT indexed_at FROM sessions WHERE id = ?`).get(cid) as { indexed_at: string } | undefined;
        if (existing && existing.indexed_at >= mtimeIso) {
          continue; // Skip unchanged file
        }
      }

      const meta = parseTranscript(targetFile);

      // Default heuristic task type classifier (will be enhanced by classifier module)
      const taskType = 'general';
      const requestCategory = 'general';

      sqlite.transaction(() => {
        upsertSession.run({
          id: cid,
          source_brain: source,
          first_prompt: meta.firstPrompt,
          model_initial: meta.modelInitial,
          model_last: meta.modelLast,
          thinking_level: meta.thinkingLevel,
          task_type: taskType,
          request_category: requestCategory,
          total_steps: meta.totalSteps,
          user_request_count: meta.userRequestCount,
          date_start: meta.dateStart,
          date_end: meta.dateEnd,
          indexed_at: new Date().toISOString(),
        });

        deleteToolCalls.run(cid);
        for (const [toolName, count] of Object.entries(meta.toolCallCounts)) {
          insertToolCall.run(cid, toolName, count);
          toolCallsIndexed++;
        }
      })();

      conversationsIndexed++;
    }
  }

  return { conversationsIndexed, toolCallsIndexed };
}
