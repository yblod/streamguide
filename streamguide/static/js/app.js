// Einstieg: Router, Theme, Job-Anzeige.
import { api } from './api.js';
import { h, toast } from './ui.js';
import * as home from './views/home.js';
import * as discover from './views/discover.js';
import * as search from './views/search.js';
import * as watchlist from './views/watchlist.js';
import * as series from './views/series.js';
import * as people from './views/people.js';
import * as history from './views/history.js';
import * as settings from './views/settings.js';

const routes = { home, discover, search, watchlist, series, people, history, settings };
const app = document.getElementById('app');
let current = null;

// ---------- Theme ----------
function applyTheme(t) {
  const theme = t || localStorage.getItem('theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('theme', theme);
}
document.getElementById('theme-toggle').addEventListener('click', () => {
  applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
});
applyTheme();

// ---------- Router ----------
export function parseHash() {
  const hash = location.hash.replace(/^#\/?/, '');
  const [path, qs] = hash.split('?');
  return { route: path || 'home', params: Object.fromEntries(new URLSearchParams(qs || '')) };
}

async function render() {
  const { route, params } = parseHash();
  const view = routes[route] || home;
  document.querySelectorAll('#nav a').forEach((a) => a.classList.toggle('active', a.dataset.route === (routes[route] ? route : 'home')));
  if (current?.destroy) current.destroy();
  app.innerHTML = '';
  window.scrollTo({ top: 0 });
  try {
    current = await view.render(app, params);
  } catch (e) {
    app.append(h('div', { class: 'glass panel' }, h('h2', {}, 'Fehler'), h('p', { class: 'muted' }, e.message)));
  }
}
window.addEventListener('hashchange', render);

// ---------- Jobs (Fortschritt unten rechts) ----------
const jobRoot = document.getElementById('job-root');
const known = new Map();
let pollTimer = null;

async function pollJobs() {
  try {
    const { running, recent } = await api.jobs();
    jobRoot.innerHTML = '';
    for (const j of running) {
      known.set(j.id, 'running');
      const pct = j.total ? Math.round((j.progress / j.total) * 100) : null;
      jobRoot.append(h('div', { class: 'job' },
        h('div', { class: 'k' }, h('span', {}, JOB_LABEL[j.kind] || j.kind), h('button', { class: 'btn sm ghost', style: { padding: '0 6px' }, title: 'Abbrechen', onClick: () => api.cancelJob(j.id) }, '✕')),
        h('div', { class: 'muted' }, j.message || '…'),
        h('div', { class: 'progress' }, h('div', { style: { width: (pct ?? 30) + '%' } })),
      ));
    }
    for (const j of recent) {
      if (known.get(j.id) === 'running' && j.status !== 'running') {
        known.set(j.id, j.status);
        toast(`${JOB_LABEL[j.kind] || j.kind}: ${j.message}`, j.status === 'done' ? 'ok' : 'err');
        window.dispatchEvent(new CustomEvent('job-finished', { detail: j }));
      }
    }
    clearTimeout(pollTimer);
    pollTimer = setTimeout(pollJobs, running.length ? 1500 : 8000);
  } catch {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(pollJobs, 10000);
  }
}
export const JOB_LABEL = {
  import_imdb: 'IMDb-Import', import_list: 'Listen-Import', import_people: 'Schauspieler-Import', imdb_dataset: 'IMDb-Bewertungen',
  refresh_library: 'Bibliothek aktualisieren', tmdb_sync: 'TMDB-Sync',
};
export function watchJobs() { clearTimeout(pollTimer); pollJobs(); }

// ---------- Start ----------
(async () => {
  try {
    const st = await api.status();
    if (!st.has_key && parseHash().route !== 'settings') {
      location.hash = '#/settings?welcome=1';
    }
  } catch { /* Server noch nicht bereit */ }
  render();
  pollJobs();
})();
