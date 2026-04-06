import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Document, DocumentListResponse } from '../models/types';

@Injectable({ providedIn: 'root' })
export class DocumentService {
  private http = inject(HttpClient);
  private base = '/api/documents';

  upload(file: File): Observable<Document> {
    const form = new FormData();
    form.append('file', file);
    return this.http.post<Document>(`${this.base}/upload`, form);
  }

  list(): Observable<DocumentListResponse> {
    return this.http.get<DocumentListResponse>(this.base);
  }

  getById(id: string): Observable<Document> {
    return this.http.get<Document>(`${this.base}/${id}`);
  }

  delete(id: string): Observable<{ deleted: boolean }> {
    return this.http.delete<{ deleted: boolean }>(`${this.base}/${id}`);
  }
}
