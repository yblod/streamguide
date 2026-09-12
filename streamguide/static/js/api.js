// Kleiner Fetch-Wrapper für die lokale API.
export class ApiError extends Error {
  constructor(status, detail) { super(detail); this.status = status; }
}

async function req(method, path, body, isForm = false) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    if (isForm) opts.body = body;
    else { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  }
  const r = await fetch('/api' + path, opts);
  let data = null;
  try { data = await r.json(); } catch { /* leer */ }
  if (r.status === 401) {
    // Session abgelaufen oder nicht angemeldet → Login-Seite, danach zurück zur aktuellen Ansicht.
    location.href = '/login?next=' + encodeURIComponent(location.pathname + location.hash);
    throw new ApiError(401, 'Nicht angemeldet');
  }
  if (!r.ok) {
    const detail = (data && (data.detail?.[0]?.msg || data.detail)) || r.statusText;
    throw new ApiError(r.status, typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return data;
}

export const api = {
  get: (p) => req('GET', p),
  post: (p, b) => req('POST', p, b),
  put: (p, b) => req('PUT', p, b),
  del: (p) => req('DELETE', p),
  form: (p, fd) => req('POST', p, fd, true),

  status: () => req('GET', '/status'),
  settings: (b) => req('PUT', '/settings', b),
  providers: () => req('GET', '/providers'),
  toggleProvider: (id, active, region = 'DE') => req('PUT', `/providers/${id}`, { active, region }),
  genres: () => req('GET', '/genres'),
  home: () => req('GET', '/home'),
  search: (q, page = 1) => req('GET', `/search?q=${encodeURIComponent(q)}&page=${page}`),
  discover: (f) => req('POST', '/discover', f),
  subs: () => req('GET', '/subs'),
  forYou: () => req('GET', '/for-you'),
  title: (mt, id, refresh = false) => req('GET', `/title/${mt}/${id}${refresh ? '?refresh=true' : ''}`),
  season: (id, n) => req('GET', `/title/tv/${id}/season/${n}`),
  videos: (mt, id) => req('GET', `/title/${mt}/${id}/videos`),
  peopleSearch: (q) => req('GET', `/people/search?q=${encodeURIComponent(q)}`),
  peopleTrending: () => req('GET', '/people/trending'),
  peopleFavorites: () => req('GET', '/people/favorites'),
  peopleNew: () => req('GET', '/people/new'),
  person: (id, refresh = false) => req('GET', `/people/${id}${refresh ? '?refresh=true' : ''}`),
  setFavorite: (id, favorite) => req('PUT', `/people/${id}/favorite`, { favorite }),
  peopleBlocked: () => req('GET', '/people/blocked'),
  setBlocked: (id, blocked) => req('PUT', `/people/${id}/blocked`, { blocked }),
  library: (status, mediaType, sort = 'added') => {
    const q = new URLSearchParams();
    if (status) q.set('status', status);
    if (mediaType) q.set('media_type', mediaType);
    q.set('sort', sort);
    return req('GET', `/library?${q}`);
  },
  setStatus: (mt, id, status, rating) => req('PUT', `/library/${mt}/${id}/status`, { status, rating }),
  setRating: (mt, id, rating) => req('PUT', `/library/${mt}/${id}/rating`, { rating }),
  setSeasons: (id, watched_seasons) => req('PUT', `/library/tv/${id}/seasons`, { watched_seasons }),
  markEpisode: (id, season, episode, watched = true, up_to = false) => req('PUT', `/library/tv/${id}/episode`, { season, episode, watched, up_to }),
  markSeason: (id, season, watched = true, include_previous = true) => req('PUT', `/library/tv/${id}/season`, { season, watched, include_previous }),
  completeSeries: (id) => req('POST', `/library/tv/${id}/complete`),
  removeEntry: (mt, id) => req('DELETE', `/library/${mt}/${id}`),
  jobs: () => req('GET', '/jobs'),
  job: (id) => req('GET', `/jobs/${id}`),
  cancelJob: (id) => req('DELETE', `/jobs/${id}`),
};

export const IMG = (path, size = 'w342') => path ? `https://image.tmdb.org/t/p/${size}${path}` : null;
