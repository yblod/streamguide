// Wiederverwendbare UI-Bausteine: Karten, Raster, Toasts, Titel-Modal.
import { api, IMG } from './api.js';

export const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
};

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ---------- Toast ----------
export function toast(msg, kind = '') {
  const root = document.getElementById('toast-root');
  const el = h('div', { class: `toast ${kind}` }, msg);
  root.append(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; setTimeout(() => el.remove(), 320); }, kind === 'err' ? 5000 : 2600);
}

export const STATUS_LABEL = { watchlist: '🔖 Watchlist', watching: '📺 Verfolgen', watched: '✓ Gesehen', disliked: '✕ Kein Interesse', dropped: '⏸ Abgebrochen' };
export const MODE_LABEL = { sub: 'Im Abo', free: 'Kostenlos', other_sub: 'Anderes Abo', rent: 'Leihen/Kaufen', none: 'Nicht verfügbar' };

// Zusatzländer (Angebote per VPN). Kennzeichnung über ein Kürzel-Badge statt Flaggen-Emoji, weil Windows keine
// Flaggen darstellt (dort erschienen nur die Buchstaben).
export const REGION_NAME = {
  DE: 'Deutschland', GB: 'Großbritannien', US: 'USA', AT: 'Österreich', CH: 'Schweiz', FR: 'Frankreich',
  IT: 'Italien', ES: 'Spanien', NL: 'Niederlande', SE: 'Schweden', DK: 'Dänemark',
};
export const regionName = (r) => REGION_NAME[r] || r;
export const regionBadge = (r, cls = '') => h('span', { class: `flag ${cls}`, title: `${regionName(r)} – per VPN` }, r);
// Anbieter-Logo mit Länder-Badge, wenn das Angebot aus einem Zusatzland (VPN) stammt
export const provLogo = (p, cls = '', titleSuffix = '') => h('span', { class: `prov ${cls} ${p.region ? 'abroad' : ''}`, title: `${p.name}${p.region ? ` (${regionName(p.region)}, per VPN)` : ''}${titleSuffix}` },
  h('img', { src: IMG(p.logo, 'w92'), alt: p.name }), p.region ? regionBadge(p.region) : null);

// ---------- Karte ----------
export function card(t, opts = {}) {
  const av = t.availability || {};
  const provs = [...(av.sub || []), ...(av.free || [])].slice(0, 3);
  const dim = provs.length ? [] : [...(av.other_sub || []), ...(av.other_free || [])].slice(0, 2);
  const u = t.user || {};
  const el = h('div', { class: `card ${provs.length || dim.length ? 'has-provs' : ''} ${opts.noQuick ? '' : 'has-quick'}`, title: t.title, onClick: () => openTitle(t.media_type, t.tmdb_id, opts.onChange) },
    t.poster_path ? h('img', { src: IMG(t.poster_path), loading: 'lazy', alt: '' }) : h('div', { class: 'noposter' }, t.media_type === 'tv' ? '📺' : '🎬'),
    h('div', { class: 'badges' },
      t.imdb_rating ? h('span', { class: 'badge-imdb' }, `★ ${t.imdb_rating.toFixed(1)}`) : (t.tmdb_rating ? h('span', { class: 'badge-status', style: { background: '#01b4e4', color: '#fff' } }, `${t.tmdb_rating.toFixed(1)}`) : h('span')),
      u.newly_available ? h('span', { class: 'badge-new avail' }, 'JETZT VERFÜGBAR')
        : u.new_season_flag ? h('span', { class: 'badge-new' }, u.new_kind === 'season' ? 'NEUE STAFFEL' : 'NEUE FOLGEN')
        : (u.status ? h('span', { class: `badge-status ${u.status}` }, u.status === 'watched' && u.rating ? `✓ ${u.rating}` : STATUS_LABEL[u.status].split(' ')[0]) : null),
    ),
    h('div', { class: 'overlay' }, h('div', { class: 't' }, t.title),
      h('div', { class: 'y' }, opts.showPeople && t.people?.length ? `${t.people.map((p) => p.name).join(', ')}${t.date ? ' · ' + t.date.slice(0, 4) : ''}` : [t.year, t.media_type === 'tv' ? 'Serie' : null].filter(Boolean).join(' · '))),
    av.mode ? h('span', { class: `mode-dot mode-${av.mode}`, title: MODE_LABEL[av.mode] }) : null,
    opts.noQuick ? null : h('div', { class: 'quick' },
      t.media_type === 'tv'
        ? h('button', { class: `q ${u.status === 'watching' ? 'on' : ''}`, title: u.status === 'watching' ? 'Nicht mehr verfolgen' : 'Serie verfolgen', onClick: (e) => { e.stopPropagation(); quick(t, u.status === 'watching' ? null : 'watching', opts); } }, '📺')
        : h('button', { class: `q ${u.status === 'watchlist' ? 'on' : ''}`, title: u.status === 'watchlist' ? 'Von der Watchlist entfernen' : 'Auf die Watchlist', onClick: (e) => { e.stopPropagation(); quick(t, u.status === 'watchlist' ? null : 'watchlist', opts); } }, '🔖'),
      h('button', { class: `q danger ${u.status === 'disliked' ? 'on' : ''}`, title: u.status === 'disliked' ? 'Kein Interesse zurücknehmen' : 'Kein Interesse', onClick: (e) => { e.stopPropagation(); quick(t, u.status === 'disliked' ? null : 'disliked', opts); } }, '✕')),
    (provs.length || dim.length) ? h('div', { class: 'provs' },
      ...provs.map((p) => provLogo(p)),
      ...dim.map((p) => provLogo(p, 'dim', ' – nicht aktiv'))) : null,
  );
  return el;
}

