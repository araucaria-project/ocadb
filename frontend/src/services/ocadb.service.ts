import { Injectable, signal, computed, inject } from '@angular/core';
import { environment } from '../environments/environment';
import { ApiLogService } from './api-log.service';

export type FileClassification = 'raw' | 'zdf' | 'master' | 'source' | 'tmp' | 'test';
export type StorageStatusType = 'not_stored' | 'deleted' | 'stored' | 'corrupted' | 'requested' | 'scheduled' | 'queued' | 'storing';

export interface StorageLocationStatus {
  ready: boolean;
  check_needed: boolean;
  status: StorageStatusType;
  expected_time?: string | null;
}

export interface StorageStatus {
  observatory: StorageLocationStatus;
  hub: StorageLocationStatus;
  cloud: StorageLocationStatus;
}

export interface FitsFile {
  _id?: string | null;
  filename: string;
  file_class: FileClassification;
  path?: string | null;
  filesize?: number | null;
  mtime?: string | null;
  digest?: string | null;
  observation_id?: string | null;
  obs_name: string;
  source_filenames: string[];
  fits_header?: FitsHeader | null;
  file_status: StorageStatus;
  access_tags: string[];
  created_at?: string | null;
  updated_at?: string | null;
  metadata: Record<string, any>;
}

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

export interface ViewerConf {
  pinnedFields: string[];
  fieldOrder: string[];
}

export const DEFAULT_VIEWER_CONF: ViewerConf = {
  pinnedFields: ['TELESCOP', 'DATE-OBS', 'FILTER', 'EXPTIME', 'AIRMASS', 'PI', 'SCIPROG', 'INSTRUME', 'RA', 'RA_TEL', 'OBSTYPE', 'IMAGETYP'],
  fieldOrder:   ['TELESCOP', 'DATE-OBS', 'FILTER', 'EXPTIME', 'AIRMASS', 'PI', 'SCIPROG', 'INSTRUME', 'RA', 'RA_TEL', 'OBSTYPE', 'IMAGETYP'],
};

export interface Observation {
  _id: string | null;
  obs_name: string;
  file_name?: string | null;
  object_id?: string | null;
  files: FitsFile[];
  filetypes?: string[];
  source_files?: string[];
  fits_header: FitsHeader;
  metadata: Record<string, any>;
  created_at?: string | null;
  updated_at?: string | null;
  oca_jd?: number | null;
}

export interface SearchObject {
  canonized_name: string | null;
  first_alias: string | null;
}

export interface SearchFilters {
  telescop?: string | null;
  date_obs_from?: string | null;
  date_obs_to?: string | null;
  imagetyp?: string | null;
  obstype?: string | null;
  object?: string | null;
  obs_name?: string | null;
  filter?: string[] | null;
  exptime_from?: string | null;
  exptime_to?: string | null;
  pi?: string | null;
  sciprog?: string | null;
  jd_from?: number | null;
  jd_to?: number | null;
  oca_jd_from?: string | null;
  oca_jd_to?: string | null;
  file_types?: string[] | null;
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
  private readonly v2BaseUrl = environment.apiV2BaseUrl;
  private readonly apiLog = inject(ApiLogService);

  loading = signal(false);
  error = signal<string | null>(null);

  token = signal<string | null>(null);
  refreshToken = signal<string | null>(null);
  currentUser = signal<string | null>(null);
  sessionExpiredUser = signal<string | null>(null);
  lastRequestInfo = signal('System initialized');
  isAuthenticated = computed(() => !!this.token());

  pagination = signal<PaginationState>({ page: 1, pageSize: 30, total: 0 });

  viewerConf = signal<ViewerConf>(DEFAULT_VIEWER_CONF);

