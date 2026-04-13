import { Component, signal, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { OcadbService, Observation, SearchFilters } from './services/ocadb.service';
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

  observations = signal<Observation[]>([]);
  displayedObservations = signal<Observation[]>([]);
  hasSearched = signal(false);
  showFilters = signal(true);
  showDebugPanel = signal(true);
  expandedLogEntry = signal<number | null>(null);

  filters = signal<SearchFilters>({});

  // Available values for dropdowns (loaded from API)
  telescopes = signal<string[]>([]);
  imageTypes = signal<string[]>([]);
  obsTypes = signal<string[]>([]);
  availableFilters = signal<string[]>([]);

  ngOnInit() {
    if (this.ocadbService.isAuthenticated()) {
      this.loadDropdowns();
    }
  }

  async handleLogin(event: Event) {
    event.preventDefault();
    const success = await this.ocadbService.login(this.loginData.username, this.loginData.password);
    if (success) {
      this.loadDropdowns();
    }
  }

  handleLogout() {
    this.ocadbService.logout();
    this.loginData = { username: '', password: '' };
    this.observations.set([]);
    this.displayedObservations.set([]);
  }

  updateFilter(key: keyof SearchFilters, value: any) {
    this.filters.update(f => ({ ...f, [key]: value || null }));
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
    this.hasSearched.set(true);
    this.showFilters.set(false);
    const results = await this.ocadbService.searchObservations(this.filters());
    this.observations.set(results);
    this.ocadbService.pagination.update(p => ({ ...p, page: 1 }));
    this.updateDisplayedPage();
  }

  // Client-side paging over fetched results
  updateDisplayedPage() {
    const pag = this.ocadbService.pagination();
    const start = (pag.page - 1) * pag.pageSize;
    const end = start + pag.pageSize;
    this.displayedObservations.set(this.observations().slice(start, end));
  }

  get totalPages(): number {
    const pag = this.ocadbService.pagination();
    return Math.max(1, Math.ceil(this.observations().length / pag.pageSize));
  }

  goToPage(page: number) {
    if (page < 1 || page > this.totalPages) return;
    this.ocadbService.pagination.update(p => ({ ...p, page }));
    this.updateDisplayedPage();
  }

  clearFilters() {
    this.filters.set({});
    this.availableFilters.set([]);
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

  getFileCloudStatus(file: any): 'stored' | 'storing' | 'none' | 'other' {
    const cloud = file?.file_status?.cloud;
    if (!cloud) return 'none';
    if (cloud.status === 'stored' && cloud.ready) return 'stored';
    if (['storing', 'queued', 'scheduled', 'requested'].includes(cloud.status)) return 'storing';
    if (cloud.status === 'not_stored' || cloud.status === 'deleted') return 'none';
    return 'other';
  }

  getFileBadgeClass(file: any): string {
    const status = this.getFileCloudStatus(file);
    switch (status) {
      case 'stored': return 'bg-emerald-900/40 text-emerald-300 border-emerald-600/50';
      case 'storing': return 'bg-amber-900/30 text-amber-300 border-amber-600/50';
      case 'none': return 'bg-transparent text-slate-500 border-slate-600/50';
      default: return 'bg-space-800 text-slate-400 border-slate-600/50';
    }
  }

  getFileLabel(file: any): string {
    const fc = file?.file_class;
    if (!fc) return '?';
    const labels: Record<string, string> = {
      raw: 'RAW', zdf: 'ZDF', master: 'MASTER', source: 'SRC', tmp: 'TMP', test: 'TEST'
    };
    return labels[fc] ?? fc.toUpperCase();
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
