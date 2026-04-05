// ── Document ──────────────────────────────────────────────────────────────────

export interface Document {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  chunk_count: number;
  status: 'processing' | 'ready' | 'error';
  created_at: string;
}

export interface DocumentListResponse {
  documents: Document[];
  total: number;
}

// ── Chat ──────────────────────────────────────────────────────────────────────

export interface ChatRequest {
  question: string;
  session_id: string;
  document_ids?: string[];
}

export interface SourceChunk {
  document_id: string;
  filename: string;
  chunk_text: string;
  score: number;
}

// SSE event types streamed from backend
export type SseEvent =
  | { type: 'token'; data: string }
  | { type: 'sources'; data: SourceChunk[] }
  | { type: 'done' }
  | { type: 'error'; data: string };

// Assembled chat message for the UI
export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceChunk[];
  streaming?: boolean;   // true while tokens are still arriving
}