async function quick(t, status, opts) {
  try {
    const updated = status ? await api.setStatus(t.media_type, t.tmdb_id, status) : await api.removeEntry(t.media_type, t.tmdb_id);
    toast(status ? `${t.title}: ${STATUS_LABEL[status]}` : `${t.title}: zurückgenommen`, 'ok');
    if (opts.onChange) opts.onChange(updated);
  } catch (e) { toast(e.message, 'err'); }
}

export function grid(items, opts = {}) {
  if (!items.length) return empty(opts.emptyText || 'Nichts gefunden.', opts.emptyIcon);
  return h('div', { class: 'grid' }, ...items.map((t) => card(t, opts)));
}

export function hrow(items, opts = {}) {
  return h('div', { class: 'hrow' }, ...items.map((t) => card(t, opts)));
}

export function skeletons(n = 12) {
  return h('div', { class: 'grid' }, ...Array.from({ length: n }, () => h('div', { class: 'skeleton' })));
}

export function empty(text, icon = '🍿') {
  return h('div', { class: 'empty' }, h('div', { class: 'big' }, icon), h('div', {}, text));
}

export function section(title, content, extra) {
  return h('section', { class: 'section' },
    h('div', { class: 'row spread', style: { marginBottom: '10px' } }, h('h2', {}, title), extra || null),
    content);
}

export function providerLogos(list, cls = '') {
  return h('span', { class: `provs ${cls}`, style: { position: 'static', display: 'inline-flex' } },
    ...list.map((p) => provLogo(p)));
}

export function fmtRuntime(min) {
  if (!min) return null;
  const hh = Math.floor(min / 60), mm = min % 60;
  return hh ? `${hh} Std ${mm ? mm + ' Min' : ''}`.trim() : `${mm} Min`;
}

