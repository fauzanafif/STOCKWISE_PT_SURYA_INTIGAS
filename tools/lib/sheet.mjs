// Sheet reading helpers: header detection by column signature, row objects.
import XLSX from 'xlsx';
import path from 'node:path';

export function openWorkbook(file) {
  return XLSX.readFile(file, { cellDates: true });
}

/** Read a sheet as an array-of-arrays (raw values, blank rows dropped).
 *  Some export sheets declare a bogus width of 16384 cols (XFD) which makes
 *  sheet_to_json materialise hundreds of millions of empty cells — clamp the
 *  read range to `maxCols` (real STOCKWISE sheets are < 30 wide). */
export function sheetRows(wb, name, maxCols = 120) {
  const ws = wb.Sheets[name];
  if (!ws || !ws['!ref']) return [];
  const range = XLSX.utils.decode_range(ws['!ref']);
  if (range.e.c > maxCols) {
    range.e.c = maxCols;
    return XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: null, blankrows: false, range });
  }
  return XLSX.utils.sheet_to_json(ws, { header: 1, raw: true, defval: null, blankrows: false });
}

const clean = (c) => (c === null || c === undefined ? '' : String(c).replace(/\s+/g, ' ').trim());

/**
 * Locate the header row by requiring every token in `signature` to appear
 * (case-insensitive substring) among that row's cells, scanning the first
 * `scan` rows. Falls back to the row with the most non-empty string cells.
 * Returns { headerIndex, header: string[], dataRows: any[][] }.
 */
export function detectHeader(rows, signature = [], scan = 12) {
  const sig = signature.map((s) => s.toUpperCase());
  let best = -1;
  for (let i = 0; i < Math.min(scan, rows.length); i++) {
    const cells = (rows[i] || []).map((c) => clean(c).toUpperCase());
    if (sig.length && sig.every((tok) => cells.some((c) => c.includes(tok)))) { best = i; break; }
  }
  if (best === -1) {
    let bestScore = -1;
    for (let i = 0; i < Math.min(scan, rows.length); i++) {
      const score = (rows[i] || []).filter((c) => typeof c === 'string' && c.trim() !== '').length;
      if (score > bestScore) { bestScore = score; best = i; }
    }
  }
  const header = (rows[best] || []).map(clean);
  return { headerIndex: best, header, dataRows: rows.slice(best + 1) };
}

/**
 * Map source header -> canonical names. `mapping` is {canonical: [candidate substrings]}.
 * Matching is case-insensitive; first candidate that is a substring of (or equals) a
 * header cell wins, and each source column is claimed once.
 * Returns { colIndex: {canonical: idx}, missing: [canonical], extra: [headerName] }.
 */
export function mapColumns(header, mapping) {
  const up = header.map((h) => h.toUpperCase());
  const claimed = new Set();
  const colIndex = {};
  for (const [canon, cands] of Object.entries(mapping)) {
    let found = -1;
    for (const cand of cands) {
      const c = cand.toUpperCase();
      for (let i = 0; i < up.length; i++) {
        if (claimed.has(i)) continue;
        if (up[i] === c || up[i].includes(c)) { found = i; break; }
      }
      if (found !== -1) break;
    }
    if (found !== -1) { colIndex[canon] = found; claimed.add(found); }
  }
  const missing = Object.keys(mapping).filter((k) => !(k in colIndex));
  const extra = header.filter((h, i) => h && !claimed.has(i));
  return { colIndex, missing, extra };
}

/** row accessor bound to a colIndex map */
export function rowGetter(colIndex) {
  return (row, canon) => {
    const i = colIndex[canon];
    return i === undefined ? null : (row[i] === undefined ? null : row[i]);
  };
}

export const baseName = (f) => path.basename(f);
