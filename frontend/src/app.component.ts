import { Component, signal, computed, inject, OnInit, ElementRef, ViewChild, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { OcadbService, Observation, SearchFilters, SearchObject, FitsFile, StorageStatusType, ViewerConf, DEFAULT_VIEWER_CONF } from './services/ocadb.service';
import { ApiLogService, ApiLogEntry } from './services/api-log.service';
import { FlatpickrDirective } from './flatpickr.directive';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, FlatpickrDirective],
  templateUrl: './app.component.html'
})
export class AppComponent implements OnInit {
  ocadbService = inject(OcadbService);
  apiLog = inject(ApiLogService);
  private _lastCalibrationKey: string | null = null;
  private _lastSourceKey: string | null = null;
  private _coneObjectKey: string | null = null;

  private static readonly LOGIN_BACKGROUNDS = Array.from({length: 23}, (_, i) => `/${i + 1}b.JPG`);
  loginBackground = signal(
    inject(DomSanitizer).bypassSecurityTrustStyle(
      `url(${AppComponent.LOGIN_BACKGROUNDS[Math.floor(Math.random() * AppComponent.LOGIN_BACKGROUNDS.length)]})`
    )
  );

  loginData = { username: '', password: '' };

  displayedObservations = signal<Observation[]>([]);
  filesLoading = signal(false);
  calibrationFiles = signal<FitsFile[]>([]);
  calibrationMissingFiles = signal<string[]>([]);
  calibrationFilesLoading = signal(false);
  sourceFiles = signal<FitsFile[]>([]);
  sourceMissingFiles = signal<string[]>([]);
  sourceFilesLoading = signal(false);
  fileHistory = signal<FitsFile[]>([]);
  hasSearched = signal(false);
  selectedFile = signal<FitsFile | null>(null);
  downloadingFile = signal(false);
  shareFile = signal<FitsFile | null>(null);
  shareUrl = signal<string | null>(null);
  shareExpiry = signal<number>(3600);
  shareLoading = signal(false);
  shareCopied = signal(false);
  selectedMetadata = signal<{ obs_name: string; metadata: Record<string, any> } | null>(null);
  selectedMetadataHtml = computed(() => {
    const m = this.selectedMetadata();
    return m ? this.formatJsonHtml(m.metadata) : null;
  });
  selectedObservation = signal<Observation | null>(null);
  showFilters = signal(true);
  showDebugPanel = signal(false);
  selectedObsIds = signal<Set<string>>(new Set());
  selectionPageMap = signal<Map<string, number>>(new Map());

  hasSelectionOnPrevPages = computed(() => {
    const currentPage = this.ocadbService.pagination().page;
    const selected = this.selectedObsIds();
    return [...this.selectionPageMap().entries()].some(([id, page]) => selected.has(id) && page < currentPage);
  });
  hasSelectionOnNextPages = computed(() => {
    const currentPage = this.ocadbService.pagination().page;
    const selected = this.selectedObsIds();
    return [...this.selectionPageMap().entries()].some(([id, page]) => selected.has(id) && page > currentPage);
  });
  scriptLoading = signal(false);
  showDownloadDialog = signal(false);
  sortExpr = signal<{ col: string; dir: 1 | -1 } | null>(null);
  downloadForCurrentUser = signal(true);
  downloadCustomUsername = signal('');
  downloadIncludeCalibration = signal(false);
  readonly DOWNLOAD_FILE_TYPES = ['zdf', 'raw', 'flat', 'zero', 'dark', 'master'] as const;
  readonly DOWNLOAD_CALIB_TYPES = new Set(['flat', 'zero', 'dark', 'master']);
  downloadFileTypes = signal<Set<string>>(new Set(this.DOWNLOAD_FILE_TYPES));
  expandedLogEntry = signal<number | null>(null);
  editingPage = signal(false);
  pageInputValue = signal('');
  @ViewChild('pageInput') pageInputRef?: ElementRef<HTMLInputElement>;
  @ViewChild('tableScrollContainer') tableScrollContainer?: ElementRef<HTMLElement>;

  hasSelectionAbove = signal(false);
  hasSelectionBelow = signal(false);

  filters = signal<SearchFilters>({});
  telescopeDropdownOpen = signal(false);
  telescopeHighlightedIndex = signal(-1);
  obsTypeDropdownOpen = signal(false);
  obsTypeHighlightedIndex = signal(-1);
  imageTypDropdownOpen = signal(false);
  imageTypHighlightedIndex = signal(-1);
  objectDropdownOpen = signal(false);
  objectQuery = signal('');
  objectHighlightedIndex = signal(-1);
  coneSearchExpanded = signal(false);
  piDropdownOpen = signal(false);
  piQuery = signal('');
  piHighlightedIndex = signal(-1);
  sciprogDropdownOpen = signal(false);
  sciprogQuery = signal('');
  sciprogHighlightedIndex = signal(-1);
  filterDropdownOpen = signal(false);
  filterQuery = signal('');
  filterHighlightedIndex = signal(-1);
  dateRangeMode = signal<'date' | 'oca_jd'>('date');
  obsNameFocused = signal(false);
  otherFieldsFocused = signal(false);

  coneRa = signal<number | null>(null);
  coneDec = signal<number | null>(null);
  coneRadius = signal<number>(60);
  coneEpoch = signal('2000.0');
  coneSearchError = signal<string | null>(null);

  // Available values for dropdowns (loaded from API)
  telescopes = signal<string[]>([]);
  imageTypes = signal<string[]>([]);
  obsTypes = signal<string[]>([]);
  availableFilters = signal<string[]>([]);
  filteredImageTypes = computed(() => this.imageTypes().filter(t => t.toLowerCase() !== 'science'));
  filteredAvailableFilters = computed(() => {
    const q = this.filterQuery().toLowerCase();
    const nonEmpty = this.availableFilters().filter(f => f.trim());
    if (!q) return nonEmpty;
    return nonEmpty.filter(f => f.toLowerCase().includes(q));
  });
  objects = signal<SearchObject[]>([]);
  filteredObjects = computed(() => {
    const q = this.objectQuery().toLowerCase().replace(/[-_.\s]/g, '');
    if (!q) return this.objects();
    return this.objects().filter(o => (o.canonized_name ?? '').includes(q));
  });
  sciprogs = signal<string[]>([]);
  filteredSciprogs = computed(() => {
    const q = this.sciprogQuery().toLowerCase().replace(/[-_.\s]/g, '');
    const nonEmpty = this.sciprogs().filter(s => s.trim());
    if (!q) return nonEmpty;
    return nonEmpty.filter(s => s.toLowerCase().replace(/[-_.\s]/g, '').includes(q));
  });
  pis = signal<string[]>([]);
  filteredPis = computed(() => {
    const q = this.piQuery().toLowerCase().replace(/[-_.\s]/g, '');
    const nonEmpty = this.pis().filter(p => p.trim());
    if (!q) return nonEmpty;
    return nonEmpty.filter(p => p.toLowerCase().replace(/[-_.\s]/g, '').includes(q));
  });