  constructor() {
    const savedToken = localStorage.getItem('ocadb_token');
    const savedRefresh = localStorage.getItem('ocadb_refresh_token');
    const savedUser = localStorage.getItem('ocadb_user');
    if (savedToken) {
      this.token.set(savedToken);
      this.refreshToken.set(savedRefresh);
      this.currentUser.set(savedUser);
      this.lastRequestInfo.set('Session restored from local storage');
    }
    const savedConf = localStorage.getItem('ocadb_viewer_conf');
    if (savedConf) {
      try { this.viewerConf.set({ ...DEFAULT_VIEWER_CONF, ...JSON.parse(savedConf) }); } catch {}
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
      this.refreshToken.set(data.refresh_token ?? null);
      this.currentUser.set(username);
      this.sessionExpiredUser.set(null);
      localStorage.setItem('ocadb_token', data.access_token);
      if (data.refresh_token) localStorage.setItem('ocadb_refresh_token', data.refresh_token);
      localStorage.setItem('ocadb_user', username);
      this.lastRequestInfo.set('Login successful.');
      this.loading.set(false);
      this.fetchViewerConf();
      return true;
    } catch (e: any) {
      this.handleFetchError(e, 'Login');
      return false;
    }
  }

  logout() {
    this.token.set(null);
    this.refreshToken.set(null);
    this.currentUser.set(null);
    localStorage.removeItem('ocadb_token');
    localStorage.removeItem('ocadb_refresh_token');
    localStorage.removeItem('ocadb_user');
    localStorage.removeItem('ocadb_viewer_conf');
    this.viewerConf.set(DEFAULT_VIEWER_CONF);
    this.error.set(null);
    this.lastRequestInfo.set('User logged out');
  }

  private async authenticatedFetch(url: string, init?: RequestInit): Promise<Response> {
    const response = await this.loggedFetch(url, { ...init, headers: this.authHeaders() });
    if (response.status !== 401 && response.status !== 403) return response;
    const refreshed = await this.tryRefresh();
    if (refreshed) return this.loggedFetch(url, { ...init, headers: this.authHeaders() });
    this.sessionExpiredUser.set(this.currentUser());
    this.logout();
    return response;
  }

  private _refreshPromise: Promise<boolean> | null = null;

  private tryRefresh(): Promise<boolean> {
    if (this._refreshPromise) return this._refreshPromise;
    this._refreshPromise = this._doRefresh().finally(() => { this._refreshPromise = null; });
    return this._refreshPromise;
  }

