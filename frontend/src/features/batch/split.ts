/** Split pasted text into batch items on lines containing only "---". A first line written
 * "# Title" names the item. Empty items are dropped. */
export interface DraftItem {
  key: string;
  title: string;
  script: string;
}

let n = 0;
export const newKey = () => `item-${Date.now().toString(36)}-${n++}`;

export function splitBulk(text: string): DraftItem[] {
  return text
    .split(/^\s*-{3,}\s*$/m)
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const m = /^#\s*(.+)\n([\s\S]*)$/.exec(part);
      return { key: newKey(), title: m ? m[1].trim() : "", script: (m ? m[2] : part).trim() };
    })
    .filter((i) => i.script);
}

export const titleFromFile = (name: string) => name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ").trim();
