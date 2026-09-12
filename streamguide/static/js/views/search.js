// Suche ist in „Entdecken“ integriert; alte Links (#/search?q=…) werden weitergeleitet.
export async function render(root, params) {
  location.replace(params.q ? `#/discover?q=${encodeURIComponent(params.q)}` : '#/discover');
  return {};
}
