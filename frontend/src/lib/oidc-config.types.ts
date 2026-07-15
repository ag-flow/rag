// Types miroirs des schemas Pydantic OidcConfigRead / OidcConfigCreate
// (cf. backend/src/rag/schemas/oidc.py)

export type OidcConfig = {
  issuer: string;
  client_id: string;
};

export type OidcConfigCreate = {
  issuer: string;
  client_id: string;
};
