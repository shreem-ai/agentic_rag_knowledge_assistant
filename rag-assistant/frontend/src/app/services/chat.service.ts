import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { SseEvent, ChatRequest, SourceChunk } from '../models/types';

export interface HistoryMessage {
  role: 'user' | 'assistant';
  content: string;
  sources: SourceChunk[];
  created_at: string;
}

export interface HistoryResponse {
  session_id: string;
  messages: HistoryMessage[];
}

@Injectable({ providedIn: 'root' })
export class ChatService {
  private base = '/api/chat';

  /**
   * Send a question and return an Observable that emits SSE events
   * as the backend streams them. Uses fetch() with ReadableStream
   * because Angular's HttpClient buffers SSE.
   */
  ask(request: ChatRequest): Observable<SseEvent> {
    return new Observable((observer) => {
      const controller = new AbortController();

      fetch(this.base, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
        signal: controller.signal,
      })
        .then(async (res) => {
          if (!res.ok || !res.body) {
            observer.error(new Error(`HTTP ${res.status}`));
            return;
          }

          const reader  = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer    = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // SSE lines look like:  data: {...}\n\n
            const parts = buffer.split('\n\n');
            buffer = parts.pop() ?? '';

            for (const part of parts) {
              const line = part.trim();
              if (!line.startsWith('data:')) continue;
              const json = line.slice(5).trim();
              try {
                const event: SseEvent = JSON.parse(json);
                observer.next(event);
                if (event.type === 'done') {
                  observer.complete();
                  return;
                }
              } catch {
                // ignore malformed lines
              }
            }
          }
          observer.complete();
        })
        .catch((err) => {
          if (err.name !== 'AbortError') observer.error(err);
        });

      return () => controller.abort();
    });
  }

  async getHistory(sessionId: string): Promise<HistoryResponse> {
    try {
      const res = await fetch(`${this.base}/history/${sessionId}`);
      if (!res.ok) return { session_id: sessionId, messages: [] };
      return res.json();
    } catch {
      return { session_id: sessionId, messages: [] };
    }
  }
}