export function fmtDate(s) {
  if (!s) return '';
  const d = new Date(s);
  return isNaN(d) ? s : d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

// ---------- Modal-Stapel: Titel ↔ Person, mit „Zurück“ und „Schließen“ ----------
const stack = [];          // Einträge: { kind: 'title'|'person', ..., changed, last, onChange }
let modalEl = null;        // gemeinsamer .modal-Container
let modalState = null;     // oberster Eintrag
let onKeyHandler = null;
let favSet = null;         // Favoriten-Schauspieler (IDs), lazy geladen

export async function loadFavSet(force = false) {
  if (favSet && !force) return favSet;
  try { favSet = new Set((await api.peopleFavorites()).results.map((p) => p.id)); } catch { favSet = favSet || new Set(); }
  return favSet;
}
export function markFavorite(id, on) { if (!favSet) favSet = new Set(); if (on) favSet.add(id); else favSet.delete(id); }

function ensureRoot() {
  if (modalEl) return modalEl;
  const root = document.getElementById('modal-root');
  root.innerHTML = '';
  const backdrop = h('div', { class: 'modal-backdrop', onClick: (e) => { if (e.target === backdrop) closeModal(); } });
  modalEl = h('div', { class: 'modal' });
  backdrop.append(modalEl);
  root.append(backdrop);
  document.body.style.overflow = 'hidden';
  onKeyHandler = (e) => { if (e.key === 'Escape') backModal(); };
  document.addEventListener('keydown', onKeyHandler);
  return modalEl;
}

function showSpinner() {
  modalEl.innerHTML = '';
  modalEl.append(h('div', { style: { padding: '60px', textAlign: 'center' } }, h('span', { class: 'spinner' })));
  if (modalEl.parentElement) modalEl.parentElement.scrollTop = 0;
}

function showError(e) {
  modalEl.innerHTML = '';
  modalEl.append(h('div', { class: 'panel' }, h('p', { class: 'muted' }, `Fehler: ${e.message}`),
    h('div', { class: 'row' }, stack.length > 1 ? h('button', { class: 'btn', onClick: backModal }, '← Zurück') : null, h('button', { class: 'btn', onClick: closeModal }, 'Schließen'))));
}

function navButtons() {
  return h('div', { class: 'modal-nav' },
    stack.length > 1 ? h('button', { class: 'btn sm', onClick: backModal, title: 'Zurück (Esc)' }, '← Zurück') : null,
    h('button', { class: 'icon-btn', onClick: closeModal, title: 'Alles schließen' }, '✕'));
}

export async function openTitle(mediaType, tmdbId, onChange) {
  ensureRoot();
  const state = { kind: 'title', mediaType, tmdbId, onChange, changed: false, last: null };
  stack.push(state); modalState = state;
  showSpinner();
  try {
    const t = await api.title(mediaType, tmdbId);
    if (modalState === state) renderModal(t);
  } catch (e) { if (modalState === state) showError(e); }
}

export async function openPerson(personId, onChange) {
  ensureRoot();
  await loadFavSet();
  const state = { kind: 'person', personId, onChange, changed: false, last: null };
  stack.push(state); modalState = state;
  showSpinner();
  try {
    const p = await api.person(personId);
    if (modalState === state) renderPerson(p);
  } catch (e) { if (modalState === state) showError(e); }
}

export async function backModal() {
  if (stack.length <= 1) { closeModal(); return; }
  const popped = stack.pop();
  modalState = stack[stack.length - 1];
  if (popped.changed) modalState.changed = true;
  const state = modalState;
  showSpinner();
  try {
    if (state.kind === 'title') { const t = await api.title(state.mediaType, state.tmdbId); if (modalState === state) renderModal(t); }
    else { const p = await api.person(state.personId); if (modalState === state) renderPerson(p); }
  } catch (e) { if (modalState === state) showError(e); }
}

export function closeModal() {
  const root = document.getElementById('modal-root');
  root.innerHTML = '';
  document.body.style.overflow = '';
  if (onKeyHandler) document.removeEventListener('keydown', onKeyHandler);
  const base = stack[0];
  const changed = stack.some((s) => s.changed);
  stack.length = 0; modalEl = null; modalState = null; onKeyHandler = null;
  if (changed && base?.onChange) base.onChange(base.kind === 'title' ? base.last : undefined);
}

async function act(fn, successMsg) {
  const state = modalState;
  try {
    const t = await fn();
    state.changed = true;
    if (modalState === state) renderModal(t);
    if (successMsg) toast(successMsg, 'ok');
  } catch (e) { toast(e.message, 'err'); }
}

const LANG_LABEL = (l) => ({ de: 'DE', en: 'EN', fr: 'FR', es: 'ES', it: 'IT', pl: 'PL', pt: 'PT', tr: 'TR', ja: 'JA', ko: 'KO', hi: 'HI' })[l] || l.toUpperCase();

function renderModal(t) {
  const modal = modalEl;
  modalState.last = t;
  const u = t.user || {};
  const av = t.availability || {};
  const mt = t.media_type, id = t.tmdb_id;
  const isTv = mt === 'tv';
  modal.innerHTML = '';
  if (modal.parentElement) modal.parentElement.scrollTop = 0;

  const offers = [];
  const offerGroup = (list, kind, mine) => list.forEach((p) => offers.push(h('div', { class: `offer ${mine ? 'mine' : ''}`, title: p.region ? `${p.name} in ${regionName(p.region)} – nur per VPN erreichbar` : p.audio && p.audio.length ? `Ton: ${p.audio.map(LANG_LABEL).join(', ')}${p.subs?.length ? ' · Untertitel: ' + p.subs.map(LANG_LABEL).join(', ') : ''}` : `${p.name} (keine Sprachdaten)` },
    h('img', { src: IMG(p.logo, 'w92'), alt: '' }), h('span', {}, p.name, p.region ? regionBadge(p.region, 'inline') : null, h('div', { class: 'kind' }, p.region ? `${kind} · ${regionName(p.region)} (VPN)` : kind),
      p.audio && p.audio.length ? h('div', { class: 'audio' }, '🔊 ' + p.audio.map(LANG_LABEL).join(' ')) : null))));
  offerGroup(av.sub || [], 'Im Abo ✓', true);
  offerGroup(av.free || [], 'Kostenlos ✓', true);
  offerGroup(av.other_sub || [], 'Abo (nicht aktiv)', false);
  offerGroup(av.other_free || [], 'Kostenlos (nicht aktiv)', false);
  offerGroup(av.rent || [], 'Leihen', false);
  offerGroup((av.buy || []).filter((b) => !(av.rent || []).some((r) => r.id === b.id)), 'Kaufen', false);

  const stars = h('div', { class: 'stars' },
    ...Array.from({ length: 10 }, (_, i) => i + 1).map((n) => h('button', { class: u.rating === n ? 'on' : '', onClick: () => act(() => api.setRating(mt, id, u.rating === n ? null : n), u.rating === n ? 'Bewertung entfernt' : `Bewertet mit ${n}`) }, n)));

  const btn = (label, status, cls = '') => h('button', {
    class: `btn sm ${u.status === status ? 'active' : ''} ${cls}`,
    onClick: () => u.status === status ? act(() => api.removeEntry(mt, id), 'Entfernt') : act(() => api.setStatus(mt, id, status), STATUS_LABEL[status]),
  }, STATUS_LABEL[status]);

  const seasonsEl = isTv ? renderSeasons(t) : null;
  const prog = t.progress;
  const cast = t.cast || [];

  modal.append(
    h('div', { class: 'hero', style: t.backdrop_path ? { backgroundImage: `url(${IMG(t.backdrop_path, 'w1280')})` } : {} }, navButtons()),
    h('div', { class: 'body' },
      h('div', { class: 'poster playable', title: 'Trailer abspielen', onClick: () => playTrailer(mt, id, t.title) },
        t.poster_path ? h('img', { src: IMG(t.poster_path, 'w500'), alt: '' }) : h('div', { class: 'noposter', style: { height: '100%', display: 'grid', placeItems: 'center', fontSize: '3rem' } }, isTv ? '📺' : '🎬'),
        h('div', { class: 'play' }, '▶')),
      h('div', { class: 'info' },
        h('h2', { class: 'title' }, t.title, t.year ? h('span', { class: 'muted', style: { fontWeight: 400 } }, ` (${t.year})`) : null),
        t.original_title && t.original_title !== t.title ? h('div', { class: 'muted small' }, t.original_title) : null,
        h('div', { class: 'meta' },
          t.imdb_rating ? h('span', { class: 'pill-imdb', title: `${t.imdb_votes?.toLocaleString('de-DE')} Stimmen` }, `IMDb ${t.imdb_rating.toFixed(1)}`) : null,
          t.tmdb_rating ? h('span', { class: 'pill-tmdb', title: `${t.tmdb_votes?.toLocaleString('de-DE')} Stimmen` }, `TMDB ${t.tmdb_rating.toFixed(1)}`) : null,
          h('span', { class: 'tag' }, isTv ? 'Serie' : 'Film'),
          t.certification ? h('span', { class: 'tag fsk' }, `FSK ${t.certification}`) : null,
          fmtRuntime(t.runtime) ? h('span', {}, isTv ? `~${fmtRuntime(t.runtime)}/Folge` : fmtRuntime(t.runtime)) : null,
          isTv && t.number_of_seasons ? h('span', {}, `${t.number_of_seasons} Staffel${t.number_of_seasons > 1 ? 'n' : ''}`) : null,
          isTv && t.status ? h('span', {}, ({ 'Returning Series': 'läuft', 'Ended': 'beendet', 'Canceled': 'abgesetzt', 'In Production': 'in Produktion', 'Planned': 'geplant' })[t.status] || t.status) : null,
          (t.origin_countries || []).length ? h('span', {}, t.origin_countries.join(', ')) : null,
          t.blocked_by?.length ? h('span', { class: 'tag block-tag', title: 'Wird in Vorschlägen ausgeblendet (Nicht mein Fall)' }, `🚫 Mit ${t.blocked_by.join(', ')}`) : null,
        ),
        h('div', { class: 'chips' }, ...(t.genres || []).map((g) => h('span', { class: 'chip', style: { cursor: 'default' } }, g))),
        h('div', { class: 'actions' },
          isTv ? btn('Verfolgen', 'watching') : btn('Watchlist', 'watchlist'),
          btn('Gesehen', 'watched'),
          isTv && (u.status === 'watching' || u.status === 'dropped') ? btn('Abgebrochen', 'dropped') : null,
          btn('Kein Interesse', 'disliked', 'danger'),
          u.status ? h('button', { class: 'btn sm ghost', title: 'Komplett aus der Bibliothek löschen (Status und Bewertung, auch bei TMDB)', onClick: () => act(() => api.removeEntry(mt, id), 'Aus Bibliothek entfernt') }, '🗑 Entfernen') : null,
          h('button', { class: 'btn sm ghost', title: 'Daten von TMDB neu laden', onClick: () => act(() => api.title(mt, id, true), 'Aktualisiert') }, '↻'),
        ),
        h('div', { class: 'section-title' }, 'Meine Bewertung', u.rated_at ? h('span', { class: 'muted', style: { textTransform: 'none', letterSpacing: 0, fontWeight: 500 } }, ` · ${fmtDate(u.rated_at)}`) : null),
        stars,
        h('div', { class: 'section-title' }, `Wo streamen? · ${MODE_LABEL[av.mode] || 'unbekannt'}`),
        offers.length ? h('div', { class: 'offers' }, ...offers) : h('p', { class: 'muted small' }, 'Aktuell kein Streaming-Angebot in Deutschland (oder deinen VPN-Ländern) bekannt.'),
        av.link ? h('p', { class: 'small' }, h('a', { href: av.jw_path ? `https://www.justwatch.com${av.jw_path}` : av.link, target: '_blank', rel: 'noopener', style: { color: 'var(--accent)' } }, 'Angebote auf JustWatch ansehen ↗'),
          av.jw ? h('span', { class: 'muted' }, ' · Wiedergabesprachen laut JustWatch') : h('span', { class: 'muted' }, ' · keine Sprachdaten bei JustWatch')) : null,
        t.overview ? [h('div', { class: 'section-title' }, 'Handlung'), h('p', { class: 'overview' }, t.overview)] : null,
        cast.length ? [h('div', { class: 'section-title' }, 'Besetzung'), castRow(cast)] : null,
        isTv && prog ? [
          h('div', { class: 'section-title' }, 'Fortschritt',
            prog.aired_total ? h('span', { class: 'muted', style: { textTransform: 'none', letterSpacing: 0, fontWeight: 500 } }, ` · ${prog.watched_total}/${prog.aired_total} Folgen gesehen`) : null),
          h('div', { class: 'progress', style: { marginBottom: '8px' } }, h('div', { style: { width: (prog.aired_total ? Math.round(prog.watched_total / prog.aired_total * 100) : 0) + '%' } })),
          h('div', { class: 'row small', style: { marginBottom: '6px' } },
            prog.pending > 0 ? h('b', {}, `${prog.pending} Folge${prog.pending > 1 ? 'n' : ''} ausstehend`) : (prog.aired_total ? h('b', { style: { color: 'var(--ok)' } }, '✓ Auf Stand') : null),
            prog.next ? h('span', { class: 'muted' }, `· Als Nächstes: ${prog.next.season_name || 'Staffel ' + prog.next.season}, Folge ${prog.next.episode}`) : null,
            t.next_episode_air ? h('span', { class: 'muted' }, `· 📅 nächste Ausstrahlung ${fmtDate(t.next_episode_air)}`) : null),
          h('div', { class: 'row', style: { marginBottom: '10px' } },
            prog.next ? h('button', { class: 'btn sm ok', onClick: () => act(() => api.markEpisode(id, prog.next.season, prog.next.episode, true), `S${prog.next.season} E${prog.next.episode} gesehen`) }, `✓ S${prog.next.season} E${prog.next.episode} gesehen`) : null,
            prog.pending > 0 ? h('button', { class: 'btn sm', onClick: () => act(() => api.completeSeries(id), 'Alle Folgen als gesehen markiert') }, '✓ Alles bis heute gesehen') : null,
            prog.complete && ['Ended', 'Canceled'].includes(t.status) && u.status === 'watching' ? h('button', { class: 'btn sm', onClick: () => act(() => api.setStatus(mt, id, 'watched'), 'Serie abgeschlossen') }, '🏁 Als gesehen abschließen') : null),
          h('div', { class: 'section-title' }, 'Staffeln & Folgen'),
          seasonsEl,
        ] : null,
        h('p', { class: 'small muted', style: { marginTop: '18px' } },
          h('a', { href: `https://www.themoviedb.org/${mt}/${id}`, target: '_blank', rel: 'noopener' }, 'TMDB ↗'), ' · ',
          t.imdb_id ? h('a', { href: `https://www.imdb.com/title/${t.imdb_id}/`, target: '_blank', rel: 'noopener' }, 'IMDb ↗') : 'kein IMDb-Eintrag'),
      ),
    ),
  );
  loadFavSet().then(() => { modal.querySelectorAll('.cast-card:not(.blocked)').forEach((el) => { if (favSet?.has(+el.dataset.id)) el.classList.add('fav'); }); });
}

function castRow(cast) {
  return h('div', { class: 'cast-row' }, ...cast.map((c) => h('div', { class: `cast-card ${favSet?.has(c.id) && !c.blocked ? 'fav' : ''} ${c.blocked ? 'blocked' : ''}`, 'data-id': c.id, title: `${c.name}${c.character ? ' als ' + c.character : ''}${c.blocked ? ' · Nicht mein Fall' : ''}`, onClick: () => openPerson(c.id) },
    h('div', { class: 'photo' }, c.profile_path ? h('img', { src: IMG(c.profile_path, 'w185'), alt: '' }) : h('span', {}, '👤'), h('span', { class: 'star' }, '★'), h('span', { class: 'block' }, '🚫')),
    h('div', { class: 'n' }, c.name),
    c.character ? h('div', { class: 'r' }, c.character) : null)));
}

// ---------- Personen-Modal ----------
function renderPerson(p) {
  const modal = modalEl;
  modalState.last = p;
  modal.innerHTML = '';
  if (modal.parentElement) modal.parentElement.scrollTop = 0;
  const state = modalState;
  const showAll = state.showAll || false;
  const credits = (p.credits || []).filter((c) => showAll || c.main);
  const bioLong = (p.biography || '').length > 500;
  const bioExpanded = state.bioExpanded || false;
  const gender = p.gender === 1 ? 'Schauspielerin' : p.gender === 2 ? 'Schauspieler' : 'Person';

  const favBtn = h('button', { class: `btn sm ${p.favorite ? 'active' : ''}`, onClick: async () => {
    try {
      const r = await api.setFavorite(p.id, !p.favorite);
      markFavorite(p.id, r.favorite);
      state.changed = true;
      toast(r.favorite ? `${p.name} zu deinen Schauspielern hinzugefügt` : `${p.name} entfernt`, 'ok');
      renderPerson({ ...p, favorite: r.favorite });
    } catch (e) { toast(e.message, 'err'); }
  } }, p.favorite ? '★ Favorit' : '☆ Favorit');

  const creditRow = (c) => {
    const u = c.user || {};
    const av = c.availability || {};
    const provs = [...(av.sub || []), ...(av.free || [])].slice(0, 2);
    return h('div', { class: 'credit', onClick: () => openTitle(c.media_type, c.tmdb_id) },
      h('div', { class: 'cp' }, c.poster_path ? h('img', { src: IMG(c.poster_path, 'w92'), alt: '' }) : h('span', {}, c.media_type === 'tv' ? '📺' : '🎬')),
      h('div', { class: 'ct' },
        h('div', { class: 'row', style: { gap: '6px' } }, h('b', {}, c.title), c.year ? h('span', { class: 'muted' }, `(${c.year})`) : null,
          h('span', { class: 'tag', style: { fontSize: '0.7rem' } }, c.media_type === 'tv' ? 'Serie' : 'Film'),
          !c.main ? h('span', { class: 'muted small' }, 'Nebenrolle') : null),
        h('div', { class: 'muted small' }, [c.character ? `als ${c.character}` : null, c.media_type === 'tv' && c.episode_count ? `${c.episode_count} Folgen` : null].filter(Boolean).join(' · '))),
      h('div', { class: 'cm' },
        u.status ? h('span', { class: `badge-status ${u.status}`, title: STATUS_LABEL[u.status] }, u.status === 'watched' ? `✓ Gesehen${u.rating ? ' · ' + u.rating : ''}` : STATUS_LABEL[u.status]) : null,
        c.imdb_rating ? h('span', { class: 'badge-imdb', title: 'IMDb-Bewertung' }, `IMDb ${c.imdb_rating.toFixed(1)}`)
          : (c.vote_average ? h('span', { class: 'pill-tmdb', style: { fontSize: '0.75rem' }, title: 'TMDB-Bewertung (IMDb noch nicht geladen)' }, `TMDB ${c.vote_average.toFixed(1)}`) : null),
        provs.length ? providerLogos(provs) : (av.mode ? h('span', { class: `mode-dot mode-${av.mode}`, style: { position: 'static', display: 'inline-block' }, title: MODE_LABEL[av.mode] }) : null)));
  };

  const blockBtn = p.blocked
    ? h('button', { class: 'pill-block', title: 'Sperre aufheben', onClick: async () => {
      try { await api.setBlocked(p.id, false); state.changed = true; toast(`${p.name} wieder freigegeben`, 'ok'); renderPerson({ ...p, blocked: false }); } catch (e) { toast(e.message, 'err'); }
    } }, '🚫 Ausgeblendet')
    : h('button', { class: 'btn sm ghost block-btn', title: 'Nicht mein Fall: Titel mit Hauptrolle dieser Person nicht mehr vorschlagen', onClick: async () => {
      try { await api.setBlocked(p.id, true); markFavorite(p.id, false); state.changed = true; toast(`${p.name}: Titel mit Hauptrolle werden nicht mehr vorgeschlagen`, 'ok'); renderPerson({ ...p, blocked: true, favorite: false }); } catch (e) { toast(e.message, 'err'); }
    } }, '🚫');

  modal.append(
    h('div', { class: 'hero person-hero' }, navButtons()),
    h('div', { class: 'body' },
      h('div', { class: 'poster' }, p.profile_path ? h('img', { src: IMG(p.profile_path, 'h632'), alt: '' }) : h('div', { class: 'noposter', style: { height: '100%', display: 'grid', placeItems: 'center', fontSize: '3rem' } }, '👤')),
      h('div', { class: 'info' },
        h('h2', { class: 'title' }, p.name),
        h('div', { class: 'meta' },
          h('span', { class: 'tag' }, p.known_for_department === 'Acting' ? gender : (p.known_for_department || 'Person')),
          p.birthday ? h('span', {}, `🎂 ${fmtDate(p.birthday)}${p.age != null ? ` (${p.deathday ? '†' : ''}${p.age})` : ''}`) : null,
          p.deathday ? h('span', {}, `† ${fmtDate(p.deathday)}`) : null,
          p.place_of_birth ? h('span', {}, p.place_of_birth) : null),
        h('div', { class: 'actions' }, favBtn, blockBtn,
          h('button', { class: 'btn sm ghost', title: 'Filmografie neu laden', onClick: async () => { try { renderPerson(await api.person(p.id, true)); toast('Aktualisiert', 'ok'); } catch (e) { toast(e.message, 'err'); } } }, '↻')),
        p.blocked ? h('p', { class: 'small muted', style: { marginTop: '-6px' } }, `Titel mit Hauptrolle von ${p.name} werden in Entdecken, „Beliebt“, „Für dich“ und „Neu von deinen Schauspielern“ nicht vorgeschlagen. Suche und Bibliothek bleiben unverändert.`) : null,
        p.biography ? [h('div', { class: 'section-title' }, 'Biografie'),
          h('p', { class: 'overview' }, bioLong && !bioExpanded ? p.biography.slice(0, 500).trimEnd() + ' …' : p.biography),
          bioLong ? h('button', { class: 'btn sm ghost', onClick: () => { state.bioExpanded = !bioExpanded; renderPerson(p); } }, bioExpanded ? 'Weniger' : 'Mehr lesen') : null] : null,
        h('div', { class: 'row spread', style: { marginTop: '14px' } },
          h('div', { class: 'section-title', style: { margin: 0 } }, showAll ? `Alle Rollen (${(p.credits || []).length})` : `Hauptrollen (${p.main_roles || 0})`),
          h('div', { class: 'seg' },
            h('button', { class: !showAll ? 'active' : '', onClick: () => { state.showAll = false; renderPerson(p); } }, 'Hauptrollen'),
            h('button', { class: showAll ? 'active' : '', onClick: () => { state.showAll = true; renderPerson(p); } }, 'Alle'))),
        credits.length ? h('div', { class: 'credits' }, ...credits.map(creditRow)) : h('p', { class: 'muted small' }, 'Keine Rollen gefunden.'),
        h('p', { class: 'small muted', style: { marginTop: '18px' } },
          h('a', { href: `https://www.themoviedb.org/person/${p.id}`, target: '_blank', rel: 'noopener' }, 'TMDB ↗'), ' · ',
          p.imdb_id ? h('a', { href: `https://www.imdb.com/name/${p.imdb_id}/`, target: '_blank', rel: 'noopener' }, 'IMDb ↗') : null),
      ),
    ),
  );
}

const openSeasons = new Set();

async function playTrailer(mt, id, title) {
  let data;
  try { data = await api.videos(mt, id); } catch (e) { toast(e.message, 'err'); return; }
  if (!data.best) { toast('Kein Trailer bei TMDB hinterlegt', 'err'); return; }
  const root = document.getElementById('modal-root');
  const close = () => { overlay.remove(); document.removeEventListener('keydown', onKey); };
  const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); close(); } };
  const pick = (v) => { frame.src = `https://www.youtube-nocookie.com/embed/${v.key}?autoplay=1&rel=0&hl=de`; label.textContent = `${v.name || v.type}${v.lang ? ' · ' + v.lang.toUpperCase() : ''}`; };
  const frame = h('iframe', { allow: 'autoplay; fullscreen; encrypted-media', allowfullscreen: true, frameborder: '0' });
  const label = h('span', { class: 'muted small' });
  const overlay = h('div', { class: 'trailer-backdrop', onClick: (e) => { if (e.target === overlay) close(); } },
    h('div', { class: 'trailer' },
      h('div', { class: 'row spread', style: { marginBottom: '8px' } },
        h('div', {}, h('b', {}, title), ' ', label),
        h('div', { class: 'row' },
          data.videos.length > 1 ? h('select', { onChange: (e) => pick(data.videos[+e.target.value]) },
            ...data.videos.map((v, i) => h('option', { value: i }, `${v.type}: ${v.name || ''}${v.lang ? ' (' + v.lang.toUpperCase() + ')' : ''}`))) : null,
          h('button', { class: 'icon-btn', onClick: close, title: 'Schließen (Esc)' }, '✕'))),
      h('div', { class: 'trailer-frame' }, frame)));
  root.append(overlay);
  document.addEventListener('keydown', onKey, true);
  pick(data.best);
}

