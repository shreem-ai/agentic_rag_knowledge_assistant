import {
  Component, inject, signal, ViewChild, ElementRef,
  AfterViewChecked, OnInit
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatService } from '../../services/chat.service';
import { DocumentService } from '../../services/document.service';
import { ChatMessage, SourceChunk, Document } from '../../models/types';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="chat-layout">

      <!-- Sidebar -->
      <aside class="sidebar">
        <h3>Documents</h3>
        <p class="sidebar-hint">Uncheck all to search everything.</p>
        @for (doc of readyDocs(); track doc.id) {
          <label class="doc-toggle" [class.selected]="selectedIds().has(doc.id)">
            <input type="checkbox" [checked]="selectedIds().has(doc.id)"
                   (change)="toggleDoc(doc.id)" />
            <span class="doc-label">
              <span class="doc-filename">{{ doc.filename }}</span>
              <span class="doc-chunks">{{ doc.chunk_count }} chunks</span>
            </span>
          </label>
        }
        @if (readyDocs().length === 0) {
          <p class="muted">No ready documents.<br>Upload some first.</p>
        }
      </aside>

      <!-- Main chat panel -->
      <div class="chat-panel">
        <div class="chat-window" #scrollContainer>

          @if (messages().length === 0) {
            <div class="empty-state">
              <div class="empty-icon">💬</div>
              <p>Ask a question about your uploaded documents.</p>
            </div>
          }

          @for (msg of messages(); track $index) {
            <div class="message" [class]="'msg-' + msg.role">

              <!-- Thinking steps (agent tool calls) -->
              @if (msg.thinkingSteps?.length) {
                <div class="thinking-log">
                  @for (step of msg.thinkingSteps!; track $index) {
                    <div class="thinking-step">⚙ {{ step }}</div>
                  }
                </div>
              }

              <!-- Answer bubble -->
              <div class="bubble">
                <span class="content">{{ msg.content }}</span>
                @if (msg.role === 'assistant' && msg.streaming) {
                  <span class="cursor">▊</span>
                }
              </div>

              <!-- Sources -->
              @if (msg.role === 'assistant' && msg.sources?.length && !msg.streaming) {
                <div class="sources-section">
                  <span class="sources-label">Sources used:</span>
                  <div class="source-chips">
                    @for (src of msg.sources; track src.document_id + src.chunk_text.slice(0,20)) {
                      <button class="chip"
                              [class.active]="expandedKey() === chipKey(src)"
                              (click)="toggleChip(src)">
                        📄 {{ src.filename }}
                        <span class="chip-score">{{ (src.score * 100).toFixed(0) }}%</span>
                      </button>
                    }
                  </div>
                  @if (expandedSrc()) {
                    <div class="chunk-preview">
                      <div class="chunk-header">
                        <strong>{{ expandedSrc()!.filename }}</strong>
                        <span class="chunk-score-pill">
                          Relevance: {{ (expandedSrc()!.score * 100).toFixed(0) }}%
                        </span>
                      </div>
                      <div class="chunk-text">{{ expandedSrc()!.chunk_text }}</div>
                    </div>
                  }
                </div>
              }

            </div>
          }
        </div>

        <!-- Input bar -->
        <div class="input-bar">
          <textarea
            [(ngModel)]="inputText"
            placeholder="Ask a question about your documents…"
            rows="1"
            (keydown.enter)="onEnter($event)"
            [disabled]="streaming()"
          ></textarea>
          <button (click)="sendMessage()" [disabled]="!inputText.trim() || streaming()">
            {{ streaming() ? '…' : 'Send' }}
          </button>
        </div>
      </div>

    </div>
  `,
  styles: [`
    .chat-layout { display: flex; height: calc(100vh - 90px); gap: 1rem; }

    .sidebar { width: 220px; flex-shrink: 0; overflow-y: auto; padding: 0.5rem; }
    .sidebar h3 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin-bottom: 0.5rem; }
    .sidebar-hint { font-size: 0.75rem; color: #94a3b8; margin-bottom: 0.75rem; line-height: 1.4; }
    .doc-toggle { display: flex; align-items: flex-start; gap: 0.5rem; padding: 0.5rem; border-radius: 8px; cursor: pointer; margin-bottom: 0.25rem; border: 1px solid transparent; transition: all 0.15s; }
    .doc-toggle:hover  { background: #f1f5f9; }
    .doc-toggle.selected { background: #eef2ff; border-color: #c7d2fe; }
    .doc-toggle input  { margin-top: 2px; accent-color: #6366f1; flex-shrink: 0; }
    .doc-label { display: flex; flex-direction: column; min-width: 0; }
    .doc-filename { font-size: 0.8rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .doc-chunks   { font-size: 0.7rem; color: #94a3b8; }

    .chat-panel  { flex: 1; display: flex; flex-direction: column; min-width: 0; }
    .chat-window { flex: 1; overflow-y: auto; padding: 1rem; display: flex; flex-direction: column; gap: 1.25rem; }

    .empty-state { text-align: center; color: #94a3b8; margin: auto; }
    .empty-icon  { font-size: 2.5rem; margin-bottom: 0.5rem; }

    .message       { display: flex; flex-direction: column; max-width: 78%; }
    .msg-user      { align-self: flex-end; align-items: flex-end; }
    .msg-assistant { align-self: flex-start; align-items: flex-start; }

    /* Thinking log */
    .thinking-log  { margin-bottom: 0.35rem; display: flex; flex-direction: column; gap: 0.2rem; }
    .thinking-step { font-size: 0.72rem; color: #6366f1; background: #eef2ff; padding: 0.15rem 0.5rem; border-radius: 4px; font-family: monospace; }

    .bubble { padding: 0.75rem 1rem; border-radius: 12px; font-size: 0.95rem; line-height: 1.65; white-space: pre-wrap; }
    .msg-user .bubble      { background: #6366f1; color: #fff; border-bottom-right-radius: 4px; }
    .msg-assistant .bubble { background: #f1f5f9; color: #0f172a; border-bottom-left-radius: 4px; }
    .cursor { animation: blink 0.8s step-end infinite; }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

    .sources-section { margin-top: 0.5rem; max-width: 520px; }
    .sources-label   { font-size: 0.73rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; display: block; margin-bottom: 0.35rem; }
    .source-chips    { display: flex; flex-wrap: wrap; gap: 0.35rem; }
    .chip { font-size: 0.75rem; background: #e0e7ff; color: #3730a3; padding: 0.2rem 0.65rem; border-radius: 20px; cursor: pointer; border: 1px solid transparent; display: inline-flex; align-items: center; gap: 0.3rem; transition: all 0.15s; }
    .chip:hover  { background: #c7d2fe; }
    .chip.active { background: #6366f1; color: #fff; border-color: #4f46e5; }
    .chip-score  { font-variant-numeric: tabular-nums; }

    .chunk-preview { margin-top: 0.6rem; padding: 0.75rem 1rem; background: #f8fafc; border-left: 3px solid #6366f1; border-radius: 0 6px 6px 0; }
    .chunk-header  { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.4rem; }
    .chunk-header strong { font-size: 0.8rem; color: #1e293b; }
    .chunk-score-pill    { font-size: 0.7rem; background: #e0e7ff; color: #3730a3; padding: 0.1rem 0.5rem; border-radius: 20px; }
    .chunk-text { font-size: 0.82rem; color: #475569; line-height: 1.6; white-space: pre-wrap; max-height: 200px; overflow-y: auto; }

    .input-bar { display: flex; gap: 0.5rem; padding: 0.75rem 0 0; border-top: 1px solid #e2e8f0; }
    textarea { flex: 1; padding: 0.75rem 1rem; border: 1px solid #cbd5e1; border-radius: 10px; font-size: 0.95rem; resize: none; font-family: inherit; outline: none; }
    textarea:focus { border-color: #6366f1; }
    button { padding: 0 1.5rem; background: #6366f1; color: #fff; border: none; border-radius: 10px; font-size: 0.95rem; cursor: pointer; transition: background 0.2s; white-space: nowrap; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    button:hover:not(:disabled) { background: #4f46e5; }
    .muted { font-size: 0.8rem; color: #94a3b8; line-height: 1.5; }
  `],
})
export class ChatComponent implements OnInit, AfterViewChecked {
  @ViewChild('scrollContainer') private scrollRef!: ElementRef;

  private chatService = inject(ChatService);
  private docService  = inject(DocumentService);

  messages    = signal<ChatMessage[]>([]);
  readyDocs   = signal<Document[]>([]);
  selectedIds = signal<Set<string>>(new Set());
  streaming   = signal(false);
  expandedSrc = signal<SourceChunk | null>(null);
  expandedKey = signal<string>('');
  inputText   = '';

  private sessionId = crypto.randomUUID();

  ngOnInit() {
    this.docService.list().subscribe((res) => {
      this.readyDocs.set(res.documents.filter((d) => d.status === 'ready'));
    });
  }

  ngAfterViewChecked() { this.scrollToBottom(); }

  toggleDoc(id: string) {
    this.selectedIds.update((set) => {
      const next = new Set(set);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  chipKey(src: SourceChunk): string {
    return src.document_id + src.chunk_text.slice(0, 30);
  }

  toggleChip(src: SourceChunk) {
    const key = this.chipKey(src);
    if (this.expandedKey() === key) {
      this.expandedKey.set(''); this.expandedSrc.set(null);
    } else {
      this.expandedKey.set(key); this.expandedSrc.set(src);
    }
  }

  onEnter(e: Event) {
    const ke = e as KeyboardEvent;
    if (!ke.shiftKey) { ke.preventDefault(); this.sendMessage(); }
  }

  sendMessage() {
    const text = this.inputText.trim();
    if (!text || this.streaming()) return;

    this.inputText = '';
    this.expandedKey.set(''); this.expandedSrc.set(null);

    this.messages.update((m) => [...m, { role: 'user', content: text }]);

    const assistantIndex = this.messages().length;
    this.messages.update((m) => [...m, {
      role: 'assistant', content: '', streaming: true, thinkingSteps: []
    }]);
    this.streaming.set(true);

    const docIds = this.selectedIds().size > 0
      ? Array.from(this.selectedIds()) : undefined;

    this.chatService.ask({
      question: text, session_id: this.sessionId, document_ids: docIds,
    }).subscribe({
      next: (event) => {
        this.messages.update((msgs) => {
          const copy = [...msgs];
          const msg  = { ...copy[assistantIndex] };

          if (event.type === 'thinking') {
            msg.thinkingSteps = [...(msg.thinkingSteps ?? []), event.data];
          } else if (event.type === 'token') {
            msg.content += event.data;
          } else if (event.type === 'sources') {
            msg.sources = event.data;
          } else if (event.type === 'error') {
            msg.content = `Error: ${(event as any).data}`;
            msg.streaming = false;
          }

          copy[assistantIndex] = msg;
          return copy;
        });
      },
      error: () => {
        this.streaming.set(false);
        this.messages.update((msgs) => {
          const copy = [...msgs];
          copy[assistantIndex] = {
            ...copy[assistantIndex],
            content: 'Connection error — please try again.',
            streaming: false,
          };
          return copy;
        });
      },
      complete: () => {
        this.streaming.set(false);
        this.messages.update((msgs) => {
          const copy = [...msgs];
          copy[assistantIndex] = { ...copy[assistantIndex], streaming: false };
          return copy;
        });
      },
    });
  }

  private scrollToBottom() {
    try {
      const el = this.scrollRef?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    } catch {}
  }
}
