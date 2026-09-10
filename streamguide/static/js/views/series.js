// Serientracking: Fortschritt auf Folgen-Ebene, neue Staffeln/Folgen, nächste Folge, Abbrechen.
import { api, IMG } from '../api.js';
import { h, openTitle, providerLogos, fmtDate, empty, toast, skeletons } from '../ui.js';

export async function render(root) {
  const f = { view: 'all' };
  const list = h('div', {});
  let items = [];

  const seg = () => {
    const el = h('div', { class: 'seg' });
    const opts = [['all', 'Alle'], ['new', 'Neue Folgen'], ['open', 'Weiterschauen'], ['fresh', 'Nicht begonnen'], ['waiting', 'Warten auf Nachschub'], ['done', 'Auf Stand'], ['dropped', 'Abgebrochen']];
    const draw = () => { el.innerHTML = ''; opts.forEach(([v, l]) => el.append(h('button', { class: f.view === v ? 'active' : '', onClick: () => { f.view = v; draw(); f.view === 'dropped' || items.some((t) => t.user.status === 'dropped') ? load() : show(); } }, l))); };
    draw();
    return el;
  };

  const show = () => {
    let l = items.filter((t) => t.user.status === (f.view === 'dropped' ? 'dropped' : 'watching'));
    if (f.view === 'new') l = l.filter((t) => t.user.new_season_flag);
    else if (f.view === 'open') l = l.filter((t) => t.progress.pending > 0 && t.progress.started && !t.user.new_season_flag);
    else if (f.view === 'fresh') l = l.filter((t) => !t.progress.started);
    else if (f.view === 'waiting') l = l.filter((t) => t.progress.pending === 0 && !['Ended', 'Canceled'].includes(t.status));
    else if (f.view === 'done') l = l.filter((t) => t.progress.pending === 0);
    list.innerHTML = '';
    if (!l.length) { list.append(empty(items.length ? 'Keine Serien in dieser Ansicht.' : 'Noch keine Serien verfolgt. Öffne eine Serie und klicke auf „Verfolgen“ oder hake direkt eine Folge ab.', '📺')); return; }
    const wrap = h('div', { class: 'series-list' });
    for (const t of l) wrap.append(seriesCard(t));
    list.append(wrap);
  };

  const act = async (fn, msg) => { try { await fn(); if (msg) toast(msg, 'ok'); load(); } catch (e) { toast(e.message, 'err'); } };

  const seriesCard = (t) => {
    const p = t.progress, u = t.user, av = t.availability || {};
    const pct = p.aired_total ? Math.round((p.watched_total / p.aired_total) * 100) : 0;
    const next = p.next;
    const provs = [...(av.sub || []), ...(av.free || [])];
    const statusTxt = ({ 'Returning Series': 'läuft', 'Ended': 'beendet', 'Canceled': 'abgesetzt', 'In Production': 'in Produktion' })[t.status] || t.status || '';
    const badge = u.status === 'dropped' ? h('span', { class: 'badge-status dropped' }, '⏸ Abgebrochen')
      : u.newly_available ? h('span', { class: 'badge-new avail' }, 'JETZT VERFÜGBAR')
      : u.new_season_flag ? h('span', { class: 'badge-new' }, u.new_kind === 'season' ? 'NEUE STAFFEL' : 'NEUE FOLGEN') : null;
    return h('div', { class: 'glass series-card', onClick: () => openTitle('tv', t.tmdb_id, load) },
      h('div', { class: 'p' }, t.poster_path ? h('img', { src: IMG(t.poster_path, 'w185'), alt: '' }) : null),
      h('div', { class: 'c' },
        h('div', { class: 'row spread' }, h('span', { class: 't' }, t.title), badge || (!p.started && u.status === 'watching' ? h('span', { class: 'tag', style: { fontSize: '0.72rem' } }, 'nicht begonnen') : null)),
        h('div', { class: 'muted small' }, [t.year, statusTxt, t.imdb_rating ? `IMDb ${t.imdb_rating.toFixed(1)}` : null, p.aired_total ? `${p.aired_total} Folgen` : null].filter(Boolean).join(' · ')),
        h('div', { class: 'progress' }, h('div', { style: { width: pct + '%' } })),
        h('div', { class: 'row spread small' },
          h('span', {}, p.pending > 0 ? h('b', {}, `${p.pending} Folge${p.pending > 1 ? 'n' : ''} ausstehend`) : (p.aired_total ? '✓ Auf Stand' : 'Noch keine Folgen'),
            h('span', { class: 'muted' }, ` · ${p.watched_total}/${p.aired_total} gesehen`)),
          u.status === 'watching' && next ? h('span', { class: 'row', style: { gap: '4px' } },
            h('button', { class: 'btn sm ok', title: 'Nächste Folge als gesehen markieren', onClick: (e) => { e.stopPropagation(); act(() => api.markEpisode(t.tmdb_id, next.season, next.episode, true), `S${next.season} E${next.episode} gesehen`); } }, `✓ S${next.season} E${next.episode}`),
            h('button', { class: 'btn sm', title: `Staffel ${next.season} komplett als gesehen markieren`, onClick: (e) => { e.stopPropagation(); act(() => api.markSeason(t.tmdb_id, next.season, true), `Staffel ${next.season} gesehen`); } }, `Staffel ${next.season} ✓`)) : null),
        h('div', { class: 'row small muted' },
          next ? h('span', {}, `Als Nächstes: ${next.season_name || 'Staffel ' + next.season}, Folge ${next.episode}`) : null,
          !next && t.next_episode_air ? h('span', {}, `📅 Nächste Folge ${fmtDate(t.next_episode_air)}`) : null,
          h('span', { class: 'grow' }),
          provs.length ? providerLogos(provs.slice(0, 3)) : h('span', { class: 'muted' }, av.mode === 'other_sub' ? 'anderes Abo' : av.mode === 'rent' ? 'nur Leihen/Kaufen' : 'nicht verfügbar')),
      ));
  };

  const load = async () => {
    try {
      const r = await api.library('watching,dropped', 'tv', 'updated');
      items = r.results;
      items.sort((a, b) => (b.user.newly_available - a.user.newly_available) || (b.user.new_season_flag - a.user.new_season_flag) || ((b.progress.pending > 0) - (a.progress.pending > 0)) || a.title.localeCompare(b.title, 'de'));
      show();
    } catch (e) { list.innerHTML = ''; list.append(empty(e.message, '⚠️')); }
  };

  root.append(
    h('div', { class: 'page-head' },
      h('div', {}, h('h1', {}, 'Serien 📺'), h('div', { class: 'sub' }, 'Verfolgte Serien: noch nicht begonnen, weiterschauen, neue Staffeln bei deinen Anbietern.')),
      h('button', { class: 'btn', onClick: async () => { try { await api.post('/library/refresh?only_series=true'); toast('Serien-Check gestartet'); } catch (e) { toast(e.message, 'err'); } } }, '↻ Neue Folgen prüfen')),
    h('div', { class: 'glass panel row spread' }, seg(), h('span', { class: 'muted small' }, 'In den Details: Folgen einzeln abhaken, „bis hier gesehen“, Staffel/Serie komplett, Abbrechen.')),
    h('div', { style: { height: '18px' } }),
    list,
  );
  list.append(skeletons(4));
  await load();
  const onJob = (e) => { if (['refresh_library', 'import_imdb', 'tmdb_sync', 'import_list'].includes(e.detail?.kind)) load(); };
  window.addEventListener('job-finished', onJob);
  return { destroy: () => window.removeEventListener('job-finished', onJob) };
}
