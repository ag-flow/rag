// Axe de densité (enabler 75058a6a) : « aéré » (défaut) ou « compact ».
// Piloté par l'attribut data-density sur <html> — les tokens d'espacement
// (density-nav / density-row / density-card) réagissent, aucun composant
// n'est dupliqué. Préférence persistée côté navigateur.

export type Density = "comfortable" | "compact";

const STORAGE_KEY = "rag-density";

export function getStoredDensity(): Density {
  return localStorage.getItem(STORAGE_KEY) === "compact" ? "compact" : "comfortable";
}

export function applyDensity(density: Density): void {
  document.documentElement.dataset.density = density;
  localStorage.setItem(STORAGE_KEY, density);
}

export function applyStoredDensity(): void {
  document.documentElement.dataset.density = getStoredDensity();
}
