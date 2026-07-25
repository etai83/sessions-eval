import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';

export const sessions = sqliteTable('sessions', {
  id: text('id').primaryKey(), // Conversation id UUID
  sourceBrain: text('source_brain').notNull(), // 'cli' | 'ide'
  firstPrompt: text('first_prompt').notNull(),
  modelInitial: text('model_initial'),
  modelLast: text('model_last'),
  thinkingLevel: text('thinking_level'), // 'Low' | 'Medium' | 'High' | null
  taskType: text('task_type').notNull(), // 'feature' | 'debug' | 'refactor' | 'research' | 'config' | 'setup'
  taskTypeOverride: text('task_type_override'), // User manual override tag
  totalSteps: integer('total_steps').notNull().default(0),
  userRequestCount: integer('user_request_count').notNull().default(0),
  dateStart: text('date_start'),
  dateEnd: text('date_end'),
  linkedLogPath: text('linked_log_path'),
  outcomeSnippet: text('outcome_snippet'),
  indexedAt: text('indexed_at').notNull(),
});

export const toolCalls = sqliteTable('tool_calls', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  sessionId: text('session_id').notNull().references(() => sessions.id, { onDelete: 'cascade' }),
  toolName: text('tool_name').notNull(),
  callCount: integer('call_count').notNull().default(0),
});
