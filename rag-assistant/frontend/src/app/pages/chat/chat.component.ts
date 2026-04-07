import {
  Component, inject, signal, ViewChild, ElementRef,
  AfterViewChecked, OnInit, SecurityContext
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
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
        <div class="sidebar-header">
          <h3>Documents</h3>
          <button class="btn-new-chat" (click)="newChat()" title="Start a new conversation">+ New</button>
        </div>
        <p class="sidebar-hint">Check documents to filter. Uncheck all to search everything.</p>
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
              <p class="empty-sub">Answers are grounded in your documents with source citations.</p>
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
                @if (msg.role === 'assistant') {
                  <div class="md-content" [innerHTML]="renderMarkdown(msg.content)"></div>
                } @else {
                  <span class="content">{{ msg.content }}</span>
                }
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
                        <span class="chip-chunk">·&nbsp;chunk&nbsp;{{ src.chunk_index + 1 }}</span>
                        <span class="chip-score">{{ (src.score * 100).toFixed(0) }}%</span>
                      </button>
                    }
                  </div>
                  @if (expandedSrc()) {
                    <div class="chunk-preview">
                      <div class="chunk-header">
                        <div class="chunk-meta">
                          <strong>{{ expandedSrc()!.filename }}</strong>
                          <span class="chunk-index-pill">Chunk #{{ expandedSrc()!.chunk_index + 1 }}</span>
                        </div>
                        <span class="chunk-score-pill">
                          Relevance: {{ (expandedSrc()!.score * 100).toFixed(0) }}%
                        </span>
                      </div>
                      <div class="chunk-text" [innerHTML]="highlightChunk(expandedSrc()!.chunk_text)"></div>
                    </div>
                  }
                </div>
              }

            </div>
          }

          <!-- Streaming indicator -->
          @if (streaming() && messages().length > 0 && !messages()[messages().length-1].content) {
            <div class="message msg-assistant">
              <div class="bubble typing-indicator">
                <span></span><span></span><span></span>
              </div>
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
    .chat-layout { display: flex; height: calc(100vh - 88px); gap: 1rem; }

    /* Sidebar */
    .sidebar { width: 220px; flex-shrink: 0; overflow-y: auto; padding: 0.5rem; display: flex; flex-direction: column; gap: 0.25rem; }
    .sidebar-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.25rem; }
    .sidebar-header h3 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; margin: 0; }
    .btn-new-chat { font-size: 0.72rem; padding: 0.2rem 0.5rem; border-radius: 6px; border: 1px solid #c7d2fe; background: #eef2ff; color: #4f46e5; cursor: pointer; white-space: nowrap; }
    .btn-new-chat:hover { background: #c7d2fe; }
    .sidebar-hint { font-size: 0.72rem; color: #94a3b8; line-height: 1.4; margin-bottom: 0.5rem; }
    .doc-toggle { display: flex; align-items: flex-start; gap: 0.5rem; padding: 0.45rem 0.5rem; border-radius: 8px; cursor: pointer; border: 1px solid transparent; transition: all 0.15s; }
    .doc-toggle:hover  { background: #f1f5f9; }
    .doc-toggle.selected { background: #eef2ff; border-color: #c7d2fe; }
    .doc-toggle input  { margin-top: 2px; accent-color: #6366f1; flex-shrink: 0; }
    .doc-label { display: flex; flex-direction: column; min-width: 0; }
    .doc-filename { font-size: 0.8rem; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 160px; }
    .doc-chunks   { font-size: 0.7rem; color: #94a3b8; }

    /* Chat panel */
    .chat-panel  { flex: 1; display: flex; flex-direction: column; min-width: 0; }
    .chat-window { flex: 1; overflow-y: auto; padding: 1rem; display: flex; flex-direction: column; gap: 1.25rem; }

    .empty-state     { text-align: center; color: #94a3b8; margin: auto; }
    .empty-icon      { font-size: 2.5rem; margin-bottom: 0.5rem; }
    .empty-sub       { font-size: 0.82rem; margin-top: 0.25rem; }

    .message       { display: flex; flex-direction: column; max-width: 80%; }
    .msg-user      { align-self: flex-end; align-items: flex-end; }
    .msg-assistant { align-self: flex-start; align-items: flex-start; }

    /* Thinking log */
    .thinking-log  { margin-bottom: 0.35rem; display: flex; flex-direction: column; gap: 0.2rem; }
    .thinking-step { font-size: 0.72rem; color: #6366f1; background: #eef2ff; padding: 0.15rem 0.5rem; border-radius: 4px; font-family: monospace; }

    /* Bubbles */
    .bubble { padding: 0.75rem 1rem; border-radius: 12px; font-size: 0.95rem; line-height: 1.65; }
    .msg-user .bubble      { background: #6366f1; color: #fff; border-bottom-right-radius: 4px; white-space: pre-wrap; }
    .msg-assistant .bubble { background: #f1f5f9; color: #0f172a; border-bottom-left-radius: 4px; }
    .cursor { animation: blink 0.8s step-end infinite; }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }

    /* Markdown rendering */
    .md-content { line-height: 1.7; }
    .md-content :global(p)      { margin: 0 0 0.6em; }
    .md-content :global(p:last-child) { margin-bottom: 0; }
    .md-content :global(strong) { font-weight: 600; }
    .md-content :global(em)     { font-style: italic; }
    .md-content :global(code)   { background: #e2e8f0; padding: 0.1em 0.35em; border-radius: 4px; font-family: monospace; font-size: 0.88em; }
    .md-content :global(pre)    { background: #1e293b; color: #e2e8f0; padding: 0.75rem 1rem; border-radius: 8px; overflow-x: auto; margin: 0.5em 0; }
    .md-content :global(pre code) { background: none; padding: 0; font-size: 0.85em; }
    .md-content :global(ul), .md-content :global(ol) { padding-left: 1.5em; margin: 0.4em 0; }
    .md-content :global(li)     { margin-bottom: 0.2em; }
    .md-content :global(h1), .md-content :global(h2), .md-content :global(h3) { font-weight: 600; margin: 0.5em 0 0.25em; }
    .md-content :global(blockquote) { border-left: 3px solid #6366f1; padding-left: 0.75rem; color: #475569; margin: 0.5em 0; }

    /* Typing indicator */
    .typing-indicator { display: flex; gap: 4px; align-items: center; padding: 0.75rem 1rem; }
    .typing-indicator span { width: 7px; height: 7px; border-radius: 50%; background: #94a3b8; animation: bounce 1.2s infinite; }
    .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
    .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes bounce { 0%,80%,100%{transform:scale(0.7);opacity:0.5} 40%{transform:scale(1);opacity:1} }

    /* Sources */
    .sources-section { margin-top: 0.5rem; max-width: 520px; }
    .sources-label   { font-size: 0.72rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; display: block; margin-bottom: 0.35rem; }
    .source-chips    { display: flex; flex-wrap: wrap; gap: 0.35rem; }
    .chip { font-size: 0.75rem; background: #e0e7ff; color: #3730a3; padding: 0.2rem 0.65rem; border-radius: 20px; cursor: pointer; border: 1px solid transparent; display: inline-flex; align-items: center; gap: 0.3rem; transition: all 0.15s; }
    .chip:hover  { background: #c7d2fe; }
    .chip.active { background: #6366f1; color: #fff; border-color: #4f46e5; }
    .chip-score  { font-variant-numeric: tabular-nums; }
    .chip-chunk  { opacity: 0.7; font-size: 0.7rem; }

    .chunk-preview { margin-top: 0.6rem; padding: 0.75rem 1rem; background: #f8fafc; border-left: 3px solid #6366f1; border-radius: 0 6px 6px 0; }
    .chunk-header  { display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.4rem; }
    .chunk-meta    { display: flex; align-items: center; gap: 0.5rem; }
    .chunk-meta strong   { font-size: 0.8rem; color: #1e293b; }
    .chunk-index-pill    { font-size: 0.68rem; background: #f1f5f9; color: #475569; padding: 0.1rem 0.45rem; border-radius: 20px; border: 1px solid #e2e8f0; }
    .chunk-score-pill    { font-size: 0.7rem; background: #e0e7ff; color: #3730a3; padding: 0.1rem 0.5rem; border-radius: 20px; }
    .chunk-text { font-size: 0.82rem; color: #334155; line-height: 1.65; white-space: pre-wrap; max-height: 200px; overflow-y: auto; }
    .chunk-text mark { background: #fef08a; color: #1e293b; border-radius: 2px; padding: 0 2px; }

    /* Input */
    .input-bar { display: flex; gap: 0.5rem; padding: 0.75rem 0 0; border-top: 1px solid #e2e8f0; }
    textarea { flex: 1; padding: 0.75rem 1rem; border: 1px solid #cbd5e1; border-radius: 10px; font-size: 0.95rem; resize: none; font-family: inherit; outline: none; transition: border-color 0.15s; }
    textarea:focus { border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }
    button { padding: 0 1.5rem; background: #6366f1; color: #fff; border: none; border-radius: 10px; font-size: 0.95rem; cursor: pointer; transition: background 0.2s; white-space: nowrap; min-width: 72px; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    button:hover:not(:disabled) { background: #4f46e5; }
    .muted { font-size: 0.8rem; color: #94a3b8; line-height: 1.5; }
  `],
})
export class ChatComponent implements OnInit, AfterViewChecked {
  @ViewChild('scrollContainer') private scrollRef!: ElementRef;

  private chatService  = inject(ChatService);
  private docService   = inject(DocumentService);
  private sanitizer    = inject(DomSanitizer);

  messages    = signal<ChatMessage[]>([]);
  readyDocs   = signal<Document[]>([]);
  selectedIds = signal<Set<string>>(new Set());
  streaming   = signal(false);
  expandedSrc = signal<SourceChunk | null>(null);
  expandedKey = signal<string>('');
  inputText   = '';
  lastQuery   = '';

  // Persist session across page refreshes
  private sessionId = this.getOrCreateSessionId();
  private shouldScroll = false;

  private getOrCreateSessionId(): string {
    const stored = localStorage.getItem('rag_session_id');
    if (stored) return stored;
    const id = crypto.randomUUID();
    localStorage.setItem('rag_session_id', id);
    return id;
  }

  async ngOnInit() {
    // Load documents list
    this.docService.list().subscribe((res) => {
      this.readyDocs.set(res.documents.filter((d) => d.status === 'ready'));
    });

    // Restore previous conversation from backend
    const history = await this.chatService.getHistory(this.sessionId);
    if (history.messages.length > 0) {
      this.messages.set(history.messages.map((m) => ({
        role: m.role,
        content: m.content,
        sources: m.sources || [],
      })));
      this.shouldScroll = true;
    }
  }

  ngAfterViewChecked() {
    if (this.shouldScroll) {
      this.scrollToBottom();
      this.shouldScroll = false;
    }
  }

  newChat() {
    const id = crypto.randomUUID();
    localStorage.setItem('rag_session_id', id);
    this.sessionId = id;
    this.messages.set([]);
    this.expandedKey.set('');
    this.expandedSrc.set(null);
  }

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

    this.inputText  = '';
    this.lastQuery  = text;
    this.expandedKey.set(''); this.expandedSrc.set(null);

    this.messages.update((m) => [...m, { role: 'user', content: text }]);

    const assistantIndex = this.messages().length;
    this.messages.update((m) => [...m, {
      role: 'assistant', content: '', streaming: true, thinkingSteps: []
    }]);
    this.streaming.set(true);
    this.shouldScroll = true;

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
            this.shouldScroll = true;
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
        this.shouldScroll = true;
      },
    });
  }

  highlightChunk(chunkText: string): SafeHtml {
    if (!chunkText) return this.sanitizer.bypassSecurityTrustHtml('');

    // Escape HTML first
    let escaped = chunkText
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Extract meaningful query words (3+ chars, skip stop words)
    const stopWords = new Set(['the','and','for','are','but','not','you','all','can','her','was','one','our','out','had','has','have','with','that','this','from','they','will','been','were','what','when','which','who','how','its']);
    const queryWords = this.lastQuery
      .toLowerCase()
      .replace(/[^\w\s]/g, '')
      .split(/\s+/)
      .filter(w => w.length >= 3 && !stopWords.has(w));

    if (queryWords.length > 0) {
      const pattern = queryWords
        .map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
        .join('|');
      escaped = escaped.replace(
        new RegExp(`(${pattern})`, 'gi'),
        '<mark>$1</mark>',
      );
    }

    return this.sanitizer.bypassSecurityTrustHtml(escaped);
  }

  renderMarkdown(text: string): SafeHtml {
    if (!text) return this.sanitizer.bypassSecurityTrustHtml('');

    // 1. Escape HTML to prevent XSS
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // 2. Code blocks (must come before inline code)
    html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, _lang, code) =>
      `<pre><code>${code.trim()}</code></pre>`
    );

    // 3. Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // 4. Bold and italic
    html = html.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');

    // 5. Headings
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // 6. Blockquotes
    html = html.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');

    // 7. Unordered lists (group consecutive items)
    html = html.replace(/^[-*]\s+(.+)$/gm, '<li>$1</li>');
    html = html.replace(/((?:<li>.+<\/li>\n?)+)/g, '<ul>$1</ul>');

    // 8. Paragraphs: split by double newline
    const blocks = html.split(/\n\n+/);
    html = blocks.map(block => {
      const trimmed = block.trim();
      if (!trimmed) return '';
      if (/^<(pre|ul|ol|h[1-3]|blockquote)/.test(trimmed)) return trimmed;
      // Replace single newlines within a paragraph with <br>
      return '<p>' + trimmed.replace(/\n/g, '<br>') + '</p>';
    }).join('');

    return this.sanitizer.bypassSecurityTrustHtml(html);
  }

  private scrollToBottom() {
    try {
      const el = this.scrollRef?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    } catch {}
  }
}
