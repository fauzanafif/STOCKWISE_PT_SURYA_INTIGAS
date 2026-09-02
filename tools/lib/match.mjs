// Matching engine. Hierarchy: EXACT kode -> alias -> exact norm desc -> exact core desc -> fuzzy token.
// Fuzzy NEVER auto-resolves to MATCHED (RULE 8) — it produces POSSIBLE_MATCH / NEED_REVIEW.
import { descNorm, descCore } from './textnorm.mjs';

export const FUZZY_STRONG = 0.90;   // -> POSSIBLE_MATCH
export const FUZZY_WEAK = 0.75;     // -> NEED_REVIEW  (below -> NEW_ITEM)
const COMMON_TOKEN_MAX = 600;       // skip ultra-common tokens when gathering candidates
const MAX_CANDIDATES = 1200;        // hard cap on masters scored per lookup

export function buildMasterIndex(masters) {
  const byKode = new Map();
  const byNorm = new Map();
  const byCore = new Map();
  const tokenIndex = new Map();      // token -> Set(masterArrayIndex)
  const coreTokens = [];             // parallel to masters: Set<string>
  const byId = new Map(masters.map((m) => [m.id, m]));
  masters.forEach((m, idx) => {
    if (m.kode_barang) push(byKode, m.kode_barang.toUpperCase(), m.id);
    if (m.deskripsi_norm) push(byNorm, m.deskripsi_norm, m.id);
    const core = m.deskripsi_core || descCore(m.deskripsi);
    if (core) push(byCore, core, m.id);
    const toks = new Set(core.split(' ').filter(Boolean));
    coreTokens[idx] = toks;
    for (const tok of toks) {
      if (!tokenIndex.has(tok)) tokenIndex.set(tok, new Set());
      tokenIndex.get(tok).add(idx);
    }
  });
  return { masters, byId, byKode, byNorm, byCore, tokenIndex, coreTokens };
}

function push(map, k, v) { if (!map.has(k)) map.set(k, []); map.get(k).push(v); }

export function resolve(idx, rawDesc, { kode = null } = {}) {
  const norm = descNorm(rawDesc);
  const core = descCore(rawDesc);
  if (!norm) return { status: 'NEW_ITEM', master_item_id: null, method: 'EMPTY', confidence: 0, candidates: [] };

  if (kode && idx.byKode.has(String(kode).toUpperCase())) {
    const ids = idx.byKode.get(String(kode).toUpperCase());
    if (ids.length === 1) return done(idx, 'MATCHED', ids[0], 'EXACT_KODE', 1.0);
  }
  if (idx.byNorm.has(norm)) {
    const ids = idx.byNorm.get(norm);
    if (ids.length === 1) return done(idx, 'MATCHED', ids[0], 'EXACT_NORM', 1.0);
    return possible(idx, ids, 'EXACT_NORM', 0.85);
  }
  if (idx.byCore.has(core)) {
    const ids = idx.byCore.get(core);
    if (ids.length === 1) return done(idx, 'MATCHED', ids[0], 'EXACT_CORE', 0.95);
    return possible(idx, ids, 'EXACT_CORE', 0.8);
  }

  // fuzzy: gather candidates from shared (non-common) tokens, score by token Jaccard
  const qtoks = new Set(core.split(' ').filter(Boolean));
  if (!qtoks.size) return { status: 'NEW_ITEM', master_item_id: null, method: 'NONE', confidence: 0, candidates: [] };
  const freq = [...qtoks].map((t) => [t, idx.tokenIndex.get(t)?.size || 0]).sort((a, b) => a[1] - b[1]);
  const cand = new Set();
  for (const [t, n] of freq) {
    if (n === 0 || n > COMMON_TOKEN_MAX) continue;
    for (const i of idx.tokenIndex.get(t)) { cand.add(i); if (cand.size >= MAX_CANDIDATES) break; }
    if (cand.size >= MAX_CANDIDATES) break;
  }
  if (!cand.size) {
    // fall back to the least-common token even if slightly over the cap
    const [t] = freq.find(([, n]) => n > 0) || [];
    if (t) { let c = 0; for (const i of idx.tokenIndex.get(t)) { cand.add(i); if (++c >= MAX_CANDIDATES) break; } }
  }

  const scored = [];
  for (const i of cand) {
    const mt = idx.coreTokens[i];
    let inter = 0;
    for (const t of qtoks) if (mt.has(t)) inter++;
    const c = inter / (qtoks.size + mt.size - inter);
    if (c >= FUZZY_WEAK) scored.push({ id: idx.masters[i].id, desc: idx.masters[i].deskripsi, confidence: round(c), method: 'FUZZY_TOKEN' });
  }
  scored.sort((a, b) => b.confidence - a.confidence);
  const top = scored.slice(0, 5);
  if (top.length && top[0].confidence >= FUZZY_STRONG)
    return { status: 'POSSIBLE_MATCH', master_item_id: null, method: 'FUZZY_TOKEN', confidence: top[0].confidence, candidates: top };
  if (top.length)
    return { status: 'NEED_REVIEW', master_item_id: null, method: 'FUZZY_TOKEN', confidence: top[0].confidence, candidates: top };
  return { status: 'NEW_ITEM', master_item_id: null, method: 'NONE', confidence: 0, candidates: [] };
}

function masterDesc(idx, id) { const m = idx.byId.get(id); return m ? m.deskripsi : null; }
function done(idx, status, id, method, confidence) {
  return { status, master_item_id: id, method, confidence, candidates: [{ id, desc: masterDesc(idx, id), confidence, method }] };
}
function possible(idx, ids, method, confidence) {
  return { status: 'POSSIBLE_MATCH', master_item_id: null, method, confidence,
    candidates: ids.slice(0, 5).map((id) => ({ id, desc: masterDesc(idx, id), confidence, method })) };
}
const round = (n) => Math.round(n * 100) / 100;
