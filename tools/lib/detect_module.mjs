// Guess which STOCKWISE module a workbook belongs to, from its filename and sheet names.
import { openWorkbook } from './sheet.mjs';
import path from 'node:path';

const RULES = [
  // [module, filename regex, sheet-name regex]
  ['master',        /\bdata\b|database\s*utama|master\s*inventory/i, /database\s*utama|safety\s*stock/i],
  ['procurement',   /ppb|\bri\b/i,                                   /^ppb$|^ri$|ppb\s*perubahan/i],
  ['npbg',          /npbg/i,                                         /^npbg$/i],
  ['borrow_lend',   /borrow|lend|pinjam/i,                           /^lend$|^borrow$/i],
  ['stpp',          /stpp/i,                                         /^stpp$/i],
  ['tire',          /ban\s*luar|tire|\bban\b/i,                      /ban\s*luar/i],
  ['asset_maint',   /maintenance\s*asset|maintenance\s*kendaraan/i,  /maintenance\s*kendaraan/i],
  ['manufacturing', /manufaktur|assembly|manufacturing/i,            /manufaktur\s*&\s*assembly|manufaktur\s*&\s*jasa/i],
  ['used_returns',  /pengembalian|bekas|used\s*return/i,             /^spare\s*part/i],
];

/** Returns { module, confidence: 'name'|'sheet'|'both'|null } */
export function detectModule(file) {
  const name = path.basename(file);
  let byName = null;
  for (const [mod, nameRe] of RULES) if (nameRe.test(name)) { byName = mod; break; }

  let bySheet = null;
  try {
    const wb = openWorkbook(file);
    const sheets = wb.SheetNames.join(' | ');
    for (const [mod, , sheetRe] of RULES) if (sheetRe.test(sheets)) { bySheet = mod; break; }
  } catch { /* unreadable — fall back to name */ }

  if (byName && bySheet) return { module: byName, confidence: byName === bySheet ? 'both' : 'name' };
  if (byName) return { module: byName, confidence: 'name' };
  if (bySheet) return { module: bySheet, confidence: 'sheet' };
  return { module: null, confidence: null };
}

// master must be ingested first so the matcher has something to match against
export const MODULE_ORDER = ['master', 'procurement', 'npbg', 'borrow_lend', 'stpp',
  'tire', 'asset_maint', 'manufacturing', 'used_returns'];