  constructor() {
    effect(() => {
      const expired = this.ocadbService.sessionExpiredUser();
      if (expired) this.loginData.username = expired;
    });

    effect((onCleanup) => {
      const obs = this.selectedObservation();
      if (!obs?._id) return;

      const intervalId = setInterval(async () => {
        const fresh = await this.ocadbService.fetchObservationById(obs._id!);
        if (!fresh) return;
        if (this.selectedObservation()?._id !== obs._id) return;
        this.selectedObservation.set(fresh);
        this.displayedObservations.update(list =>
          list.map(o => o._id === fresh._id ? fresh : o)
        );
      }, 10000);

      onCleanup(() => clearInterval(intervalId));
    });

    effect((onCleanup) => {
      const obs = this.selectedObservation();
      const obsFilenames = new Set(obs?.files.map(f => f.filename) ?? []);
      const names = [...new Set(
        (obs?.files.flatMap(f => f.source_filenames ?? []) ?? []).filter(n => !obsFilenames.has(n))
      )];
      const key = names.slice().sort().join('\0');

      const keyChanged = key !== this._lastCalibrationKey;
      this._lastCalibrationKey = key;

      if (!names.length) {
        this.calibrationFiles.set([]);
        this.calibrationMissingFiles.set([]);
        if (!(obs?.source_files?.length)) this.calibrationFilesLoading.set(false);
        return;
      }

      const fetchKey = key;
      const doFetch = (showLoading: boolean) => {
        if (showLoading) {
          this.calibrationFilesLoading.set(true);
          this.calibrationFiles.set([]);
          this.calibrationMissingFiles.set([]);
        }
        Promise.all(names.map(n => this.ocadbService.fetchFileByFilename(n).then(f => ({ name: n, file: f }))))
          .then(results => {
            if (this._lastCalibrationKey !== fetchKey) return;
            this.calibrationFiles.set(results.filter(r => r.file !== null).map(r => r.file!));
            this.calibrationMissingFiles.set(results.filter(r => r.file === null).map(r => r.name));
            this.calibrationFilesLoading.set(false);
          });
      };

      if (keyChanged) doFetch(true);
      const intervalId = setInterval(() => doFetch(false), 10000);
      onCleanup(() => clearInterval(intervalId));
    });

    effect((onCleanup) => {
      const file = this.selectedFile();
      if (!file?.filename) return;

      const intervalId = setInterval(async () => {
        const fresh = await this.ocadbService.fetchFileByFilename(file.filename);
        if (!fresh) return;
        if (this.selectedFile()?.filename !== file.filename) return;
        this.selectedFile.set(fresh);
        this.displayedObservations.update(list =>
          list.map(obs => ({
            ...obs,
            files: obs.files.map(f => f._id === fresh._id ? fresh : f)
          }))
        );
      }, 10000);

      onCleanup(() => clearInterval(intervalId));
    });

    effect((onCleanup) => {
      const file = this.selectedFile();
      const names = [...new Set(file?.source_filenames ?? [])];
      const key = names.slice().sort().join('\0');

      const keyChanged = key !== this._lastSourceKey;
      this._lastSourceKey = key;

      if (!names.length) {
        this.sourceFiles.set([]);
        this.sourceMissingFiles.set([]);
        this.sourceFilesLoading.set(false);
        return;
      }

      const fetchKey = key;
      const doFetch = (showLoading: boolean) => {
        if (showLoading) this.sourceFilesLoading.set(true);
        Promise.all(names.map(n => this.ocadbService.fetchFileByFilename(n).then(f => ({ name: n, file: f }))))
          .then(results => {
            if (this._lastSourceKey !== fetchKey) return;
            this.sourceFiles.set(results.filter(r => r.file !== null).map(r => r.file!));
            this.sourceMissingFiles.set(results.filter(r => r.file === null).map(r => r.name));
            this.sourceFilesLoading.set(false);
          });
      };

      if (keyChanged) doFetch(true);
      const intervalId = setInterval(() => doFetch(false), 10000);
      onCleanup(() => clearInterval(intervalId));
    });

    effect(() => {
      this.selectedObsIds();
      this.displayedObservations();
      setTimeout(() => this.updateSelectionIndicators(), 0);
    });
  }

