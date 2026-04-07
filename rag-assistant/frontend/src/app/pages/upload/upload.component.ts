import { Component, inject, OnInit, OnDestroy, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { interval, Subscription, switchMap, takeWhile } from 'rxjs';
import { DocumentService } from '../../services/document.service';
import { Document } from '../../models/types';

@Component({
  selector: 'app-upload',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <div class="upload-page">
      <h1>Upload Documents</h1>
      <p class="subtitle">Supported formats: PDF, TXT, Markdown</p>

      <div
        class="drop-zone"
        [class.drag-over]="isDragging()"
        (dragover)="onDragOver($event)"
        (dragleave)="isDragging.set(false)"
        (drop)="onDrop($event)"
        (click)="fileInput.click()"
      >
        <div class="dz-icon">📄</div>
        <p>Drag & drop files here, or <strong>click to browse</strong></p>
        <input #fileInput type="file" accept=".pdf,.txt,.md" multiple hidden (change)="onFileSelected($event)" />
      </div>

      @if (uploading()) { <div class="status-bar uploading">Uploading and processing…</div> }
      @if (uploadError()) { <div class="status-bar error">{{ uploadError() }}</div> }
      @if (uploadSuccess()) { <div class="status-bar success">Upload complete! Document is being indexed.</div> }

      <div class="doc-list">
        <div class="list-header">
          <h2>Your Documents ({{ documents().length }})</h2>
          <a routerLink="/chat" class="btn-chat">Go to Chat →</a>
        </div>

        @if (loading()) {
          <p class="muted">Loading documents…</p>
        } @else if (documents().length === 0) {
          <p class="muted">No documents uploaded yet. Drop a file above to get started.</p>
        } @else {
          @for (doc of documents(); track doc.id) {
            <div class="doc-item">
              <div class="doc-info">
                <span class="doc-name">{{ doc.filename }}</span>
                <span class="doc-meta">
                  {{ formatSize(doc.file_size) }} · {{ doc.file_type.toUpperCase() }}
                  @if (doc.status === 'ready') { · {{ doc.chunk_count }} chunks indexed }
                </span>
              </div>
              <div class="doc-right">
                <span class="badge" [class]="'badge-' + doc.status">{{ doc.status }}</span>
                <button class="btn-delete" (click)="deleteDoc(doc.id)" title="Remove">✕</button>
              </div>
            </div>
            @if (doc.status === 'error') {
              <div class="error-detail">Processing failed — file may be corrupted or empty.</div>
            }
          }
        }
      </div>
    </div>
  `,
  styles: [`
    .upload-page { max-width: 720px; margin: 0 auto; }
    h1 { font-size: 1.6rem; margin-bottom: 0.25rem; }
    .subtitle { color: #64748b; margin-bottom: 1.5rem; }
    .drop-zone { border: 2px dashed #cbd5e1; border-radius: 12px; padding: 3rem 2rem; text-align: center; cursor: pointer; transition: all 0.2s; background: #f8fafc; }
    .drop-zone:hover, .drop-zone.drag-over { border-color: #6366f1; background: #eef2ff; }
    .dz-icon { font-size: 2.5rem; margin-bottom: 0.75rem; }
    .status-bar { margin-top: 1rem; padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.9rem; }
    .uploading { background: #eff6ff; color: #1d4ed8; }
    .error     { background: #fef2f2; color: #dc2626; }
    .success   { background: #f0fdf4; color: #16a34a; }
    .doc-list { margin-top: 2rem; }
    .list-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1rem; }
    .list-header h2 { margin: 0; }
    .btn-chat { background: #6366f1; color: #fff; padding: 0.5rem 1.25rem; border-radius: 8px; text-decoration: none; font-size: 0.9rem; }
    .doc-item { display: flex; align-items: center; justify-content: space-between; padding: 0.85rem 1rem; border: 1px solid #e2e8f0; border-radius: 8px; margin-bottom: 0.5rem; background: #fff; }
    .doc-name  { font-weight: 500; display: block; }
    .doc-meta  { font-size: 0.8rem; color: #64748b; }
    .doc-right { display: flex; align-items: center; gap: 0.5rem; }
    .badge { font-size: 0.75rem; padding: 0.25rem 0.65rem; border-radius: 20px; white-space: nowrap; }
    .badge-ready      { background: #dcfce7; color: #15803d; }
    .badge-processing { background: #fef9c3; color: #92400e; }
    .badge-error      { background: #fee2e2; color: #dc2626; }
    .btn-delete { background: none; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.2rem 0.5rem; cursor: pointer; color: #94a3b8; font-size: 0.8rem; transition: all 0.15s; }
    .btn-delete:hover { background: #fef2f2; border-color: #fca5a5; color: #dc2626; }
    .error-detail { font-size: 0.8rem; color: #dc2626; padding: 0.25rem 1rem 0.5rem; }
    .muted { color: #94a3b8; }
  `],
})
export class UploadComponent implements OnInit, OnDestroy {
  private docService = inject(DocumentService);
  private pollSub?: Subscription;

  documents     = signal<Document[]>([]);
  loading       = signal(false);
  uploading     = signal(false);
  uploadError   = signal('');
  uploadSuccess = signal(false);
  isDragging    = signal(false);

  ngOnInit() {
    this.loadDocuments();
    // Poll while any document is still processing; stop automatically when all are done
    this.pollSub = interval(2500).pipe(
      switchMap(() => this.docService.list()),
      takeWhile((res) => res.documents.some((d) => d.status === 'processing'), true),
    ).subscribe((res) => this.documents.set(res.documents));
  }

  ngOnDestroy() { this.pollSub?.unsubscribe(); }

  loadDocuments() {
    this.loading.set(true);
    this.docService.list().subscribe({
      next: (res) => { this.documents.set(res.documents); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    if (input.files) this.uploadFiles(Array.from(input.files));
    input.value = '';
  }

  onDragOver(e: DragEvent) { e.preventDefault(); this.isDragging.set(true); }
  onDrop(e: DragEvent) {
    e.preventDefault(); this.isDragging.set(false);
    if (e.dataTransfer?.files) this.uploadFiles(Array.from(e.dataTransfer.files));
  }

  uploadFiles(files: File[]) {
    this.uploadError.set(''); this.uploadSuccess.set(false); this.uploading.set(true);
    let pending = files.length;
    files.forEach((file) => {
      this.docService.upload(file).subscribe({
        next: (doc) => {
          this.documents.update((prev) => [doc, ...prev.filter(d => d.id !== doc.id)]);
          if (--pending === 0) { this.uploading.set(false); this.uploadSuccess.set(true); }
        },
        error: (err) => {
          this.uploadError.set(err.error?.detail || 'Upload failed.');
          this.uploading.set(false);
        },
      });
    });
  }

  deleteDoc(id: string) {
    this.docService.delete(id).subscribe({
      next: () => this.documents.update((docs) => docs.filter((d) => d.id !== id)),
      error: () => alert('Delete failed.'),
    });
  }

  formatSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }
}
