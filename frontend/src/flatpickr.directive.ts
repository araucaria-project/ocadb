import { Directive, ElementRef, Input, Output, EventEmitter, OnInit, OnDestroy, OnChanges, SimpleChanges } from '@angular/core';
import flatpickr from 'flatpickr';
import { Instance } from 'flatpickr/dist/types/instance';

@Directive({
  selector: '[fpickr]',
  standalone: true,
  exportAs: 'fpickr'
})
export class FlatpickrDirective implements OnInit, OnDestroy, OnChanges {
  @Input() fpValue: string | null = null;
  @Input() fpDefaultHour = 0;
  @Input() fpDefaultMinute = 0;
  @Input() fpDefaultSecond = 0;
  @Output() fpChange = new EventEmitter<string>();

  private fp: Instance | null = null;

  constructor(private el: ElementRef<HTMLInputElement>) {}

  ngOnInit() {
    this.fp = flatpickr(this.el.nativeElement as Node, {
      dateFormat: 'Y-m-d H:i:S',
      defaultDate: this.fpValue || undefined,
      enableTime: true,
      enableSeconds: true,
      time_24hr: true,
      defaultHour: this.fpDefaultHour,
      defaultMinute: this.fpDefaultMinute,
      defaultSeconds: this.fpDefaultSecond,
      disableMobile: true,
      appendTo: document.body,
      onChange: (_dates: Date[], dateStr: string) => {
        this.fpChange.emit(dateStr);
      },
      onReady: (_dates, _dateStr, fp) => {
        this.applyMonthDropdownDark(fp);
        this.injectYearDropdown(fp);
      },
      onYearChange: (_dates, _dateStr, fp) => {
        this.syncYearDropdown(fp);
      },
    }) as Instance;
  }

  private applyMonthDropdownDark(fp: Instance) {
    const monthSelect = fp.calendarContainer?.querySelector<HTMLSelectElement>('.flatpickr-monthDropdown-months');
    if (!monthSelect) return;
    monthSelect.style.colorScheme = 'dark';
    monthSelect.style.background = '#1f253d';
    monthSelect.style.color = '#e2e8f0';
    monthSelect.style.border = '1px solid #2d3552';
    monthSelect.style.borderRadius = '4px';
  }

  private injectYearDropdown(fp: Instance) {
    const yearInput = fp.calendarContainer?.querySelector<HTMLInputElement>('.cur-year');
    if (!yearInput) return;

    const select = document.createElement('select');
    select.className = 'cur-year-select';

    const currentYear = fp.currentYear;
    const minYear = 2000;
    const maxYear = new Date().getFullYear() + 1;

    for (let y = maxYear; y >= minYear; y--) {
      const opt = document.createElement('option');
      opt.value = String(y);
      opt.textContent = String(y);
      if (y === currentYear) opt.selected = true;
      select.appendChild(opt);
    }

    select.addEventListener('change', () => {
      fp.changeYear(Number(select.value));
    });

    yearInput.parentNode?.replaceChild(select, yearInput);
  }

  private syncYearDropdown(fp: Instance) {
    const select = fp.calendarContainer?.querySelector<HTMLSelectElement>('.cur-year-select');
    if (select) select.value = String(fp.currentYear);
  }

  ngOnChanges(changes: SimpleChanges) {
    if (this.fp && changes['fpValue']) {
      this.fp.setDate(this.fpValue || '', false);
    }
  }

  open() {
    this.fp?.open();
  }

  ngOnDestroy() {
    this.fp?.destroy();
  }
}
