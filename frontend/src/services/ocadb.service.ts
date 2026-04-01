import { Injectable, signal, computed, inject } from '@angular/core';
import { environment } from '../environments/environment';
import { ApiLogService } from './api-log.service';

export interface FitsHeader {
  OBJECT?: string | null;
  TELESCOP?: string | null;
  INSTRUME?: string | null;
  FILTER?: string | null;
  EXPTIME?: number | null;
  'DATE-OBS'?: string | null;
  IMAGETYP?: string | null;
  OBSTYPE?: string | null;
  AIRMASS?: number | null;
  RA?: number | null;
  DEC?: number | null;
  JD?: number | null;
  OBSERVER?: string | null;
  'OBS-PROG'?: string | null;
  NAXIS1?: number | null;
  NAXIS2?: number | null;
  [key: string]: any;
}

export interface Observation {
  _id: string | null;
  obs_name: string;
  file_name?: string | null;
  object_id?: string | null;
  files: any[];
  fits_header: FitsHeader;
  metadata: Record<string, any>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface SearchFilters {
  telescop?: string | null;
  date_obs_from?: string | null;
  date_obs_to?: string | null;
  imagetyp?: string | null;
  obstype?: string | null;
  object?: string | null;
  filter?: string[] | null;
  exptime_from?: string | null;
  exptime_to?: string | null;
  pi?: string | null;
  sciprog?: string | null;
  cone_search?: {
    ra: number;
    dec: number;
    arc_seconds: number;
    epoch?: string;
  } | null;
}

export interface PaginationState {
  page: number;
  pageSize: number;
  total: number;
}

@Injectable({
  providedIn: 'root'
})
export class OcadbService {
  private readonly baseUrl = environment.apiBaseUrl;
  private readonly apiLog = inject(ApiLogService);

  loading = signal(false);
  error = signal<string | null>(null);

  token = signal<string | null>(null);
  lastRequestInfo = signal('System initialized');
  isAuthenticated = computed(() => !!this.token());

  pagination = signal<PaginationState>({ page: 1, pageSize: 50, total: 0 });

  constructor() {
    const savedToken = localStorage.getItem('ocadb_token');
    if (savedToken) {
      this.token.set(savedToken);
      this.lastRequestInfo.set('Session restored from local storage');
    }
  }

  clearError() {
    this.error.set(null);
  }