  scrollToNearestSelectionAbove() {
    const container = this.tableScrollContainer?.nativeElement;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    let nearest: Element | null = null;
    let nearestBottom = -Infinity;
    for (const id of this.selectedObsIds()) {
      const td = container.querySelector(`td[data-obs-id="${id}"]`);
      if (!td) continue;
      const tr = td.closest('tr')!;
      const rowRect = tr.getBoundingClientRect();
      if (rowRect.bottom < rect.top && rowRect.bottom > nearestBottom) {
        nearestBottom = rowRect.bottom;
        nearest = tr;
      }
    }
    nearest?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  scrollToNearestSelectionBelow() {
    const container = this.tableScrollContainer?.nativeElement;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    let nearest: Element | null = null;
    let nearestTop = Infinity;
    for (const id of this.selectedObsIds()) {
      const td = container.querySelector(`td[data-obs-id="${id}"]`);
      if (!td) continue;
      const tr = td.closest('tr')!;
      const rowRect = tr.getBoundingClientRect();
      if (rowRect.top > rect.bottom && rowRect.top < nearestTop) {
        nearestTop = rowRect.top;
        nearest = tr;
      }
    }
    nearest?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  updateSelectionIndicators() {
    const container = this.tableScrollContainer?.nativeElement;
    if (!container || this.selectedObsIds().size === 0) {
      this.hasSelectionAbove.set(false);
      this.hasSelectionBelow.set(false);
      return;
    }
    const rect = container.getBoundingClientRect();
    let above = false, below = false;
    for (const id of this.selectedObsIds()) {
      const td = container.querySelector(`td[data-obs-id="${id}"]`);
      if (!td) continue;
      const rowRect = td.closest('tr')!.getBoundingClientRect();
      if (rowRect.bottom < rect.top) above = true;
      if (rowRect.top > rect.bottom) below = true;
      if (above && below) break;
    }
    this.hasSelectionAbove.set(above);
    this.hasSelectionBelow.set(below);
  }

  ngOnInit() {
    if (this.ocadbService.isAuthenticated()) {
      this.search();
    }
  }

  async handleLogin(event: Event) {
    event.preventDefault();
    const success = await this.ocadbService.login(this.loginData.username, this.loginData.password);
    if (success) {
      this.search();
    }
  }

  openSourceFile(file: FitsFile) {
    const current = this.selectedFile();
    if (current) this.fileHistory.update(h => [...h, current]);
    this.selectedFile.set(file);
  }

  goBackFile() {
    const history = this.fileHistory();
    if (history.length > 0) {
      const prev = history[history.length - 1];
      this.fileHistory.update(h => h.slice(0, -1));
      this.selectedFile.set(prev);
    } else {
      this.selectedFile.set(null);
    }
  }

  testSpinner() {
    this.ocadbService.loading.set(true);
    setTimeout(() => this.ocadbService.loading.set(false), 3000);
  }

  closeFileViewer() {
    this.selectedFile.set(null);
    this.fileHistory.set([]);
  }

  async openMetadata(obs: Observation) {
    if (obs.metadata && Object.keys(obs.metadata).length > 0) {
      this.selectedMetadata.set({ obs_name: obs.obs_name, metadata: obs.metadata });
      return;
    }
    if (!obs._id) return;
    const full = await this.ocadbService.fetchObservationById(obs._id);
    if (!full) return;
    this.displayedObservations.update(list => list.map(o => o._id === full._id ? full : o));
    this.selectedMetadata.set({ obs_name: full.obs_name, metadata: full.metadata });
  }

  async openObservation(obs: Observation) {
    this.selectedObservation.set(obs);
    this.filesLoading.set(true);
    this.calibrationFilesLoading.set(true);
    if (!obs._id) return;
    const full = await this.ocadbService.fetchObservationById(obs._id);
    if (!full || this.selectedObservation()?._id !== obs._id) return;
    this.selectedObservation.set(full);
    this.filesLoading.set(false);
    this.displayedObservations.update(list =>
      list.map(o => o._id === full._id ? full : o)
    );
  }

  handleLogout() {
    this.ocadbService.logout();
    this.loginData = { username: '', password: '' };
    this.displayedObservations.set([]);
  }

  updateFilter(key: keyof SearchFilters, value: any) {
    this.filters.update(f => ({ ...f, [key]: value || null }));
  }

  formatDateInput(event: Event, key: 'date_obs_from' | 'date_obs_to') {
    const input = event.target as HTMLInputElement;
    const selStart = input.selectionStart ?? input.value.length;
    const digitsBeforeCursor = input.value.slice(0, selStart).replace(/\D/g, '').length;

    const raw = input.value.replace(/\D/g, '').slice(0, 8);
    let formatted = raw;
    if (raw.length > 4) formatted = `${raw.slice(0, 4)}-${raw.slice(4)}`;
    if (raw.length > 6) formatted = `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6)}`;

    input.value = formatted;

    let digitsSeen = 0;
    let newCursor = formatted.length;
    for (let i = 0; i < formatted.length; i++) {
      if (formatted[i] !== '-') digitsSeen++;
      if (digitsSeen === digitsBeforeCursor) {
        newCursor = i + 1;
        if (newCursor < formatted.length && formatted[newCursor] === '-') newCursor++;
        break;
      }
    }
    input.setSelectionRange(newCursor, newCursor);

    if (formatted.length === 10) {
      const time = key === 'date_obs_from' ? ' 00:00:00' : ' 23:59:59';
      this.updateFilter(key, formatted + time);
    } else {
      this.updateFilter(key, null);
    }
  }

  updateFilterArray(key: keyof SearchFilters, value: string) {
    const items = value ? value.split(',').map(s => s.trim()).filter(Boolean) : null;
    this.filters.update(f => ({ ...f, [key]: items }));
  }

  toggleFileTypeFilter(ft: string) {
    this.filters.update(f => {
      const current = f.file_types ?? [];
      const next = current.includes(ft) ? current.filter(t => t !== ft) : [...current, ft];
      return { ...f, file_types: next.length ? next : null };
    });
  }

  async onTelescopeChange(telescope: string) {
    this.updateFilter('telescop', telescope);
    const filterList = await this.ocadbService.fetchTelescopeFilters(telescope || 'all');
    this.availableFilters.set(filterList);
    const currentFilter = this.filters().filter?.[0];
    if (currentFilter && !filterList.includes(currentFilter)) {
      this.filters.update(f => ({ ...f, filter: null }));
      this.filterQuery.set('');
    }
  }

  switchDateRangeMode(mode: 'date' | 'oca_jd') {
    if (this.dateRangeMode() === mode) return;
    const f = this.filters();
    const wasActive = mode === 'date'
      ? (f.oca_jd_from != null || f.oca_jd_to != null)
      : !!(f.date_obs_from || f.date_obs_to);
    this.dateRangeMode.set(mode);
    if (mode === 'date') {
      this.updateFilter('oca_jd_from', null);
      this.updateFilter('oca_jd_to', null);
    } else {
      this.updateFilter('date_obs_from', '');
      this.updateFilter('date_obs_to', '');
    }
    if (wasActive) this.search();
  }

  get obsNameMode(): boolean {
    return !!this.filters().obs_name || this.obsNameFocused();
  }

  get otherFiltersActive(): boolean {
    if (this.otherFieldsFocused()) return true;
    const f = this.filters();
    return !!(f.telescop || f.object || f.imagetyp || f.obstype ||
      f.filter?.length || f.date_obs_from || f.date_obs_to ||
      f.pi || f.sciprog || f.jd_from != null || f.jd_to != null ||
      f.oca_jd_from != null || f.oca_jd_to != null ||
      f.file_types?.length || this.coneRa() != null || this.coneSearchExpanded());
  }


  async search() {
    if (!this.ocadbService.isAuthenticated()) return;

    this.hasSearched.set(true);
    this.showFilters.set(false);

    if (this.obsNameMode) {
      this.ocadbService.loading.set(true);
      const obs = await this.ocadbService.fetchObservationByName(this.filters().obs_name!);
      this.ocadbService.loading.set(false);
      const results = obs ? [obs] : [];
      this.displayedObservations.set(results);
      this.ocadbService.pagination.update(p => ({ ...p, total: results.length, page: 1 }));
      this.loadDropdowns();
      return;
    }

    const hasRa = this.coneRa() != null;
    const hasDec = this.coneDec() != null;
    if (this.coneSearchExpanded() && hasRa !== hasDec) {
      this.coneSearchError.set('Both RA and Dec are required for cone search.');
      return;
    }
    this.coneSearchError.set(null);

    const cone_search = (this.coneSearchExpanded() && hasRa && hasDec) ? {
      ra: this.coneRa()!,
      dec: this.coneDec()!,
      arc_seconds: this.coneRadius(),
      epoch: this.coneEpoch() || '2000.0'
    } : null;

    this.ocadbService.pagination.update(p => ({ ...p, page: 1 }));
    const baseFilters = this.coneSearchExpanded() ? { ...this.filters(), object: null } : this.filters();
    const results = await this.ocadbService.searchObservations({ ...baseFilters, cone_search }, 1, this.getSortExpr());
    this.displayedObservations.set(results);
    this.loadDropdowns();
  }

  get totalPages(): number {
    const pag = this.ocadbService.pagination();
    return Math.max(1, Math.ceil(pag.total / pag.pageSize));
  }

  get visiblePages(): (number | null)[] {
    const total = this.totalPages;
    const current = this.ocadbService.pagination().page;
    const shown = new Set<number>();
    shown.add(1);
    shown.add(total);
    for (let p = Math.max(1, current - 1); p <= Math.min(total, current + 1); p++) shown.add(p);
    const sorted = [...shown].sort((a, b) => a - b);
    const result: (number | null)[] = [];
    for (let i = 0; i < sorted.length; i++) {
      if (i > 0 && sorted[i] - sorted[i - 1] > 1) result.push(null);
      result.push(sorted[i]);
    }
    return result;
  }

  async goToPage(page: number) {
    if (page < 1 || page > this.totalPages) return;
    const results = await this.ocadbService.searchObservations(this.filters(), page, this.getSortExpr());
    this.displayedObservations.set(results);
  }

  startPageEdit() {
    this.pageInputValue.set(String(this.ocadbService.pagination().page));
    this.editingPage.set(true);
    setTimeout(() => this.pageInputRef?.nativeElement.focus(), 0);
  }

  async commitPageEdit() {
    const p = parseInt(this.pageInputValue(), 10);
    this.editingPage.set(false);
    if (!isNaN(p)) await this.goToPage(p);
  }

  toggleObsSelection(id: string) {
    const isSelected = this.selectedObsIds().has(id);
    const currentPage = this.ocadbService.pagination().page;
    this.selectedObsIds.update(set => {
      const next = new Set(set);
      isSelected ? next.delete(id) : next.add(id);
      return next;
    });
    this.selectionPageMap.update(m => {
      const next = new Map(m);
      isSelected ? next.delete(id) : next.set(id, currentPage);
      return next;
    });
  }

  private _dragSelectActive = false;
  private _dragSelectMode: 'select' | 'deselect' = 'select';

  private _applyDragSelect(obsId: string) {
    const currentPage = this.ocadbService.pagination().page;
    this.selectedObsIds.update(set => {
      const next = new Set(set);
      this._dragSelectMode === 'select' ? next.add(obsId) : next.delete(obsId);
      return next;
    });
    this.selectionPageMap.update(m => {
      const next = new Map(m);
      this._dragSelectMode === 'select' ? next.set(obsId, currentPage) : next.delete(obsId);
      return next;
    });
  }

  startDragSelect(obsId: string, event: MouseEvent | TouchEvent) {
    event.stopPropagation();
    event.preventDefault();
    this._dragSelectActive = true;
    this._dragSelectMode = this.selectedObsIds().has(obsId) ? 'deselect' : 'select';
    this._applyDragSelect(obsId);

    const onTouchMove = (e: TouchEvent) => {
      e.preventDefault();
      const t = e.touches[0];
      const el = document.elementFromPoint(t.clientX, t.clientY)?.closest('[data-obs-id]');
      if (el) this._applyDragSelect(el.getAttribute('data-obs-id')!);
    };
    const onUp = () => {
      this._dragSelectActive = false;
      document.removeEventListener('mouseup', onUp);
      document.removeEventListener('touchend', onUp);
      document.removeEventListener('touchmove', onTouchMove);
    };
    document.addEventListener('mouseup', onUp);
    document.addEventListener('touchend', onUp);
    document.addEventListener('touchmove', onTouchMove, { passive: false });
  }

  onDragSelectEnter(obsId: string) {
    if (this._dragSelectActive) this._applyDragSelect(obsId);
  }

  allOnPageSelected(): boolean {
    const obs = this.displayedObservations();
    return obs.length > 0 && obs.every(o => o._id && this.selectedObsIds().has(o._id));
  }

  toggleSelectAll() {
    const currentPage = this.ocadbService.pagination().page;
    const ids = this.displayedObservations().map(o => o._id).filter((id): id is string => !!id);
    const allSelected = ids.every(id => this.selectedObsIds().has(id));
    this.selectedObsIds.update(set => {
      const next = new Set(set);
      if (allSelected) ids.forEach(id => next.delete(id));
      else ids.forEach(id => next.add(id));
      return next;
    });
    this.selectionPageMap.update(m => {
      const next = new Map(m);
      if (allSelected) ids.forEach(id => next.delete(id));
      else ids.forEach(id => next.set(id, currentPage));
      return next;
    });
  }

  clearSelection() {
    this.selectedObsIds.set(new Set());
    this.selectionPageMap.set(new Map());
  }

  async goToNearestSelectionBefore() {
    const currentPage = this.ocadbService.pagination().page;
    const selected = this.selectedObsIds();
    const pages = [...this.selectionPageMap().entries()]
      .filter(([id, page]) => selected.has(id) && page < currentPage)
      .map(([, page]) => page);
    if (pages.length) await this.goToPage(Math.max(...pages));
  }

  async goToNearestSelectionAfter() {
    const currentPage = this.ocadbService.pagination().page;
    const selected = this.selectedObsIds();
    const pages = [...this.selectionPageMap().entries()]
      .filter(([id, page]) => selected.has(id) && page > currentPage)
      .map(([, page]) => page);
    if (pages.length) await this.goToPage(Math.min(...pages));
  }

  openDownloadDialog() {
    this.downloadForCurrentUser.set(true);
    this.downloadCustomUsername.set('');
    this.downloadIncludeCalibration.set(false);
    this.downloadFileTypes.set(new Set(this.DOWNLOAD_FILE_TYPES));
    this.showDownloadDialog.set(true);
  }

  toggleDownloadFileType(type: string) {
    this.downloadFileTypes.update(set => {
      const next = new Set(set);
      next.has(type) ? next.delete(type) : next.add(type);
      return next;
    });
  }

  async executeDownloadScript() {
    const ids = [...this.selectedObsIds()];
    if (!ids.length) return;
    const username = this.downloadForCurrentUser()
      ? (this.ocadbService.currentUser() ?? undefined)
      : this.downloadCustomUsername().trim() || undefined;
    this.scriptLoading.set(true);
    this.showDownloadDialog.set(false);
    const includeCalib = this.downloadIncludeCalibration();
    const selectedTypes = [...this.downloadFileTypes()].filter(t => includeCalib || !this.DOWNLOAD_CALIB_TYPES.has(t));
    const visibleTypes = this.DOWNLOAD_FILE_TYPES.filter(t => includeCalib || !this.DOWNLOAD_CALIB_TYPES.has(t));
    const allTypes = selectedTypes.length === visibleTypes.length;
    await this.ocadbService.downloadScript(ids, username, includeCalib, allTypes ? undefined : selectedTypes);
    this.scriptLoading.set(false);
  }

  private scrollDropdownItem(key: string, index: number) {
    queueMicrotask(() => {
      const container = document.querySelector(`[data-dropdown="${key}"]`);
      if (!container) return;
      const items = container.querySelectorAll<HTMLElement>('button');
      items[index]?.scrollIntoView({ block: 'nearest' });
    });
  }

  onTelescopeKeydown(event: KeyboardEvent) {
    const list = this.telescopes();
    const total = list.length + 1; // +1 for "All"
    const idx = this.telescopeHighlightedIndex();

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      this.telescopeDropdownOpen.set(true);
      const newIdx = idx < total - 1 ? idx + 1 : 0;
      this.telescopeHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('telescope', newIdx);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      this.telescopeDropdownOpen.set(true);
      const newIdx = idx > 0 ? idx - 1 : total - 1;
      this.telescopeHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('telescope', newIdx);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (this.telescopeDropdownOpen() && idx >= 0) {
        if (idx === 0) {
          this.onTelescopeChange('');
        } else {
          this.onTelescopeChange(list[idx - 1]);
        }
        this.telescopeDropdownOpen.set(false);
        this.search();
      } else {
        this.telescopeDropdownOpen.set(!this.telescopeDropdownOpen());
      }
      this.telescopeHighlightedIndex.set(-1);
    } else if (event.key === 'Escape') {
      this.telescopeDropdownOpen.set(false);
      this.telescopeHighlightedIndex.set(-1);
    }
  }

  onObsTypeKeydown(event: KeyboardEvent) {
    const list = this.obsTypes();
    const total = list.length + 1; // +1 for "All"
    const idx = this.obsTypeHighlightedIndex();

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      this.obsTypeDropdownOpen.set(true);
      const newIdx = idx < total - 1 ? idx + 1 : 0;
      this.obsTypeHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('obstype', newIdx);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      this.obsTypeDropdownOpen.set(true);
      const newIdx = idx > 0 ? idx - 1 : total - 1;
      this.obsTypeHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('obstype', newIdx);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (this.obsTypeDropdownOpen() && idx >= 0) {
        if (idx === 0) {
          this.updateFilter('obstype', '');
          this.updateFilter('imagetyp', '');
        } else {
          const t = list[idx - 1];
          this.updateFilter('obstype', t);
          if (t !== 'calib') this.updateFilter('imagetyp', '');
        }
        this.obsTypeDropdownOpen.set(false);
        this.search();
      } else {
        this.obsTypeDropdownOpen.set(!this.obsTypeDropdownOpen());
      }
      this.obsTypeHighlightedIndex.set(-1);
    } else if (event.key === 'Escape') {
      this.obsTypeDropdownOpen.set(false);
      this.obsTypeHighlightedIndex.set(-1);
    }
  }

