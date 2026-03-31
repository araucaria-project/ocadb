import { Injectable, signal } from '@angular/core';

export interface ApiLogEntry {
  id: number;
  timestamp: Date;
  method: string;
  url: string;
  requestBody: string | null;
  requestHeaders: Record<string, string>;
  status: number | null;
  responseBody: string | null;
  responseHeaders: Record<string, string>;
  durationMs: number | null;
  error: string | null;
}

const MAX_ENTRIES = 100;
const TRUNCATE_BODY = 8000;

@Injectable({ providedIn: 'root' })
export class ApiLogService {
  private seq = 0;

  entries = signal<ApiLogEntry[]>([]);

  createEntry(method: string, url: string, requestHeaders: Record<string, string>, body?: any): ApiLogEntry {
    const entry: ApiLogEntry = {
      id: ++this.seq,
      timestamp: new Date(),
      method: method.toUpperCase(),
      url,
      requestBody: body != null ? this.truncate(this.prettify(typeof body === 'string' ? body : JSON.stringify(body))) : null,
      requestHeaders,
      status: null,
      responseBody: null,
      responseHeaders: {},
      durationMs: null,
      error: null,
    };
    this.push(entry);
    return entry;
  }

  completeEntry(entry: ApiLogEntry, status: number, responseHeaders: Record<string, string>, responseBody?: string) {
    entry.status = status;
    entry.responseHeaders = responseHeaders;
    entry.responseBody = responseBody != null ? this.truncate(this.prettify(responseBody)) : null;
    entry.durationMs = Date.now() - entry.timestamp.getTime();
    this.entries.update(list => [...list]);
  }

  failEntry(entry: ApiLogEntry, error: string) {
    entry.error = error;
    entry.durationMs = Date.now() - entry.timestamp.getTime();
    this.entries.update(list => [...list]);
  }

  clear() {
    this.entries.set([]);
  }

  private push(entry: ApiLogEntry) {
    this.entries.update(list => {
      const next = [...list, entry];
      return next.length > MAX_ENTRIES ? next.slice(next.length - MAX_ENTRIES) : next;
    });
  }

  private prettify(text: string): string {
    try {
      const parsed = JSON.parse(text);
      return JSON.stringify(parsed, null, 2);
    } catch {
      return text;
    }
  }

  private truncate(text: string): string {
    if (text.length <= TRUNCATE_BODY) return text;
    const cut = text.substring(0, TRUNCATE_BODY);
    const lastNewline = cut.lastIndexOf('\n');
    return (lastNewline > TRUNCATE_BODY * 0.8 ? cut.substring(0, lastNewline) : cut) + '\n... (truncated)';
  }
}
