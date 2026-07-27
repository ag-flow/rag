/** Miroir de `rag.schemas.vault_endpoints.slugify` (aperçu côté client).
 *
 * Le slug faisant foi est calculé par le backend ; celui-ci ne sert qu'à
 * l'aperçu temps réel dans le formulaire.
 */
export function slugifyLabel(label: string): string {
  return label
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}
