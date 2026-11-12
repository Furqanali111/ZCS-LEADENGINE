export type TemplateValues = { practice: string; contact: string; city: string; state: string };

// Fills {practice}, {contact}, {city}, {state}. An empty value also drops the space before it and a comma
// left at the start of a line, so "Hi {contact}," becomes "Hi," and "{contact}, thanks" becomes "thanks".
// Unknown placeholders are left as typed.
export function fillTemplate(text: string, v: TemplateValues): string {
  return text
    .replace(/([ \t]*)\{(practice|contact|city|state)\}/g, (_, space: string, key: keyof TemplateValues) => (v[key] ? space + v[key] : ""))
    .replace(/^[ \t]*,[ \t]*/gm, "");
}
