import type { ChannelHit } from "@/lib/search-config.types";

export type SimulatedHit = {
  path: string;
  chunk_index: number;
  score: number;
};

/**
 * Refusion RRF côté client (simulation du playground, sans rappel serveur) :
 * score(doc) = w_vector / (k + rang_vectoriel) + w_lexical / (k + rang_lexical).
 * Un document absent d'un canal ne contribue rien sur ce canal.
 * Identité d'un document = path + chunk_index.
 */
export function simulateRrf(
  vectorChannel: ChannelHit[],
  lexicalChannel: ChannelHit[],
  k: number,
  weightVector: number,
  weightLexical: number,
): SimulatedHit[] {
  const byDoc = new Map<string, SimulatedHit>();

  const accumulate = (channel: ChannelHit[], weight: number) => {
    for (const hit of channel) {
      const key = `${hit.path}#${hit.chunk_index}`;
      const contribution = weight / (k + hit.rank);
      const existing = byDoc.get(key);
      if (existing) {
        existing.score += contribution;
      } else {
        byDoc.set(key, { path: hit.path, chunk_index: hit.chunk_index, score: contribution });
      }
    }
  };

  accumulate(vectorChannel, weightVector);
  accumulate(lexicalChannel, weightLexical);

  return [...byDoc.values()].sort((a, b) => b.score - a.score);
}
