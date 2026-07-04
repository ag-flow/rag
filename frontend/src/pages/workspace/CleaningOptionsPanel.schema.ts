export interface CleaningOptions {
  clean_content: boolean;
  strip_separators: boolean;
  strip_boilerplate: boolean;
  strip_html: boolean;
}

export const DEFAULT_CLEANING_OPTIONS: CleaningOptions = {
  clean_content: false,
  strip_separators: false,
  strip_boilerplate: false,
  strip_html: false,
};

export const CLEANING_KEYS = [
  "clean_content",
  "strip_separators",
  "strip_boilerplate",
  "strip_html",
] as const satisfies readonly (keyof CleaningOptions)[];
