import { SearchFilters } from './services/ocadb.service';

/**
 * Pure serialize/parse helpers for reflecting search + view state in the URL query
 * string. No signals, no DOM access beyond taking/returning plain values — the actual
 * history.pushState/replaceState calls and signal reads/writes live in app.component.ts,
 * this file only defines the mapping between state shapes and query params.
 */

export interface UrlSearchState {
  filters: SearchFilters; // cone_search is NOT included here, see `cone` below
  cone: { coordinates: string; radius: number; epoch: string } | null;
  sortExpr: { col: string; dir: 1 | -1 } | null;
  page: number;
}

export interface UrlViewState {
  obsName: string | null;
  fileName: string | null;
}

// Scalar SearchFilters fields that map 1:1 onto a same-named query param.
const SCALAR_FILTER_KEYS: (keyof SearchFilters)[] = [
  'telescop', 'date_obs_from', 'date_obs_to', 'imagetyp', 'obstype', 'object', 'obs_name',
  'exptime_from', 'exptime_to', 'pi', 'sciprog', 'jd_from', 'jd_to', 'oca_jd_from', 'oca_jd_to',
];

// Array SearchFilters fields, comma-joined into one query param each.
const ARRAY_FILTER_KEYS: (keyof SearchFilters)[] = ['filter', 'file_types', 'tags'];

export function buildSearchParams(search: UrlSearchState, view: UrlViewState): URLSearchParams {
  const params = new URLSearchParams();

  for (const key of SCALAR_FILTER_KEYS) {
    const value = search.filters[key];
    if (value !== null && value !== undefined && value !== '') {
      params.set(key, String(value));
    }
  }
  for (const key of ARRAY_FILTER_KEYS) {
    const value = search.filters[key] as string[] | null | undefined;
    if (value && value.length) params.set(key, value.join(','));
  }
  if (search.filters.has_requested_files) {
    params.set('has_requested_files', '1');
  }
  if (search.cone) {
    params.set('cone', search.cone.coordinates);
    params.set('cone_radius', String(search.cone.radius));
    params.set('cone_epoch', search.cone.epoch);
  }
  if (search.sortExpr) {
    params.set('sort', `${search.sortExpr.col}:${search.sortExpr.dir}`);
  }
  if (search.page && search.page !== 1) {
    params.set('page', String(search.page));
  }
  if (view.obsName) params.set('obs', view.obsName);
  if (view.fileName) params.set('file', view.fileName);

  return params;
}

export function parseSearchParams(qs: string): { search: UrlSearchState; view: UrlViewState } {
  const params = new URLSearchParams(qs);
  const filters: SearchFilters = {};

  for (const key of SCALAR_FILTER_KEYS) {
    const raw = params.get(key);
    if (raw === null) continue;
    if (key === 'jd_from' || key === 'jd_to') {
      (filters as any)[key] = Number(raw);
    } else {
      (filters as any)[key] = raw;
    }
  }
  for (const key of ARRAY_FILTER_KEYS) {
    const raw = params.get(key);
    if (raw) (filters as any)[key] = raw.split(',').filter(Boolean);
  }
  if (params.get('has_requested_files')) {
    filters.has_requested_files = true;
  }

  const coneCoordinates = params.get('cone');
  const cone = coneCoordinates ? {
    coordinates: coneCoordinates,
    radius: Number(params.get('cone_radius') ?? '60'),
    epoch: params.get('cone_epoch') ?? '2000.0',
  } : null;

  const sortRaw = params.get('sort');
  let sortExpr: { col: string; dir: 1 | -1 } | null = null;
  if (sortRaw) {
    const [col, dirRaw] = sortRaw.split(':');
    const dir = dirRaw === '-1' ? -1 : 1;
    if (col) sortExpr = { col, dir };
  }

  const pageRaw = params.get('page');
  const page = pageRaw ? Math.max(1, parseInt(pageRaw, 10) || 1) : 1;

  return {
    search: { filters, cone, sortExpr, page },
    view: { obsName: params.get('obs'), fileName: params.get('file') },
  };
}
