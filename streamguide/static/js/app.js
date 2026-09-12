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
import * as subs from './views/subs.js';

const routes = { home, discover, search, watchlist, series, abos: subs, people, history, settings };
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

// ---------- Profil ----------
const profileBtn = document.getElementById('profile-btn');
function showProfile(st) {
  window.sgProfile = st.profile || { id: 'main', name: 'Ich', max_age: null, restricted: false, is_main: true };
  profileBtn.textContent = '';
  profileBtn.append('👤 ', st.profile?.name || 'Ich');
  profileBtn.hidden = !(st.profiles && st.profiles.length > 1);
}
profileBtn.addEventListener('click', async () => {
  let d;
  try { d = await api.get('/profiles'); } catch (e) { return toast(e.message, 'err'); }
  const root = document.getElementById('modal-root');
  root.innerHTML = '';
  const close = () => { root.innerHTML = ''; };
  const backdrop = h('div', { class: 'modal-backdrop', onClick: (e) => { if (e.target === backdrop) close(); } });
  const box = h('div', { class: 'modal', style: { width: 'min(420px, 100%)', padding: '22px' } },
    h('h2', { style: { marginBottom: '12px' } }, '👤 Profil wechseln'),
    h('div', { class: 'profile-list' }, ...d.profiles.map((p) => h('button', { class: `profile-row ${p.id === d.current ? 'active' : ''}`, onClick: async () => {
      if (p.id === d.current) return close();
      let pin = null;
      if (p.id === 'main' && d.pin_required) { pin = window.prompt('PIN für das Hauptprofil:'); if (pin === null) return; }
      try { await api.post('/profiles/switch', { id: p.id, pin }); location.reload(); } catch (e) { toast(e.message, 'err'); }
    } }, h('span', { class: 'av' }, p.id === 'main' ? '👑' : '🙂'), h('span', { class: 'grow' }, p.name, p.max_age != null ? h('div', { class: 'muted small' }, `Inhalte bis ${p.max_age} Jahre`) : null), p.id === d.current ? h('span', {}, '✓') : null))),
    h('div', { class: 'row', style: { marginTop: '14px', justifyContent: 'flex-end' } }, h('button', { class: 'btn', onClick: close }, 'Schließen')));
  backdrop.append(box);
  root.append(backdrop);
});

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
    showProfile(st);
    if (!st.has_key && parseHash().route !== 'settings') {
      location.hash = '#/settings?welcome=1';
    }
  } catch { /* Server noch nicht bereit */ }
  render();
  pollJobs();
})();
