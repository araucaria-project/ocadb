import { AfterViewInit, Directive, ElementRef, inject } from '@angular/core';

/** Focuses the element when it is rendered. The native `autofocus` attribute only
 * works on page load, not for elements added later (e.g. the next login step). */
@Directive({
  selector: '[appAutofocus]',
  standalone: true
})
export class AutofocusDirective implements AfterViewInit {
  private el = inject(ElementRef<HTMLElement>);

  ngAfterViewInit() {
    this.el.nativeElement.focus();
  }
}