  private async _doRefresh(): Promise<boolean> {
    const rt = this.refreshToken();
    if (!rt) return false;
    try {
      const res = await this.loggedFetch(`${this.baseUrl}/auth/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rt })
      });
      if (!res.ok) return false;
      const data = await res.json();
      this.token.set(data.access_token);
      this.refreshToken.set(data.refresh_token ?? null);
      localStorage.setItem('ocadb_token', data.access_token);
      if (data.refresh_token) localStorage.setItem('ocadb_refresh_token', data.refresh_token);
      return true;
    } catch {
      return false;
    }
  }

  async searchObservations(filters: SearchFilters, page?: number, sortExpr?: Record<string, 1 | -1> | null): Promise<Observation[]> {
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
      const currentPage = page ?? pag.page;
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
      if (filters.oca_jd_from) body.oca_jd_from = Number(filters.oca_jd_from);
      if (filters.oca_jd_to) body.oca_jd_to = Number(filters.oca_jd_to);
      if (filters.cone_search) body.cone_search = filters.cone_search;
      if (sortExpr) body.sort_expr = sortExpr;

      const url = `${this.v2BaseUrl}/observations/search?page=${currentPage}&page_size=${pag.pageSize}`;
      this.lastRequestInfo.set(`POST /api/v2/observations/search (page ${currentPage})`);

      const response = await this.authenticatedFetch(url, {
        method: 'POST',
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          throw new Error('Session expired. Please login again.');
        }
        if (response.status === 404) {
          this.lastRequestInfo.set('No results found');
          this.loading.set(false);
          this.pagination.update(p => ({ ...p, total: 0, page: 1 }));
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

      const result: { data: Observation[]; metadata: { total_count: number }[] } = await response.json();
      const total = result.metadata?.[0]?.total_count ?? 0;
      this.pagination.update(p => ({ ...p, total, page: currentPage }));
      this.lastRequestInfo.set(`Loaded ${result.data.length} of ${total} observations (page ${currentPage})`);
      this.loading.set(false);
      return result.data ?? [];
    } catch (e: any) {
      this.handleFetchError(e, 'Search');
      return [];
    }
  }

  async fetchValuesList(field: 'telescop' | 'imagetyp' | 'obstype' | 'pi' | 'object' | 'sciprog'): Promise<string[]> {
    if (!this.token()) return [];
    try {
      const response = await this.authenticatedFetch(`${this.v2BaseUrl}/observations/values/${field}`);
      if (!response.ok) return [];
      return await response.json();
    } catch {
      return [];
    }
  }

  async fetchSearchObjects(): Promise<SearchObject[]> {
    if (!this.token()) return [];
    try {
      const response = await this.authenticatedFetch(`${this.v2BaseUrl}/observations/values/search_object`);
      if (!response.ok) return [];
      return await response.json();
    } catch {
      return [];
    }
  }

  async fetchPresignedUrl(filename: string, expiresIn?: number): Promise<string | null> {
    try {
      let url = `${this.v2BaseUrl}/files/by-filename/${encodeURIComponent(filename)}/plainurl`;
      if (expiresIn != null) url += `?expires_in=${expiresIn}`;
      const response = await this.authenticatedFetch(url);
      if (!response.ok) return null;
      return await response.json();
    } catch {
      return null;
    }
  }

  async downloadScript(ids: string[], username?: string, includeCalibration = false, fileTypes?: string[]): Promise<void> {
    try {
      const response = await this.authenticatedFetch(`${this.v2BaseUrl}/observations/download-script`, {
        method: 'POST',
        body: JSON.stringify({
          obs_ids: ids,
          ...(username ? { username } : {}),
          include_calibration: includeCalibration,
          ...(fileTypes ? { file_types: fileTypes } : {})
        })
      });
      if (!response.ok) {
        const msg = await this.extractErrorMessage(response, `Download script failed (${response.status})`);
        this.error.set(msg);
        return;
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'download.sh';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      this.handleFetchError(e, 'Download script');
    }
  }

  async fetchObjectCoordinates(objectName: string): Promise<{ra: number, dec: number} | null> {
    try {
      const response = await this.authenticatedFetch(`${this.v2BaseUrl}/observations/search?page=1&page_size=1`, {
        method: 'POST',
        body: JSON.stringify({ object: objectName })
      });
      if (!response.ok) return null;
      const result = await response.json();
      const obs = result.data?.[0];
      const ra = obs?.fits_header?.['RA'];
      const dec = obs?.fits_header?.['DEC'];
      if (ra == null || dec == null) return null;
      return { ra: Number(ra), dec: Number(dec) };
    } catch {
      return null;
    }
  }

  async fetchObservationByName(name: string): Promise<Observation | null> {
    try {
      const response = await this.authenticatedFetch(`${this.v2BaseUrl}/observations/by-observation-name/${encodeURIComponent(name)}/`);
      if (!response.ok) return null;
      return await response.json();
    } catch {
      return null;
    }
  }

  async fetchObservationById(id: string): Promise<Observation | null> {
    try {
      const response = await this.authenticatedFetch(`${this.v2BaseUrl}/observations/${id}/`);
      if (!response.ok) return null;
      return await response.json();
    } catch {
      return null;
    }
  }

  async fetchViewerConf(): Promise<void> {
    try {
      const response = await this.authenticatedFetch(`${this.baseUrl}/auth/user/viewer_conf`);
      if (!response.ok) return;
      const conf: ViewerConf = { ...DEFAULT_VIEWER_CONF, ...await response.json() };
      this.viewerConf.set(conf);
      localStorage.setItem('ocadb_viewer_conf', JSON.stringify(conf));
    } catch {}
  }

  async saveViewerConf(conf: ViewerConf): Promise<void> {
    this.viewerConf.set(conf);
    localStorage.setItem('ocadb_viewer_conf', JSON.stringify(conf));
    try {
      await this.authenticatedFetch(`${this.baseUrl}/auth/user/viewer_conf`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(conf),
      });
    } catch {}
  }

  async fetchFileByFilename(filename: string): Promise<FitsFile | null> {
    try {
      const response = await this.authenticatedFetch(`${this.v2BaseUrl}/files/by-filename/${encodeURIComponent(filename)}/`);
      if (!response.ok) return null;
      return await response.json();
    } catch {
      return null;
    }
  }

  async fetchTelescopeFilters(telescope: string): Promise<string[]> {
    if (!this.token() || !telescope) return [];
    try {
      const response = await this.authenticatedFetch(`${this.v2BaseUrl}/observations/values/${telescope}/filter`);
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
