import { Component, ElementRef, Input, Renderer2, ViewChild } from '@angular/core';

@Component({
  selector: 'app-info-icon',
  standalone: true,
  template: `
    <span class="group relative inline-flex items-center ml-1 align-middle normal-case tracking-normal" (mouseenter)="position()">
      <svg class="w-3 h-3 text-slate-600 hover:text-slate-400 transition-colors cursor-help" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
        <path stroke-linecap="round" stroke-linejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
      </svg>
      <span #tooltip class="pointer-events-none absolute left-1/2 bottom-full mb-1.5 w-max max-w-[220px] rounded bg-space-700 border border-space-600 px-2 py-1 text-[10px] font-normal text-slate-200 opacity-0 group-hover:opacity-100 transition-opacity z-30 shadow-lg text-center" style="transform: translateX(-50%);">
        {{ text }}
      </span>
    </span>
  `
})
export class InfoIconComponent {
  @Input() text = '';
  @ViewChild('tooltip') tooltipRef!: ElementRef<HTMLElement>;

  constructor(private renderer: Renderer2, private hostRef: ElementRef<HTMLElement>) {}

  position(): void {
    const el = this.tooltipRef.nativeElement;
    const margin = 8;

    // Reset to the default position (centered, above the icon) before measuring.
    this.renderer.removeClass(el, 'top-full');
    this.renderer.removeClass(el, 'mt-1.5');
    this.renderer.addClass(el, 'bottom-full');
    this.renderer.addClass(el, 'mb-1.5');
    this.renderer.setStyle(el, 'transform', 'translateX(-50%)');

    const rect = el.getBoundingClientRect();
    const clipTop = this.nearestScrollAncestorTop();

    if (rect.top < clipTop + margin) {
      // Not enough room above — flip below the icon instead.
      this.renderer.removeClass(el, 'bottom-full');
      this.renderer.removeClass(el, 'mb-1.5');
      this.renderer.addClass(el, 'top-full');
      this.renderer.addClass(el, 'mt-1.5');
    }

    const hRect = el.getBoundingClientRect();
    const overflowLeft = margin - hRect.left;
    const overflowRight = hRect.right - (window.innerWidth - margin);

    if (overflowLeft > 0) {
      this.renderer.setStyle(el, 'transform', `translateX(calc(-50% + ${overflowLeft}px))`);
    } else if (overflowRight > 0) {
      this.renderer.setStyle(el, 'transform', `translateX(calc(-50% - ${overflowRight}px))`);
    }
  }

  private nearestScrollAncestorTop(): number {
    let node: HTMLElement | null = this.hostRef.nativeElement.parentElement;
    while (node) {
      const overflowY = window.getComputedStyle(node).overflowY;
      if (overflowY === 'auto' || overflowY === 'scroll' || overflowY === 'hidden' || overflowY === 'clip') {
        return node.getBoundingClientRect().top;
      }
      node = node.parentElement;
    }
    return 0;
  }
}