  async login(username: string, password: string): Promise<boolean> {
    this.loading.set(true);
    this.error.set(null);
    this.lastRequestInfo.set(`Authenticating as ${username}...`);

    if (!navigator.onLine) {
      this.error.set('No Internet connection. Please check your network settings.');
      this.loading.set(false);
      return false;
    }

    try {
      const params = new URLSearchParams();
      params.append('grant_type', 'password');
      params.append('username', username);
      params.append('password', password);

      const response = await this.loggedFetch(`${this.baseUrl}/auth/token/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: params.toString()
      });

      if (!response.ok) {
        if (response.status === 401) throw new Error('Incorrect username or password.');
        if (response.status === 403) throw new Error('Access denied. Account may be inactive.');
        if (response.status >= 500) throw new Error(`API server error (${response.status}). The backend may be starting up or misconfigured.`);
        throw new Error(await this.extractErrorMessage(response, `Login failed (${response.status})`));
      }

      const data = await response.json();
      if (!data.access_token) throw new Error('Invalid server response: no access token.');

      this.token.set(data.access_token);
      localStorage.setItem('ocadb_token', data.access_token);
      this.lastRequestInfo.set('Login successful.');
      this.loading.set(false);
      return true;
    } catch (e: any) {
      this.handleFetchError(e, 'Login');
      return false;
    }
  }

  logout() {
    this.token.set(null);
    localStorage.removeItem('ocadb_token');
    this.error.set(null);
    this.lastRequestInfo.set('User logged out');
  }

  async searchObservations(filters: SearchFilters): Promise<Observation[]> {
    if (!this.token()) {
      this.error.set('You must be logged in to search.');
      return [];
    }

    if (!navigator.onLine) {
      this.error.set('No Internet connection.');
      return [];
    }

    this.loading.set(true);
    this.error.set(null);

    try {
      const pag = this.pagination();
      const body: Record<string, any> = {};

      if (filters.telescop) body.telescop = filters.telescop;
      if (filters.date_obs_from) body.date_obs_from = filters.date_obs_from;
      if (filters.date_obs_to) body.date_obs_to = filters.date_obs_to;
      if (filters.imagetyp) body.imagetyp = filters.imagetyp;
      if (filters.obstype) body.obstype = filters.obstype;
      if (filters.object) body.object = filters.object;
      if (filters.filter && filters.filter.length > 0) body.filter = filters.filter;
      if (filters.exptime_from) body.exptime_from = filters.exptime_from;
      if (filters.exptime_to) body.exptime_to = filters.exptime_to;
      if (filters.pi) body.pi = filters.pi;
      if (filters.sciprog) body.sciprog = filters.sciprog;
      if (filters.cone_search) body.cone_search = filters.cone_search;

      const url = `${this.baseUrl}/observations/search`;
      this.lastRequestInfo.set(`POST /observations/search ${JSON.stringify(body)}`);

      const response = await this.loggedFetch(url, {
        method: 'POST',
        headers: this.authHeaders(),
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          this.logout();
          throw new Error('Session expired. Please login again.');
        }
        if (response.status === 404) {
          this.lastRequestInfo.set('No results found');
          this.loading.set(false);
          this.pagination.update(p => ({ ...p, total: 0 }));
          return [];
        }
        if (response.status === 422) {
          const err = await response.json();
          throw new Error(`Invalid search: ${JSON.stringify(err.detail)}`);
        }
        if (response.status >= 500) {
          throw new Error(`API server error (${response.status}). The backend may be starting up or misconfigured.`);
        }
        throw new Error(`API Error: ${response.status} ${response.statusText}`);
      }

      const data: Observation[] = await response.json();
      this.pagination.update(p => ({ ...p, total: data.length }));
      this.lastRequestInfo.set(`Loaded ${data.length} observations`);
      this.loading.set(false);
      return data;
    } catch (e: any) {
      this.handleFetchError(e, 'Search');
      return [];
    }
  }

  async fetchValuesList(field: 'telescop' | 'imagetyp' | 'obstype' | 'pi' | 'object'): Promise<string[]> {
    if (!this.token()) return [];

    try {
      const response = await this.loggedFetch(`${this.baseUrl}/observations/values/${field}`, {
        headers: this.authHeaders()
      });
      if (!response.ok) return [];
      return await response.json();
    } catch {
      return [];
    }
  }

  async fetchTelescopeFilters(telescope: string): Promise<string[]> {
    if (!this.token() || !telescope) return [];

    try {
      const response = await this.loggedFetch(`${this.baseUrl}/observations/values/${telescope}/filter`, {
        headers: this.authHeaders()
      });
      if (!response.ok) return [];
      return await response.json();
    } catch {
      return [];
    }
  }

  private authHeaders(): HeadersInit {
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${this.token()}`
    };
  }

  private async loggedFetch(url: string, init?: RequestInit): Promise<Response> {
    const reqHeaders: Record<string, string> = {};
    if (init?.headers) {
      const h = init.headers;
      if (h instanceof Headers) {
        h.forEach((v, k) => reqHeaders[k] = v);
      } else if (Array.isArray(h)) {
        h.forEach(([k, v]) => reqHeaders[k] = v);
      } else {
        Object.entries(h).forEach(([k, v]) => reqHeaders[k] = v);
      }
    }
    const entry = this.apiLog.createEntry(init?.method ?? 'GET', url, reqHeaders, init?.body);
    try {
      const response = await fetch(url, init);
      const resHeaders: Record<string, string> = {};
      response.headers.forEach((v, k) => resHeaders[k] = v);
      const clone = response.clone();
      try {
        const text = await clone.text();
        this.apiLog.completeEntry(entry, response.status, resHeaders, text);
      } catch {
        this.apiLog.completeEntry(entry, response.status, resHeaders);
      }
      return response;
    } catch (e: any) {
      this.apiLog.failEntry(entry, e.message ?? 'Network error');
      throw e;
    }
  }

  private async extractErrorMessage(response: Response, fallback: string): Promise<string> {
    try {
      const errData = await response.json();
      if (errData.detail) {
        return Array.isArray(errData.detail)
          ? errData.detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ')
          : errData.detail;
      }
    } catch { /* ignore parse errors */ }
    return fallback;
  }

  private handleFetchError(e: any, context: string) {
    let msg = e.message;
    if (msg === 'Failed to fetch' || msg?.includes('NetworkError') || msg?.includes('ECONNREFUSED')) {
      msg = `Cannot reach the API server at ${this.baseUrl}. Is the backend running?`;
    }
    this.error.set(msg);
    this.lastRequestInfo.set(`${context} error: ${msg}`);
    this.loading.set(false);
  }
}