function renderSeasons(t) {
  const prog = t.progress || { seasons: [] };
  const id = t.tmdb_id;
  if (!prog.seasons.length) return h('p', { class: 'muted small' }, 'Keine Staffelinformationen.');
  const wrap = h('div', { class: 'seasons' });
  const today = new Date().toISOString().slice(0, 10);
  for (const s of prog.seasons) {
    const aired = s.aired > 0;
    const watchedSet = new Set(s.watched_episodes || []);
    const cb = h('input', { type: 'checkbox', checked: s.complete, disabled: !aired, title: 'Staffel (und alle davor) komplett gesehen', onChange: () =>
      act(() => api.markSeason(id, s.season_number, cb.checked, true), cb.checked ? `${s.name || 'Staffel ' + s.season_number} gesehen` : null) });
    const epBox = h('div', { class: `episodes ${openSeasons.has(s.season_number) ? '' : 'hidden'}` });
    const partial = aired && !s.complete && s.watched > 0;
    const loadEpisodes = async () => {
      epBox.innerHTML = '';
      epBox.append(h('span', { class: 'spinner' }));
      try {
        const se = await api.season(id, s.season_number);
        epBox.innerHTML = '';
        se.episodes.forEach((e) => {
          const epAired = e.air_date && e.air_date <= today;
          const isW = watchedSet.has(e.episode_number);
          const ecb = h('input', { type: 'checkbox', checked: isW, disabled: !epAired, onChange: () =>
            act(() => api.markEpisode(id, s.season_number, e.episode_number, ecb.checked, false), null) });
          epBox.append(h('div', { class: `episode ${isW ? 'watched' : ''} ${!epAired ? 'future' : ''}` },
            ecb,
            h('b', {}, `${e.episode_number}.`),
            h('span', { class: 'grow' }, e.name || `Folge ${e.episode_number}`),
            h('span', { class: 'muted' }, [fmtDate(e.air_date), e.runtime ? `${e.runtime} Min` : null].filter(Boolean).join(' · ')),
            epAired && !isW ? h('button', { class: 'btn sm ghost', title: 'Alles bis einschließlich dieser Folge als gesehen markieren', onClick: () =>
              act(() => api.markEpisode(id, s.season_number, e.episode_number, true, true), `Bis S${s.season_number} E${e.episode_number} gesehen`) }, '⇤ bis hier') : null));
        });
      } catch (e) { epBox.innerHTML = ''; epBox.append(h('span', { class: 'muted' }, e.message)); }
    };
    const row = h('div', { class: `season ${s.complete ? 'watched' : ''}` },
      cb,
      h('span', { class: 'sn' }, s.name || `Staffel ${s.season_number}`),
      h('span', { class: 'sm' }, [
        aired ? `${s.watched}/${s.aired} gesehen` : null,
        s.episode_count && s.episode_count !== s.aired ? `${s.episode_count} Folgen geplant` : null,
        s.air_date ? fmtDate(s.air_date) : null].filter(Boolean).join(' · ')),
      partial ? h('span', { class: 'tag', style: { fontSize: '0.72rem' } }, 'angefangen') : null,
      !aired ? h('span', { class: 'future' }, 'noch nicht ausgestrahlt') : null,
      h('span', { class: 'grow' }),
      h('button', { class: 'btn sm ghost', onClick: () => {
        if (!epBox.classList.contains('hidden')) { epBox.classList.add('hidden'); openSeasons.delete(s.season_number); return; }
        openSeasons.add(s.season_number);
        epBox.classList.remove('hidden');
        if (!epBox.childElementCount) loadEpisodes();
      } }, openSeasons.has(s.season_number) ? 'Folgen ▴' : 'Folgen ▾'),
    );
    wrap.append(row, epBox);
    if (openSeasons.has(s.season_number)) loadEpisodes();
  }
  return wrap;
}
