import { NextResponse } from 'next/server';
import { runIndexer } from '@/lib/indexer';
import { runSessionLogsIngester } from '@/lib/session_logs_ingester';
import { classifyAllIndexedSessions } from '@/lib/task_classifier';

export async function POST() {
  try {
    const indexerResult = runIndexer({ force: false });
    const classifierResult = classifyAllIndexedSessions();
    const ingesterResult = runSessionLogsIngester();

    return NextResponse.json({
      success: true,
      conversationsIndexed: indexerResult.conversationsIndexed,
      toolCallsIndexed: indexerResult.toolCallsIndexed,
      classifiedSessions: classifierResult,
      logsLinked: ingesterResult.linkedLogs,
      syncedAt: new Date().toISOString(),
    });
  } catch (error: any) {
    return NextResponse.json(
      { success: false, error: error?.message || 'Sync failed' },
      { status: 500 }
    );
  }
}
