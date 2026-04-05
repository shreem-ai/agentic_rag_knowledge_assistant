import { Component } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: `
    <nav class="navbar">
      <span class="brand">RAG Assistant</span>
      <div class="nav-links">
        <a routerLink="/upload" routerLinkActive="active">Upload</a>
        <a routerLink="/chat" routerLinkActive="active">Chat</a>
      </div>
    </nav>
    <main class="main-content">
      <router-outlet />
    </main>
  `,
  styles: [`
    .navbar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 2rem;
      height: 56px;
      background: #0f172a;
      color: #fff;
    }
    .brand { font-weight: 600; font-size: 1.1rem; letter-spacing: 0.5px; }
    .nav-links { display: flex; gap: 1.5rem; }
    .nav-links a { color: #94a3b8; text-decoration: none; font-size: 0.9rem; transition: color 0.2s; }
    .nav-links a:hover, .nav-links a.active { color: #fff; }
    .main-content { max-width: 1100px; margin: 0 auto; padding: 2rem 1rem; }
  `],
})
export class AppComponent {}
