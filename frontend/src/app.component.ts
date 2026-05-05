import { Component, signal, inject, OnInit, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { OcadbService, Observation, SearchFilters, FitsFile, StorageStatusType } from './services/ocadb.service';
import { ApiLogService, ApiLogEntry } from './services/api-log.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html'
})
export class AppComponent implements OnInit {
  ocadbService = inject(OcadbService);
  apiLog = inject(ApiLogService);

  loginData = { username: '', password: '' };

  displayedObservations = signal<Observation[]>([]);
  hasSearched = signal(false);
  selectedFile = signal<FitsFile | null>(null);
  downloadingFile = signal(false);
  shareFile = signal<FitsFile | null>(null);
  shareUrl = signal<string | null>(null);
  shareExpiry = signal<number>(3600);
  shareLoading = signal(false);
  shareCopied = signal(false);
  selectedMetadata = signal<{ obs_name: string; metadata: Record<string, any> } | null>(null);
  selectedObservation = signal<Observation | null>(null);
  showFilters = signal(true);
  showDebugPanel = signal(false);
  selectedObsIds = signal<Set<string>>(new Set());
  scriptLoading = signal(false);
  showDownloadDialog = signal(false);
  downloadForCurrentUser = signal(true);
  downloadCustomUsername = signal('');
  expandedLogEntry = signal<number | null>(null);
  editingPage = signal(false);
  pageInputValue = signal('');
  @ViewChild('pageInput') pageInputRef?: ElementRef<HTMLInputElement>;

  filters = signal<SearchFilters>({});

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

  ngOnInit() {
    if (this.ocadbService.isAuthenticated()) {
      this.loadDropdowns();
      this.search();
    }
  }

  async handleLogin(event: Event) {
    event.preventDefault();
    const success = await this.ocadbService.login(this.loginData.username, this.loginData.password);
    if (success) {
      this.loadDropdowns();
      this.search();
    }
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

    this.updateFilter(key, formatted.length === 10 ? formatted : null);
  }

  updateFilterArray(key: keyof SearchFilters, value: string) {
    const items = value ? value.split(',').map(s => s.trim()).filter(Boolean) : null;
    this.filters.update(f => ({ ...f, [key]: items }));
  }

  async onTelescopeChange(telescope: string) {
    this.updateFilter('telescop', telescope);
    if (telescope) {
      const filters = await this.ocadbService.fetchTelescopeFilters(telescope);
      this.availableFilters.set(filters);
    } else {
      this.availableFilters.set([]);
    }
  }

  async search() {
    if (!this.ocadbService.isAuthenticated()) return;

    const hasRa = this.coneRa() != null;
    const hasDec = this.coneDec() != null;
    if (hasRa !== hasDec) {
      this.coneSearchError.set('Both RA and Dec are required for cone search.');
      return;
    }
    this.coneSearchError.set(null);

    const cone_search = (hasRa && hasDec) ? {
      ra: this.coneRa()!,
      dec: this.coneDec()!,
      arc_seconds: this.coneRadius(),
      epoch: this.coneEpoch() || '2000.0'
    } : null;

    this.hasSearched.set(true);
    this.showFilters.set(false);
    this.ocadbService.pagination.update(p => ({ ...p, page: 1 }));
    const results = await this.ocadbService.searchObservations({ ...this.filters(), cone_search }, 1);
    this.displayedObservations.set(results);
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
    const results = await this.ocadbService.searchObservations(this.filters(), page);
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
    this.selectedObsIds.update(set => {
      const next = new Set(set);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  allOnPageSelected(): boolean {
    const obs = this.displayedObservations();
    return obs.length > 0 && obs.every(o => o._id && this.selectedObsIds().has(o._id));
  }

  toggleSelectAll() {
    const ids = this.displayedObservations().map(o => o._id).filter((id): id is string => !!id);
    const allSelected = ids.every(id => this.selectedObsIds().has(id));
    this.selectedObsIds.update(set => {
      const next = new Set(set);
      if (allSelected) ids.forEach(id => next.delete(id));
      else ids.forEach(id => next.add(id));
      return next;
    });
  }

  clearSelection() {
    this.selectedObsIds.set(new Set());
  }

  openDownloadDialog() {
    this.downloadForCurrentUser.set(true);
    this.downloadCustomUsername.set('');
    this.showDownloadDialog.set(true);
  }

  async executeDownloadScript() {
    const ids = [...this.selectedObsIds()];
    if (!ids.length) return;
    const username = this.downloadForCurrentUser()
      ? (this.ocadbService.currentUser() ?? undefined)
      : this.downloadCustomUsername().trim() || undefined;
    this.scriptLoading.set(true);
    this.showDownloadDialog.set(false);
    await this.ocadbService.downloadScript(ids, username);
    this.scriptLoading.set(false);
  }

  clearFilters() {
    this.filters.set({});
    this.availableFilters.set([]);
    this.coneRa.set(null);
    this.coneDec.set(null);
    this.coneRadius.set(60);
    this.coneEpoch.set('2000.0');
    this.coneSearchError.set(null);
    this.search();
  }

  resetToHome() {
    this.selectedObsIds.set(new Set());
    this.selectedObservation.set(null);
    this.clearFilters();
  }

  expandedLogSections = signal<Record<string, boolean>>({});

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
    switch (file.file_class) {
      case 'zdf': return 'bg-emerald-900/40 text-emerald-300 border-emerald-600/50';
      case 'raw': return 'bg-amber-900/30 text-amber-300 border-amber-600/50';
      default: return 'bg-space-800 text-slate-400 border-slate-600/50';
    }
  }

  getFileLabel(file: FitsFile): string {
    const labels: Record<string, string> = {
      raw: 'RAW', zdf: 'ZDF', master: 'MASTER', source: 'SRC', tmp: 'TMP', test: 'TEST'
    };
    return labels[file.file_class] ?? file.file_class.toUpperCase();
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

  ocaJd(jd: number | null | undefined): string {
    if (jd == null) return '—';
    return String(Math.floor(jd) % 10000).padStart(4, '0');
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
    const [telescopes, imageTypes, obsTypes] = await Promise.all([
      this.ocadbService.fetchValuesList('telescop'),
      this.ocadbService.fetchValuesList('imagetyp'),
      this.ocadbService.fetchValuesList('obstype')
    ]);
    this.telescopes.set(telescopes);
    this.imageTypes.set(imageTypes);
    this.obsTypes.set(obsTypes);
  }
}