  onImageTypKeydown(event: KeyboardEvent) {
    const list = this.filteredImageTypes();
    const total = list.length + 1; // +1 for "All"
    const idx = this.imageTypHighlightedIndex();

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      this.imageTypDropdownOpen.set(true);
      const newIdx = idx < total - 1 ? idx + 1 : 0;
      this.imageTypHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('imagetyp', newIdx);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      this.imageTypDropdownOpen.set(true);
      const newIdx = idx > 0 ? idx - 1 : total - 1;
      this.imageTypHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('imagetyp', newIdx);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (this.imageTypDropdownOpen() && idx >= 0) {
        if (idx === 0) {
          this.updateFilter('imagetyp', '');
        } else {
          this.updateFilter('imagetyp', list[idx - 1]);
        }
        this.imageTypDropdownOpen.set(false);
        this.search();
      } else {
        this.imageTypDropdownOpen.set(!this.imageTypDropdownOpen());
      }
      this.imageTypHighlightedIndex.set(-1);
    } else if (event.key === 'Escape') {
      this.imageTypDropdownOpen.set(false);
      this.imageTypHighlightedIndex.set(-1);
    }
  }

  onObjectKeydown(event: KeyboardEvent) {
    const list = this.filteredObjects();
    const hasAll = !this.objectQuery();
    const total = list.length + (hasAll ? 1 : 0);
    const idx = this.objectHighlightedIndex();

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      this.objectDropdownOpen.set(true);
      const newIdx = idx < total - 1 ? idx + 1 : 0;
      this.objectHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('object', newIdx);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      this.objectDropdownOpen.set(true);
      const newIdx = idx > 0 ? idx - 1 : total - 1;
      this.objectHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('object', newIdx);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (this.objectDropdownOpen() && idx >= 0) {
        const allOffset = hasAll ? 1 : 0;
        if (hasAll && idx === 0) {
          this.objectQuery.set('');
          this.updateFilter('object', '');
        } else {
          const selected = list[idx - allOffset];
          const label = selected.first_alias ?? selected.canonized_name ?? '';
          this.objectQuery.set(label);
          this.updateFilter('object', label);
        }
      } else if (list.length === 1) {
        const label = list[0].first_alias ?? list[0].canonized_name ?? '';
        this.objectQuery.set(label);
        this.updateFilter('object', label);
      }
      this.objectHighlightedIndex.set(-1);
      this.objectDropdownOpen.set(false);
      (event.target as HTMLElement).blur();
      this.search();
    } else if (event.key === 'Escape') {
      this.objectDropdownOpen.set(false);
      this.objectHighlightedIndex.set(-1);
    }
  }

  onObjectFocus() {
    if (this.coneSearchExpanded()) {
      this.coneSearchExpanded.set(false);
    }
    this.otherFieldsFocused.set(true);
    this.objectDropdownOpen.set(true);
  }

  async toggleConeSearch() {
    if (this.coneSearchExpanded()) {
      const wasActive = this.coneRa() != null || this.coneDec() != null || !!this.filters().object;
      this.coneSearchExpanded.set(false);
      if (wasActive) this.search();
    } else {
      const currentObject = this.filters().object ?? null;
      const alreadyHasCoords = this.coneRa() != null || this.coneDec() != null;
      const objectChanged = currentObject !== this._coneObjectKey;
      this.coneSearchExpanded.set(true);
      if (currentObject && (!alreadyHasCoords || objectChanged)) {
        if (objectChanged) { this.coneRa.set(null); this.coneDec.set(null); }
        const match = this.objects().find(
          o => (o.first_alias ?? o.canonized_name) === currentObject || o.canonized_name === currentObject
        );
        if (match?.ra != null && match?.dec != null) {
          this.coneRa.set(match.ra);
          this.coneDec.set(match.dec);
          this._coneObjectKey = currentObject;
        }
      }
      if (currentObject || alreadyHasCoords) this.search();
    }
  }

  onPiKeydown(event: KeyboardEvent) {
    const list = this.filteredPis();
    const hasAll = !this.piQuery();
    const total = list.length + (hasAll ? 1 : 0);
    const idx = this.piHighlightedIndex();

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      this.piDropdownOpen.set(true);
      const newIdx = idx < total - 1 ? idx + 1 : 0;
      this.piHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('pi', newIdx);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      this.piDropdownOpen.set(true);
      const newIdx = idx > 0 ? idx - 1 : total - 1;
      this.piHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('pi', newIdx);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (this.piDropdownOpen() && idx >= 0) {
        const allOffset = hasAll ? 1 : 0;
        if (hasAll && idx === 0) {
          this.piQuery.set('');
          this.updateFilter('pi', '');
        } else {
          const selected = list[idx - allOffset];
          this.piQuery.set(selected);
          this.updateFilter('pi', selected);
        }
      } else if (list.length === 1) {
        this.piQuery.set(list[0]);
        this.updateFilter('pi', list[0]);
      }
      this.piHighlightedIndex.set(-1);
      this.piDropdownOpen.set(false);
      (event.target as HTMLElement).blur();
      this.search();
    } else if (event.key === 'Escape') {
      this.piDropdownOpen.set(false);
      this.piHighlightedIndex.set(-1);
    }
  }

  onSciprogKeydown(event: KeyboardEvent) {
    const list = this.filteredSciprogs();
    const hasAll = !this.sciprogQuery();
    const total = list.length + (hasAll ? 1 : 0);
    const idx = this.sciprogHighlightedIndex();

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      this.sciprogDropdownOpen.set(true);
      const newIdx = idx < total - 1 ? idx + 1 : 0;
      this.sciprogHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('sciprog', newIdx);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      this.sciprogDropdownOpen.set(true);
      const newIdx = idx > 0 ? idx - 1 : total - 1;
      this.sciprogHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('sciprog', newIdx);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (this.sciprogDropdownOpen() && idx >= 0) {
        const allOffset = hasAll ? 1 : 0;
        if (hasAll && idx === 0) {
          this.sciprogQuery.set('');
          this.updateFilter('sciprog', '');
        } else {
          const selected = list[idx - allOffset];
          this.sciprogQuery.set(selected);
          this.updateFilter('sciprog', selected);
        }
      } else if (list.length === 1) {
        this.sciprogQuery.set(list[0]);
        this.updateFilter('sciprog', list[0]);
      }
      this.sciprogHighlightedIndex.set(-1);
      this.sciprogDropdownOpen.set(false);
      (event.target as HTMLElement).blur();
      this.search();
    } else if (event.key === 'Escape') {
      this.sciprogDropdownOpen.set(false);
      this.sciprogHighlightedIndex.set(-1);
    }
  }

  onFilterKeydown(event: KeyboardEvent) {
    const list = this.filteredAvailableFilters();
    const hasAll = !this.filterQuery();
    const total = list.length + (hasAll ? 1 : 0);
    const idx = this.filterHighlightedIndex();

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      this.filterDropdownOpen.set(true);
      const newIdx = idx < total - 1 ? idx + 1 : 0;
      this.filterHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('filter', newIdx);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      this.filterDropdownOpen.set(true);
      const newIdx = idx > 0 ? idx - 1 : total - 1;
      this.filterHighlightedIndex.set(newIdx);
      this.scrollDropdownItem('filter', newIdx);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (this.filterDropdownOpen() && idx >= 0) {
        const allOffset = hasAll ? 1 : 0;
        if (hasAll && idx === 0) {
          this.filterQuery.set('');
          this.filters.update(f => ({ ...f, filter: null }));
        } else {
          const selected = list[idx - allOffset];
          this.filterQuery.set(selected);
          this.filters.update(f => ({ ...f, filter: [selected] }));
        }
      } else if (list.length === 1) {
        this.filterQuery.set(list[0]);
        this.filters.update(f => ({ ...f, filter: [list[0]] }));
      }
      this.filterHighlightedIndex.set(-1);
      this.filterDropdownOpen.set(false);
      (event.target as HTMLElement).blur();
      this.search();
    } else if (event.key === 'Escape') {
      this.filterDropdownOpen.set(false);
      this.filterHighlightedIndex.set(-1);
    }
  }

  onObjectSelected() {
    this.coneRa.set(null);
    this.coneDec.set(null);
    this._coneObjectKey = null;
  }

  clearObjectFilter() {
    this.objectQuery.set('');
    this.updateFilter('object', '');
    this.objectDropdownOpen.set(false);
    this.coneRa.set(null);
    this.coneDec.set(null);
    this._coneObjectKey = null;
  }

  toggleSort(col: string) {
    const current = this.sortExpr();
    if (current?.col !== col) {
      this.sortExpr.set({ col, dir: 1 });
    } else if (current.dir === 1) {
      this.sortExpr.set({ col, dir: -1 });
    } else {
      this.sortExpr.set(null);
    }
    this.search();
  }

  private getSortExpr(): Record<string, 1 | -1> | null {
    const s = this.sortExpr();
    return s ? { [s.col]: s.dir } : null;
  }

  clearFilters() {
    this.filters.set({});
    this.sortExpr.set(null);
    this._coneObjectKey = null;
    this.availableFilters.set([]);
    this.objectQuery.set('');
    this.piQuery.set('');
    this.sciprogQuery.set('');
    this.filterQuery.set('');
    this.coneSearchExpanded.set(false);
    this.dateRangeMode.set('date');
    this.coneRa.set(null);
    this.coneDec.set(null);
    this.coneRadius.set(60);
    this.coneEpoch.set('2000.0');
    this.coneSearchError.set(null);
    this.search();
  }

  resetToHome() {
    this.selectedObsIds.set(new Set());
    this.selectionPageMap.set(new Map());
    this.selectedObservation.set(null);
    this.filesLoading.set(false);
    this.clearFilters();
  }

  expandedLogSections = signal<Record<string, boolean>>({});
  coordMode = signal<'DEG' | 'SX'>('DEG');

  readonly FIELD_DEFS: Record<string, { label: string }> = {
    'TELESCOP':  { label: 'Telescope' },
    'DATE-OBS':  { label: 'Date-Obs' },
    'FILTER':    { label: 'Filter' },
    'EXPTIME':   { label: 'Exp Time' },
    'AIRMASS':   { label: 'Airmass' },
    'PI':        { label: 'PI' },
    'SCIPROG':   { label: 'Sci Prog' },
    'INSTRUME':  { label: 'Instrument' },
    'RA':        { label: 'RA / Dec' },
    'RA_TEL':    { label: 'Telescope RA / Dec' },
    'OBSTYPE':   { label: 'Obs Type' },
    'IMAGETYP':  { label: 'Image Type' },
  };

  private readonly FIELD_ALIASES: Record<string, string> = {
    'DEC': 'RA',
    'DEC_TEL': 'RA_TEL',
  };

  pinnedFields = computed(() => {
    const pinned = new Set(this.ocadbService.viewerConf().pinnedFields);
    if (pinned.has('RA')) pinned.add('DEC');
    if (pinned.has('RA_TEL')) pinned.add('DEC_TEL');
    return pinned;
  });
  fieldOrder = computed(() => this.ocadbService.viewerConf().fieldOrder);
  visibleFields = computed(() => {
    const pinned = this.pinnedFields();
    return this.fieldOrder().filter(k => pinned.has(k) && !this.FIELD_ALIASES[k]);
  });

  dragKey = signal<string | null>(null);
  dragOverKey = signal<string | null>(null);
  dragOverEnd = signal(false);
  dragHandleActive = signal(false);
  private _globalDragOverHandler: ((e: DragEvent) => void) | null = null;
  private _globalDropHandler: ((e: DragEvent) => void) | null = null;

  togglePin(key: string) {
    const canonical = this.FIELD_ALIASES[key] ?? key;
    const conf = this.ocadbService.viewerConf();
    const pinned = new Set(conf.pinnedFields);
    const fieldOrder = [...conf.fieldOrder];
    if (pinned.has(canonical)) {
      pinned.delete(canonical);
    } else {
      pinned.add(canonical);
      if (!fieldOrder.includes(canonical)) fieldOrder.push(canonical);
    }
    this.ocadbService.saveViewerConf({ ...conf, pinnedFields: [...pinned], fieldOrder });
  }

  onDragStart(event: DragEvent, key: string) {
    this.dragKey.set(key);
    event.dataTransfer?.setData('text/plain', key);
    const el = event.currentTarget as HTMLElement;
    const ghost = el.cloneNode(true) as HTMLElement;
    ghost.style.opacity = '0.5';
    ghost.style.position = 'fixed';
    ghost.style.top = '-1000px';
    ghost.style.width = el.offsetWidth + 'px';
    document.body.appendChild(ghost);
    event.dataTransfer?.setDragImage(ghost, event.offsetX, event.offsetY);
    setTimeout(() => document.body.removeChild(ghost), 0);

    this._globalDragOverHandler = (e: DragEvent) => {
      e.preventDefault();
      this._updateDragIndicator(e.clientY);
    };
    this._globalDropHandler = (e: DragEvent) => {
      e.preventDefault();
      this._executeDrop();
    };
    document.addEventListener('dragover', this._globalDragOverHandler);
    document.addEventListener('drop', this._globalDropHandler);
  }

  private _updateDragIndicator(clientY: number) {
    const rows = Array.from(document.querySelectorAll<HTMLElement>('[data-drag-key]'));
    if (!rows.length) return;
    if (clientY > rows[rows.length - 1].getBoundingClientRect().bottom) {
      this.dragOverKey.set(null);
      this.dragOverEnd.set(true);
      return;
    }
    for (const row of rows) {
      if (clientY <= row.getBoundingClientRect().bottom) {
        this.dragOverKey.set(row.dataset['dragKey'] ?? null);
        this.dragOverEnd.set(false);
        return;
      }
    }
  }

  private _executeDrop() {
    const sourceKey = this.dragKey();
    const targetKey = this.dragOverKey();
    const isEnd = this.dragOverEnd();
    this.dragKey.set(null);
    this.dragOverKey.set(null);
    this.dragOverEnd.set(false);
    if (!sourceKey) return;
    const conf = this.ocadbService.viewerConf();
    const order = [...conf.fieldOrder];
    const fromIdx = order.indexOf(sourceKey);
    if (fromIdx === -1) return;
    order.splice(fromIdx, 1);
    if (isEnd) {
      const pinned = new Set(conf.pinnedFields);
      let lastPinnedIdx = -1;
      for (let i = order.length - 1; i >= 0; i--) {
        if (pinned.has(order[i])) { lastPinnedIdx = i; break; }
      }
      order.splice(lastPinnedIdx + 1, 0, sourceKey);
    } else if (targetKey && targetKey !== sourceKey) {
      const toIdx = order.indexOf(targetKey);
      if (toIdx === -1) return;
      order.splice(toIdx, 0, sourceKey);
    } else {
      return;
    }
    this.ocadbService.saveViewerConf({ ...conf, fieldOrder: order });
  }

  onContainerDragOver(event: DragEvent) {
    event.preventDefault();
  }

  onContainerDragLeave(_event: DragEvent) {}

  onContainerDrop(event: DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    this._executeDrop();
  }

  onDragEnd() {
    if (this._globalDragOverHandler) {
      document.removeEventListener('dragover', this._globalDragOverHandler);
      this._globalDragOverHandler = null;
    }
    if (this._globalDropHandler) {
      document.removeEventListener('drop', this._globalDropHandler);
      this._globalDropHandler = null;
    }
    this.dragKey.set(null);
    this.dragOverKey.set(null);
    this.dragOverEnd.set(false);
    this.dragHandleActive.set(false);
  }

  toggleLogEntry(id: number) {
    this.expandedLogEntry.update(current => current === id ? null : id);
    this.expandedLogSections.set({});
  }

  toggleLogSection(section: string) {
    this.expandedLogSections.update(s => ({ ...s, [section]: !s[section] }));
  }

  headerEntries(headers: Record<string, string>): [string, string][] {
    return Object.entries(headers);
  }

  getStatusClass(entry: ApiLogEntry): string {
    if (entry.error) return 'text-red-400';
    if (!entry.status) return 'text-slate-500';
    if (entry.status >= 200 && entry.status < 300) return 'text-emerald-400';
    if (entry.status >= 400 && entry.status < 500) return 'text-amber-400';
    return 'text-red-400';
  }

  getFileCloudStatus(file: FitsFile): 'stored' | 'storing' | 'none' | 'other' {
    const cloud = file?.file_status?.cloud;
    if (!cloud) return 'none';
    if (cloud.status === 'stored' && cloud.ready) return 'stored';
    if (['storing', 'queued', 'scheduled', 'requested'].includes(cloud.status)) return 'storing';
    if (cloud.status === 'not_stored' || cloud.status === 'deleted') return 'none';
    return 'other';
  }

  getFileBadgeClass(file: FitsFile): string {
    return this.getFileBadgeClassByType(file.file_class);
  }

  getFileBadgeClassByType(fileClass: string): string {
    switch (fileClass) {
      case 'zdf': return 'bg-emerald-900/40 text-emerald-300 border-emerald-600/50';
      case 'raw': return 'bg-amber-900/30 text-amber-300 border-amber-600/50';
      default: return 'bg-space-800 text-slate-400 border-slate-600/50';
    }
  }

  getFileLabel(file: FitsFile): string {
    return this.getFileLabelByType(file.file_class);
  }

  getFileLabelByType(fileClass: string): string {
    if (!fileClass) return '?';
    const labels: Record<string, string> = {
      raw: 'RAW', zdf: 'ZDF', master: 'MASTER', source: 'SRC', tmp: 'TMP', test: 'TEST'
    };
    return labels[fileClass] ?? fileClass.toUpperCase();
  }

  async downloadFile(file: FitsFile) {
    this.downloadingFile.set(true);
    const url = await this.ocadbService.fetchPresignedUrl(file.filename);
    this.downloadingFile.set(false);
    if (!url) return;
    const a = document.createElement('a');
    a.href = url;
    a.download = file.filename;
    a.click();
  }

  async openShare(file: FitsFile) {
    this.shareFile.set(file);
    this.shareUrl.set(null);
    this.shareCopied.set(false);
    this.shareLoading.set(true);
    const url = await this.ocadbService.fetchPresignedUrl(file.filename, this.shareExpiry());
    this.shareLoading.set(false);
    this.shareUrl.set(url);
  }

  getCalibDisplayLabel(file: FitsFile): string {
    const parsed = this.getCalibFileLabel(file.filename);
    const imagetyp = (file.fits_header?.['IMAGETYP'] as string | null | undefined)?.toLowerCase();
    if (imagetyp && imagetyp !== 'raw') return imagetyp;
    return parsed;
  }

  getCalibFileLabel(filename: string): string {
    const name = filename.split('/').pop() ?? filename;
    const m = /\w{5}.\d{4}_\d{5}(?:_(\w+))?\.(?:fits|fz)/i.exec(name);
    if (!m) return '—';
    return m[1] ?? 'raw';
  }

  closeShare() {
    this.shareFile.set(null);
    this.shareUrl.set(null);
    this.shareCopied.set(false);
  }

  async regenerateShareUrl() {
    const file = this.shareFile();
    if (!file) return;
    this.shareCopied.set(false);
    this.shareLoading.set(true);
    const url = await this.ocadbService.fetchPresignedUrl(file.filename, this.shareExpiry());
    this.shareLoading.set(false);
    this.shareUrl.set(url);
  }

  async copyShareUrl() {
    const url = this.shareUrl();
    if (!url) return;
    await navigator.clipboard.writeText(url);
    this.shareCopied.set(true);
    setTimeout(() => this.shareCopied.set(false), 2000);
  }

  getStorageStatusClass(status: StorageStatusType, ready: boolean): string {
    if (status === 'stored' && ready) return 'text-emerald-400';
    if (['storing', 'queued', 'scheduled', 'requested'].includes(status)) return 'text-amber-400';
    if (status === 'corrupted') return 'text-red-400';
    return 'text-slate-600';
  }

  calibrationSkeletonNames(obs: Observation): string[] {
    return obs.source_files ?? [];
  }

  private formatSexagesimal(value: number, isRA: boolean): string {
    const total = isRA ? value / 15 : Math.abs(value);
    const sign = (!isRA && value < 0) ? '-' : (isRA ? '' : '+');
    const h = Math.floor(total);
    const mTotal = (total - h) * 60;
    const m = Math.floor(mTotal);
    const s = (mTotal - m) * 60;
    const hStr = String(h).padStart(2, '0');
    const mStr = String(m).padStart(2, '0');
    const sStr = s.toFixed(1).padStart(4, '0');
    return `${sign}${hStr}:${mStr}:${sStr}`;
  }

  formatRA(ra: number | null | undefined): string {
    if (ra == null) return '—';
    return this.coordMode() === 'SX' ? this.formatSexagesimal(ra, true) : ra.toFixed(4);
  }

  formatDec(dec: number | null | undefined): string {
    if (dec == null) return '—';
    return this.coordMode() === 'SX' ? this.formatSexagesimal(dec, false) : dec.toFixed(4);
  }

  getTelescopeColor(telescope: string | null | undefined): string {
    const map: Record<string, string> = { jk15: '#67F4F5', zb08: '#0082E8', wk06: '#14AD4E' };
    return map[telescope?.toLowerCase() ?? ''] ?? '#475569';
  }

  getStorageStatusBgClass(status: StorageStatusType, ready: boolean): string {
    if (status === 'stored' && ready) return 'bg-emerald-400 shadow-[0_0_6px_1px_rgba(52,211,153,0.5)]';
    if (['storing', 'queued', 'scheduled', 'requested'].includes(status)) return 'bg-amber-400 shadow-[0_0_6px_1px_rgba(251,191,36,0.5)]';
    if (status === 'corrupted') return 'bg-red-400 shadow-[0_0_6px_1px_rgba(248,113,113,0.5)]';
    return 'bg-slate-600';
  }

  formatFilesize(bytes: number | null | undefined): string {
    if (bytes == null) return '—';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  sortedFiles(files: FitsFile[]): FitsFile[] {
    const order: Record<string, number> = { zdf: 0, raw: 1 };
    return [...files].sort((a, b) => (order[a.file_class] ?? 2) - (order[b.file_class] ?? 2));
  }

  sortedFileTypes(types: string[]): string[] {
    const order: Record<string, number> = { zdf: 0, raw: 1 };
    return [...types].sort((a, b) => (order[a] ?? 2) - (order[b] ?? 2));
  }

  ocaJd(jd: number | null | undefined): string {
    if (jd == null) return '—';
    return String(Math.floor(jd) % 10000).padStart(4, '0');
  }

  formatOcaJd(val: number | null | undefined): string {
    if (val == null) return '—';
    return String(val).padStart(4, '0');
  }

  hasMetadata(obs: Observation): boolean {
    return obs.metadata != null && Object.keys(obs.metadata).length > 0;
  }

  fitsHeaderEntries(file: FitsFile): [string, any][] {
    if (!file.fits_header) return [];
    return Object.entries(file.fits_header).filter(([, v]) => v != null);
  }

  headerEntries2(header: Record<string, any> | null | undefined): [string, any][] {
    if (!header) return [];
    return Object.entries(header).filter(([, v]) => v != null);
  }

  private async loadDropdowns() {
    const currentTelescope = this.filters().telescop;
    const [telescopes, imageTypes, obsTypes, objects, pis, sciprogs, filterList] = await Promise.all([
      this.ocadbService.fetchValuesList('telescop'),
      this.ocadbService.fetchValuesList('imagetyp'),
      this.ocadbService.fetchValuesList('obstype'),
      this.ocadbService.fetchSearchObjects(),
      this.ocadbService.fetchValuesList('pi'),
      this.ocadbService.fetchValuesList('sciprog'),
      this.ocadbService.fetchTelescopeFilters(currentTelescope || 'all')
    ]);
    this.telescopes.set(telescopes);
    this.imageTypes.set(imageTypes);
    this.obsTypes.set(obsTypes);
    this.objects.set(objects);
    this.pis.set(pis);
    this.sciprogs.set(sciprogs);
    this.availableFilters.set(filterList);
  }

  private sanitizer = inject(DomSanitizer);

  formatJsonHtml(obj: any): SafeHtml {
    return this.sanitizer.bypassSecurityTrustHtml(this._jsonToHtml(obj, 0));
  }

  private _jsonToHtml(obj: any, indent: number): string {
    const pad = '  '.repeat(indent);
    const inner = '  '.repeat(indent + 1);
    if (obj === null) return `<span style="color:#64748b">null</span>`;
    if (typeof obj === 'boolean') return `<span style="color:#a78bfa">${obj}</span>`;
    if (typeof obj === 'number') return `<span style="color:#fbbf24">${obj}</span>`;
    if (typeof obj === 'string') return `<span style="color:#86efac">"${this._escHtml(obj)}"</span>`;
    if (Array.isArray(obj)) {
      if (!obj.length) return `<span style="color:#94a3b8">[]</span>`;
      const items = obj.map(v => `${inner}${this._jsonToHtml(v, indent + 1)}`).join(`<span style="color:#64748b">,</span>\n`);
      return `<span style="color:#94a3b8">[</span>\n${items}\n${pad}<span style="color:#94a3b8">]</span>`;
    }
    if (typeof obj === 'object') {
      const keys = Object.keys(obj);
      if (!keys.length) return `<span style="color:#94a3b8">{}</span>`;
      const items = keys.map(k =>
        `${inner}<span style="color:#38bdf8">"${this._escHtml(k)}"</span><span style="color:#64748b">: </span>${this._jsonToHtml(obj[k], indent + 1)}`
      ).join(`<span style="color:#64748b">,</span>\n`);
      return `<span style="color:#94a3b8">{</span>\n${items}\n${pad}<span style="color:#94a3b8">}</span>`;
    }
    return this._escHtml(String(obj));
  }

  private _escHtml(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
}
