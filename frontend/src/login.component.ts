import { Component, OnDestroy, OnInit, computed, inject, input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer } from '@angular/platform-browser';
import { OcadbService } from './services/ocadb.service';
import { LoginLink } from './login-link';
import { AutofocusDirective } from './autofocus.directive';
import { LoginMethod, lastIdentifier, preferredLoginMethod, readStorage, rememberLoginMethod, setLastIdentifier, writeStorage } from './login-methods';
import { environment } from './environments/environment';

type LoginStep = 'identifier' | 'password' | 'code' | 'link';

const REMEMBER_DEVICE_KEY = 'ocadb_remember_device';
const RESEND_COOLDOWN_SECONDS = 60;

/** Identifier-first login: Araucaria ID or email, then password or an emailed code. */
@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, AutofocusDirective],
  templateUrl: './login.component.html'
})
export class LoginComponent implements OnInit, OnDestroy {
  ocadbService = inject(OcadbService);

  /** Set when the app was opened from the link in a code email. */
  pendingLink = input<LoginLink | null>(null);

  readonly adminEmail = environment.adminEmail;

  private static readonly BACKGROUNDS = Array.from({length: 23}, (_, i) => `/${i + 1}b.JPG`);
  background = inject(DomSanitizer).bypassSecurityTrustStyle(
    `url(${LoginComponent.BACKGROUNDS[Math.floor(Math.random() * LoginComponent.BACKGROUNDS.length)]})`
  );

  step = signal<LoginStep>('identifier');
  identifier = signal('');
  password = '';
  code = '';
  remember = readStorage(REMEMBER_DEVICE_KEY) === 'true';
  resendIn = signal(0);
  private resendTimer: ReturnType<typeof setInterval> | null = null;

  preferredMethod = computed(() => preferredLoginMethod(this.identifier()));

  ngOnInit() {
    const link = this.pendingLink();
    if (link) {
      this.identifier.set(link.identifier);
      this.code = link.code;
      this.step.set('link');
      return;
    }
    const known = this.ocadbService.sessionExpiredUser() ?? lastIdentifier();
    if (known) {
      this.identifier.set(known);
      // Code users stay on screen 1 (prefilled): opening the page must not send an email.
      if (this.preferredMethod() === 'password') this.step.set('password');
    }
  }

  ngOnDestroy() {
    this.stopResendTimer();
  }

  /** Screen 1 -> 2: an emailed code, unless this browser last used a password for this identifier. */
  async submitIdentifier(event: Event) {
    event.preventDefault();
    const identifier = this.identifier().trim();
    if (!identifier) return;
    this.identifier.set(identifier);
    this.ocadbService.clearError();
    if (this.preferredMethod() === 'password') {
      this.step.set('password');
    } else {
      await this.requestCode();
    }
  }

  async submitPassword(event: Event) {
    event.preventDefault();
    this.saveRememberDevice();
    if (await this.ocadbService.login(this.identifier(), this.password, this.remember)) {
      this.finish('password');
    }
  }

  async requestCode() {
    if (this.resendIn() > 0) return;
    const returnTo = window.location.pathname + window.location.search;
    if (await this.ocadbService.requestLoginCode(this.identifier(), returnTo)) {
      this.code = '';
      this.step.set('code');
      this.startResendTimer();
    }
  }

  async submitCode(event: Event) {
    event.preventDefault();
    this.saveRememberDevice();
    const code = this.code.replace(/\s/g, '');
    if (await this.ocadbService.verifyLoginCode(this.identifier(), code, this.remember)) {
      this.finish('code');
    }
  }

  usePassword() {
    this.ocadbService.clearError();
    this.password = '';
    this.step.set('password');
  }

  changeIdentifier() {
    this.ocadbService.clearError();
    this.password = '';
    this.code = '';
    this.step.set('identifier');
  }

  private finish(method: LoginMethod) {
    // currentUser is the Araucaria ID by now, also when an email was typed.
    rememberLoginMethod([this.identifier(), this.ocadbService.currentUser()], method);
    setLastIdentifier(this.identifier());
    this.password = '';
    this.code = '';
  }

  private saveRememberDevice() {
    writeStorage(REMEMBER_DEVICE_KEY, String(this.remember));
  }

  private startResendTimer() {
    this.stopResendTimer();
    this.resendIn.set(RESEND_COOLDOWN_SECONDS);
    this.resendTimer = setInterval(() => {
      this.resendIn.update(s => s - 1);
      if (this.resendIn() <= 0) this.stopResendTimer();
    }, 1000);
  }

  private stopResendTimer() {
    if (this.resendTimer) clearInterval(this.resendTimer);
    this.resendTimer = null;
  }
}
