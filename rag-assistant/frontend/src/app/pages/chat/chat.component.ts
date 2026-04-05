import { Component, inject, signal, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ChatService } from '../../services/chat.service';
import { ChatMessage, SourceChunk } from '../../models/types';

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="chat-page">
      <div class="chat-window" #scrollContainer>
        @if (messages().length === 0) {
          <div class="empty-state">
            <div class="empty-icon">💬</div>
            <p>Ask a question about your uploaded documents.</p>
          </div>
        }

        @for (msg of messages(); track $index) {
          <div class="message" [class]="'msg-' + msg.role">
            <div class="bubble">
              <span class="content">{{ msg.content }}</span>
              @if (msg.role === 'assistant' && msg.streaming) {
                <span class="cursor">▊</span>
              }
            </div>

            <!-- Source chips (shown after streaming completes) -->
            @if (msg.sources && msg.sources.length > 0 && !msg.streaming) {
              <div class="sources">
                <span class="sources-label">Sources:</span>
                @for (src of msg.sources; track src.document_id) {
                  <div class="source-chip" (click)="toggleSource(src)">
                    📄 {{ src.filename }}
                    <span class="score">{{ (src.score * 100).toFixed(0) }}%</span>
                  </div>
                }
              </div>
              @if (expandedSource()) {
                <div class="source-excerpt">
                  <strong>{{ expandedSource()!.filename }}</strong>
                  <p>{{ expandedSource()!.chunk_text }}</p>
                </div>
              }
            }
          </div>
        }
      </div>

      <!-- Input bar -->
      <div class="input-bar">
        <textarea
          [(ngModel)]="inputText"
          placeholder="Ask a question about your documents..."
          rows="1"
          (keydown.enter)="onEnter($event)"
          [disabled]="streaming()"
        ></textarea>
        <button (click)="sendMessage()" [disabled]="!inputText.trim() || streaming()">
          {{ streaming() ? '...' : 'Send' }}
        </button>
      </div>
    </div>
  `,
  styles: [`
    .chat-page { display: flex; flex-direction: column; height: calc(100vh - 100px); }
    .chat-window {
      flex: 1; overflow-y: auto; padding: 1rem;
      display: flex; flex-direction: column; gap: 1rem;
    }
    .empty-state { text-align: center; color: #94a3b8; margin: auto; }
    .empty-icon { font-size: 2.5rem; margin-bottom: 0.5rem; }
    .message { display: flex; flex-direction: column; max-width: 75%; }
    .msg-user { align-self: flex-end; align-items: flex-end; }
    .msg-assistant { align-self: flex-start; align-items: flex-start; }
    .bubble {
      padding: 0.75rem 1rem; border-radius: 12px;
      font-size: 0.95rem; line-height: 1.6; white-space: pre-wrap;
    }
    .msg-user .bubble    { background: #6366f1; color: #fff; border-bottom-right-radius: 4px; }
    .msg-assistant .bubble { background: #f1f5f9; color: #0f172a; border-bottom-left-radius: 4px; }
    .cursor { animation: blink 0.8s step-end infinite; }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
    .sources { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.5rem; align-items: center; }
    .sources-label { font-size: 0.75rem; color: #64748b; }
    .source-chip {
      font-size: 0.75rem; background: #e0e7ff; color: #3730a3;
      padding: 0.2rem 0.6rem; border-radius: 20px; cursor: pointer;
      display: flex; align-items: center; gap: 0.3rem; transition: background 0.2s;
    }
    .source-chip:hover { background: #c7d2fe; }
    .score { opacity: 0.7; }
    .source-excerpt {
      margin-top: 0.5rem; padding: 0.75rem; background: #f8fafc;
      border-left: 3px solid #6366f1; border-radius: 4px;
      font-size: 0.85rem; color: #334155; max-width: 500px;
    }
    .source-excerpt strong { display: block; margin-bottom: 0.25rem; }
    .input-bar {
      display: flex; gap: 0.5rem; padding: 1rem 0;
      border-top: 1px solid #e2e8f0;
    }
    textarea {
      flex: 1; padding: 0.75rem 1rem; border: 1px solid #cbd5e1;
      border-radius: 10px; font-size: 0.95rem; resize: none;
      font-family: inherit; outline: none;
    }
    textarea:focus { border-color: #6366f1; }
    button {
      padding: 0 1.5rem; background: #6366f1; color: #fff;
      border: none; border-radius: 10px; font-size: 0.95rem;
      cursor: pointer; transition: background 0.2s;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    button:hover:not(:disabled) { background: #4f46e5; }
  `],
})
export class ChatComponent implements AfterViewChecked {
  @ViewChild('scrollContainer') private scrollRef!: ElementRef;

  private chatService = inject(ChatService);

  messages = signal<ChatMessage[]>([]);
  inputText = '';
  streaming = signal(false);
  expandedSource = signal<SourceChunk | null>(null);

  // Each browser session gets a UUID as the conversation session_id
  private sessionId = crypto.randomUUID();

  ngAfterViewChecked() {
    this.scrollToBottom();
  }

  onEnter(e: KeyboardEvent) {
    if (!e.shiftKey) { e.preventDefault(); this.sendMessage(); }
  }

  sendMessage() {
    const text = this.inputText.trim();
    if (!text || this.streaming()) return;

    this.inputText = '';
    this.expandedSource.set(null);

    // Add user message
    this.messages.update((m) => [...m, { role: 'user', content: text }]);

    // Add empty assistant message that will fill with tokens
    const assistantIndex = this.messages().length;
    this.messages.update((m) => [...m, { role: 'assistant', content: '', streaming: true }]);
    this.streaming.set(true);

    this.chatService.ask({ question: text, session_id: this.sessionId }).subscribe({
      next: (event) => {
        if (event.type === 'token') {
          this.messages.update((msgs) => {
            const copy = [...msgs];
            copy[assistantIndex] = {
              ...copy[assistantIndex],
              content: copy[assistantIndex].content + event.data,
            };
            return copy;
          });
        } else if (event.type === 'sources') {
          this.messages.update((msgs) => {
            const copy = [...msgs];
            copy[assistantIndex] = { ...copy[assistantIndex], sources: event.data };
            return copy;
          });
        }
      },
      error: () => {
        this.streaming.set(false);
        this.messages.update((msgs) => {
          const copy = [...msgs];
          copy[assistantIndex] = { ...copy[assistantIndex], content: 'Error: could not get response.', streaming: false };
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

  toggleSource(src: SourceChunk) {
    this.expandedSource.set(this.expandedSource()?.document_id === src.document_id ? null : src);
  }

  private scrollToBottom() {
    try {
      const el = this.scrollRef?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    } catch {}
  }
}
