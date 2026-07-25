import fs from 'fs';
import path from 'path';
import { sqlite } from '../db';

export interface TaskRule {
  task_type: string;
  prompt_keywords: string[];
  tools?: string[];
}

export interface TaskRulesConfig {
  default_task_type: string;
  rules: TaskRule[];
}

let rulesConfig: TaskRulesConfig | null = null;

export function loadTaskRules(): TaskRulesConfig {
  if (rulesConfig) return rulesConfig;
  const rulesPath = path.join(process.cwd(), 'config', 'task_rules.json');
  if (fs.existsSync(rulesPath)) {
    try {
      rulesConfig = JSON.parse(fs.readFileSync(rulesPath, 'utf-8'));
      return rulesConfig!;
    } catch {
      // fallback
    }
  }
  return {
    default_task_type: 'feature',
    rules: [
      { task_type: 'debug', prompt_keywords: ['fix', 'bug', 'debug', 'error', 'failing'] },
      { task_type: 'refactor', prompt_keywords: ['refactor', 'rewrite', 'clean'] },
      { task_type: 'research', prompt_keywords: ['explore', 'search', 'explain', 'what is', 'how'] },
      { task_type: 'config', prompt_keywords: ['config', 'setting', 'install'] },
      { task_type: 'feature', prompt_keywords: ['build', 'create', 'add', 'implement'] },
    ],
  };
}

export const REQUEST_CATEGORY_RULES: Record<string, string[]> = {
  'ui-frontend': ['dashboard', 'component', 'button', 'layout', 'css', 'style', 'page', 'ui', 'modal', 'form', 'react', 'next', 'view', 'display', 'frontend'],
  'backend-api': ['api', 'route', 'endpoint', 'server', 'handler', 'middleware', 'rest', 'http', 'post', 'get', 'backend'],
  'database': ['schema', 'query', 'sql', 'migration', 'table', 'database', 'db', 'sqlite', 'drizzle', 'column', 'row', 'store'],
  'git-workflow': ['branch', 'commit', 'merge', 'pr', 'rebase', 'git', 'push', 'pull', 'cherry-pick', 'repository', 'repo'],
  'testing': ['test', 'spec', 'assert', 'coverage', 'jest', 'vitest', 'mock', 'tdd'],
  'devops': ['deploy', 'ci/cd', 'docker', 'build', 'pipeline', 'kubernetes', 'cloud', 'host'],
  'config-setup': ['install', 'config', 'setup', 'env', 'package', 'dependency', 'npm', 'setting', 'json'],
  'docs': ['readme', 'document', 'doc', 'comment', 'explain', 'jsdoc', 'markdown', 'md', 'ticket', 'issue'],
  'architecture': ['design', 'refactor', 'pattern', 'module', 'structure', 'interface', 'class', 'type', 'schema'],
  'data-analysis': ['analyze', 'chart', 'visualize', 'metrics', 'data', 'graph', 'plot', 'cluster', 'stats', 'analytics'],
  'skills-plugins': ['skill', 'plugin', 'extension', 'mcp', 'agent', 'tool', 'slash', 'subagent'],
};

export function classifyRequestCategory(prompt: string): string {
  const lower = prompt.toLowerCase();
  let bestCategory = 'general';
  let maxScore = 0;

  for (const [category, keywords] of Object.entries(REQUEST_CATEGORY_RULES)) {
    let score = 0;
    for (const kw of keywords) {
      if (lower.includes(kw)) {
        score++;
      }
    }
    if (score > maxScore) {
      maxScore = score;
      bestCategory = category;
    }
  }

  return bestCategory;
}

export function classifyConversation(prompt: string, toolNames: string[]): string {
  const config = loadTaskRules();
  const lowerPrompt = prompt.toLowerCase();
  const lowerTools = toolNames.map(t => t.toLowerCase());

  let bestMatch = config.default_task_type;
  let maxScore = 0;

  for (const rule of config.rules) {
    let score = 0;
    for (const kw of rule.prompt_keywords) {
      if (lowerPrompt.includes(kw.toLowerCase())) {
        score += 2;
      }
    }

    if (rule.tools) {
      for (const tool of rule.tools) {
        if (lowerTools.includes(tool.toLowerCase())) {
          score += 1;
        }
      }
    }

    if (score > maxScore) {
      maxScore = score;
      bestMatch = rule.task_type;
    }
  }

  return bestMatch;
}

export function classifyAllIndexedSessions(): number {
  const selectSessions = sqlite.prepare(`SELECT id, first_prompt FROM sessions`);
  const selectTools = sqlite.prepare(`SELECT tool_name FROM tool_calls WHERE session_id = ?`);
  const updateSession = sqlite.prepare(`UPDATE sessions SET task_type = ?, request_category = ? WHERE id = ?`);

  const allSessions = selectSessions.all() as Array<{ id: string; first_prompt: string }>;
  let updatedCount = 0;

  sqlite.transaction(() => {
    for (const s of allSessions) {
      const tools = (selectTools.all(s.id) as Array<{ tool_name: string }>).map(t => t.tool_name);
      const classifiedType = classifyConversation(s.first_prompt, tools);
      const classifiedCategory = classifyRequestCategory(s.first_prompt);
      updateSession.run(classifiedType, classifiedCategory, s.id);
      updatedCount++;
    }
  })();

  return updatedCount;
}

