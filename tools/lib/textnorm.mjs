// Shared text / value normalization. Mirrored by stockwise/textnorm.py — keep in sync.
import crypto from 'node:crypto';

const CONDITION_TAGS = [
  'BEKAS', 'REFURBISHED', 'REFURBHISED', 'REFUBISHED', 'REFURBISH',
  'BUANG', 'VULKANISIR', 'RECONDITION', 'REKONDISI', 'BARU',
];

// values that mean "empty" in key/reference columns
const SENTINELS = new Set(['', '-', '--', 'N/A', 'NA', 'NULL', 'NONE', '.', 'ORIGIN']);

export function isBlank(v) {
  if (v === null || v === undefined) return true;
  const s = String(v).trim().toUpperCase();
  return SENTINELS.has(s);
}

/** Null unless a real value. Keeps 'ORIGIN' out of key columns but callers that
 *  need the literal (tire ref_npbg) should read the raw cell instead. */
export function cleanKey(v) {
  return isBlank(v) ? null : String(v).trim();
}

export function cleanText(v) {
  if (v === null || v === undefined) return null;
  const s = String(v).replace(/\s+/g, ' ').trim();
  return s === '' ? null : s;
}

/** Full LEVEL-3 normalization key. */
export function descNorm(v) {
  if (v === null || v === undefined) return '';
  let s = String(v).toUpperCase();
  s = s.replace(/[""”“]/g, '"').replace(/[''’‘´`]/g, "'");
  s = s.replace(/ /g, ' ');
  s = s.replace(/REFURBHISED|REFUBISHED/g, 'REFURBISHED');
  s = s.replace(/\s*[×xX]\s*(?=\d)/g, ' X ');   // dimension separators around numbers
  s = s.replace(/\s*\/\s*/g, ' / ');
  s = s.replace(/\s*-\s*/g, ' - ');
  s = s.replace(/[^\w\s"'./%()-]/g, ' ');
  s = s.replace(/\s+/g, ' ').trim();
  s = s.replace(/[.\-\/\s]+$/, '').trim();
  return s;
}

/** Condition-tag-stripped key for LEVEL-3b matching. */
export function descCore(v) {
  let s = descNorm(v);
  // strip leading "(TAG) " groups
  let changed = true;
  while (changed) {
    changed = false;
    for (const tag of CONDITION_TAGS) {
      const re = new RegExp('^\\(?\\s*' + tag + '\\s*\\)?\\s*[-:]?\\s*');
      if (re.test(s)) { s = s.replace(re, ''); changed = true; }
    }
  }
  return s.replace(/\s+/g, ' ').trim();
}

/** parse "STOK 15 PCS" / "STOK O PCS" / "1,5" / 15 -> number | null */
export function parseStockNum(v) {
  if (v === null || v === undefined) return null;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  let s = String(v).trim();
  if (s === '') return null;
  s = s.toUpperCase().replace(/\bSTOK\b|\bSISA\b/g, ' ');
  // "STOK O PCS" -> O is a typo for 0 only when isolated between spaces/among digits
  s = s.replace(/(?<=\s|^)O(?=\s|$)/g, '0');
  const m = s.replace(/(\d)[.,](\d)/g, '$1.$2').match(/-?\d+(?:\.\d+)?/);
  return m ? parseFloat(m[0]) : null;
}

export function parseNum(v) {
  if (v === null || v === undefined || v === '') return null;
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  const s = String(v).trim();
  if (isBlank(s)) return null;
  const m = s.replace(/(\d)[.,](\d)/g, '$1.$2').replace(/[^0-9.\-]/g, ' ').match(/-?\d+(?:\.\d+)?/);
  return m ? parseFloat(m[0]) : null;
}

/** Excel/SheetJS gives Date objects for date cells (with a spurious LMT offset).
 *  Return YYYY-MM-DD in Asia/Jakarta by rounding to nearest local day. */
export function parseDateISO(v) {
  if (v === null || v === undefined || v === '') return null;
  if (v instanceof Date && !isNaN(v)) {
    const t = new Date(v.getTime() + 7 * 3600 * 1000); // shift to WIB
    return t.toISOString().slice(0, 10);
  }
  const s = String(v).trim();
  if (isBlank(s)) return null;
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[1]}-${m[2]}-${m[3]}`;
  m = s.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})/);
  if (m) {
    let [_, d, mo, y] = m;
    if (y.length === 2) y = '20' + y;
    return `${y}-${String(mo).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
  }
  return null;
}

export function parseBool(v) {
  if (v === null || v === undefined || v === '') return null;
  const s = String(v).trim().toUpperCase();
  if (['YA', 'Y', 'YES', 'TRUE', '1', 'PERLU'].includes(s)) return 1;
  if (['TIDAK', 'T', 'NO', 'FALSE', '0'].includes(s)) return 0;
  return null;
}

export function rowHash(parts) {
  return crypto.createHash('sha1').update(parts.map(p => (p === null || p === undefined ? '' : String(p))).join('|')).digest('hex');
}

/** token set Jaccard for cheap fuzzy (no external lib) */
export function tokenJaccard(a, b) {
  const ta = new Set(descCore(a).split(' ').filter(Boolean));
  const tb = new Set(descCore(b).split(' ').filter(Boolean));
  if (!ta.size || !tb.size) return 0;
  let inter = 0;
  for (const t of ta) if (tb.has(t)) inter++;
  return inter / (ta.size + tb.size - inter);
}
