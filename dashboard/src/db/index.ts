import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import * as schema from './schema';
import path from 'path';
import fs from 'fs';

const dbDir = path.join(process.cwd(), '.data');
if (!fs.existsSync(dbDir)) {
  fs.mkdirSync(dbDir, { recursive: true });
}

const dbPath = path.join(dbDir, 'sessions.db');
const sqlite = new Database(dbPath);
sqlite.pragma('journal_mode = WAL');

// Ensure tables exist on boot
sqlite.exec(`
  CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    source_brain TEXT NOT NULL,
    first_prompt TEXT NOT NULL,
    model_initial TEXT,
    model_last TEXT,
    thinking_level TEXT,
    task_type TEXT NOT NULL,
    task_type_override TEXT,
    total_steps INTEGER NOT NULL DEFAULT 0,
    user_request_count INTEGER NOT NULL DEFAULT 0,
    date_start TEXT,
    date_end TEXT,
    linked_log_path TEXT,
    outcome_snippet TEXT,
    indexed_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    call_count INTEGER NOT NULL DEFAULT 0
  );
`);

export const db = drizzle(sqlite, { schema });
export { sqlite };
