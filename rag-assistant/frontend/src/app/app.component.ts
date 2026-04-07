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
        <a routerLink="/chat"   routerLinkActive="active">Chat</a>
      </div>
    </nav>
    <main class="main-content">
      <router-outlet />
    </main>
  `,
  styles: [`
    :host { display: flex; flex-direction: column; height: 100vh; }

    .navbar {
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 2rem; height: 56px;
      background: #0f172a; color: #fff;
      flex-shrink: 0;
    }
    .brand { font-weight: 600; font-size: 1.1rem; letter-spacing: 0.5px; }
    .nav-links { display: flex; gap: 1.5rem; }
    .nav-links a { color: #94a3b8; text-decoration: none; font-size: 0.9rem; transition: color 0.2s; }
    .nav-links a:hover, .nav-links a.active { color: #fff; }

    .main-content {
      flex: 1; overflow: hidden;
      padding: 1rem 1.5rem;
      max-width: 1200px; width: 100%; margin: 0 auto; box-sizing: border-box;
    }
  `],
})
export class AppComponent {}
