import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-info-icon',
  standalone: true,
  template: `
    <span class="group relative inline-flex items-center ml-1 align-middle normal-case tracking-normal">
      <svg class="w-3 h-3 text-slate-600 hover:text-slate-400 transition-colors cursor-help" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <path stroke-linecap="round" stroke-linejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
      </svg>
      <span class="pointer-events-none absolute left-1/2 bottom-full -translate-x-1/2 mb-1.5 w-max max-w-[220px] rounded bg-space-700 border border-space-600 px-2 py-1 text-[10px] font-normal text-slate-200 opacity-0 group-hover:opacity-100 transition-opacity z-30 shadow-lg text-center">
        {{ text }}
      </span>
    </span>
  `
})
export class InfoIconComponent {
  @Input() text = '';
}
