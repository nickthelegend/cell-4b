// Byte-mode QR encoder. Versions 1-20, EC level L and M.
//
// Vendored rather than imported: an MV3 extension cannot load script from a
// CDN, and a QR code that will not scan is the worst failure this bridge has
// -- it fails at the bench, holding a lancet, with no way to tell whether the
// encoder or the camera is wrong. So this is self-contained and round-trip
// tested against the browser's own BarcodeDetector in qr.test.html.

const EXP = new Uint8Array(512), LOG = new Uint8Array(256);
(function () {                                   // GF(256), primitive poly 0x11D
  let x = 1;
  for (let i = 0; i < 255; i++) {
    EXP[i] = x; LOG[x] = i;
    x <<= 1; if (x & 0x100) x ^= 0x11D;
  }
  for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
})();
const mul = (a, b) => (a === 0 || b === 0) ? 0 : EXP[LOG[a] + LOG[b]];

function rsGenerator(n) {
  let poly = [1];
  for (let i = 0; i < n; i++) {
    const next = new Array(poly.length + 1).fill(0);
    for (let j = 0; j < poly.length; j++) {
      next[j] ^= poly[j];
      next[j + 1] ^= mul(poly[j], EXP[i]);
    }
    poly = next;
  }
  return poly;
}

export function rsEncode(data, ecLen) {
  const gen = rsGenerator(ecLen);
  const res = new Uint8Array(data.length + ecLen);
  res.set(data);
  for (let i = 0; i < data.length; i++) {
    const factor = res[i];
    if (factor === 0) continue;
    for (let j = 0; j < gen.length; j++) res[i + j] ^= mul(gen[j], factor);
  }
  return res.slice(data.length);
}

// [total codewords, ecPerBlock, group1Blocks, group1Data, group2Blocks, group2Data]
// Versions 1-20. Index 0 = level L, index 1 = level M.
const SPEC = {
  1:  [[26,7,1,19,0,0],        [26,10,1,16,0,0]],
  2:  [[44,10,1,34,0,0],       [44,16,1,28,0,0]],
  3:  [[70,15,1,55,0,0],       [70,26,1,44,0,0]],
  4:  [[100,20,1,80,0,0],      [100,18,2,32,0,0]],
  5:  [[134,26,1,108,0,0],     [134,24,2,43,0,0]],
  6:  [[172,18,2,68,0,0],      [172,16,4,27,0,0]],
  7:  [[196,20,2,78,0,0],      [196,18,4,31,0,0]],
  8:  [[242,24,2,97,0,0],      [242,22,2,38,2,39]],
  9:  [[292,30,2,116,0,0],     [292,22,3,36,2,37]],
  10: [[346,18,2,68,2,69],     [346,26,4,43,1,44]],
  11: [[404,20,4,81,0,0],      [404,30,1,50,4,51]],
  12: [[466,24,2,92,2,93],     [466,22,6,36,2,37]],
  13: [[532,26,4,107,0,0],     [532,22,8,37,1,38]],
  14: [[581,30,3,115,1,116],   [581,24,4,40,5,41]],
  15: [[655,22,5,87,1,88],     [655,24,5,41,5,42]],
  16: [[733,24,5,98,1,99],     [733,28,7,45,3,46]],
  17: [[815,28,1,107,5,108],   [815,28,10,46,1,47]],
  18: [[901,30,5,120,1,121],   [901,26,9,43,4,44]],
  19: [[991,28,3,113,4,114],   [991,26,3,44,11,45]],
  20: [[1085,28,3,107,5,108],  [1085,26,3,41,13,42]],
};

const ALIGN = {
  1: [], 2: [6,18], 3: [6,22], 4: [6,26], 5: [6,30], 6: [6,34],
  7: [6,22,38], 8: [6,24,42], 9: [6,26,46], 10: [6,28,50], 11: [6,30,54],
  12: [6,32,58], 13: [6,34,62], 14: [6,26,46,66], 15: [6,26,48,70],
  16: [6,26,50,74], 17: [6,30,54,78], 18: [6,30,56,82], 19: [6,30,58,86],
  20: [6,34,62,90],
};

function capacity(version, level) {
  const s = SPEC[version][level];
  return s[2] * s[3] + s[4] * s[5];
}

export function buildCodewords(bytes, version, level) {
  const s = SPEC[version][level];
  const [, ecLen, g1n, g1d, g2n, g2d] = s;
  const total = capacity(version, level);

  // mode (0100) + length + payload + terminator, then pad
  const bits = [];
  const push = (val, len) => { for (let i = len - 1; i >= 0; i--) bits.push((val >> i) & 1); };
  push(0b0100, 4);
  push(bytes.length, version >= 10 ? 16 : 8);
  for (const b of bytes) push(b, 8);
  for (let i = 0; i < 4 && bits.length < total * 8; i++) bits.push(0);
  while (bits.length % 8) bits.push(0);
  const data = [];
  for (let i = 0; i < bits.length; i += 8) {
    let v = 0; for (let j = 0; j < 8; j++) v = (v << 1) | bits[i + j];
    data.push(v);
  }
  const PAD = [0xEC, 0x11];
  for (let i = 0; data.length < total; i++) data.push(PAD[i % 2]);

  // split into blocks, interleave data then ec
  const blocks = [], ecs = [];
  let p = 0;
  for (let i = 0; i < g1n; i++) { const b = data.slice(p, p + g1d); p += g1d; blocks.push(b); ecs.push(rsEncode(b, ecLen)); }
  for (let i = 0; i < g2n; i++) { const b = data.slice(p, p + g2d); p += g2d; blocks.push(b); ecs.push(rsEncode(b, ecLen)); }

  const out = [];
  const maxData = Math.max(g1d, g2d || 0);
  for (let i = 0; i < maxData; i++)
    for (const b of blocks) if (i < b.length) out.push(b[i]);
  for (let i = 0; i < ecLen; i++)
    for (const e of ecs) out.push(e[i]);
  return out;
}

// ---------------------------------------------------------------- matrix ----

const FORMAT_BITS = (level, mask) => {          // BCH(15,5) + the 0x5412 mask
  const LEVEL_BITS = [0b01, 0b00];              // L=01, M=00
  let v = (LEVEL_BITS[level] << 3) | mask;
  let d = v << 10;
  for (let i = 4; i >= 0; i--) if (d & (1 << (i + 10))) d ^= 0x537 << i;
  return ((v << 10) | d) ^ 0x5412;
};

const VERSION_BITS = (version) => {             // BCH(18,6), v7+
  let d = version << 12;
  for (let i = 5; i >= 0; i--) if (d & (1 << (i + 12))) d ^= 0x1F25 << i;
  return (version << 12) | d;
};

const MASKS = [
  (r, c) => (r + c) % 2 === 0,
  (r) => r % 2 === 0,
  (r, c) => c % 3 === 0,
  (r, c) => (r + c) % 3 === 0,
  (r, c) => (Math.floor(r / 2) + Math.floor(c / 3)) % 2 === 0,
  (r, c) => ((r * c) % 2) + ((r * c) % 3) === 0,
  (r, c) => (((r * c) % 2) + ((r * c) % 3)) % 2 === 0,
  (r, c) => (((r + c) % 2) + ((r * c) % 3)) % 2 === 0,
];

function place(version, level, codewords, mask) {
  const n = version * 4 + 17;
  const m = Array.from({ length: n }, () => new Int8Array(n).fill(-1));
  const set = (r, c, v) => { if (r >= 0 && r < n && c >= 0 && c < n) m[r][c] = v; };

  const finder = (r0, c0) => {
    for (let r = -1; r <= 7; r++) for (let c = -1; c <= 7; c++) {
      const inner = r >= 0 && r <= 6 && c >= 0 && c <= 6;
      const ring = r === 0 || r === 6 || c === 0 || c === 6;
      const core = r >= 2 && r <= 4 && c >= 2 && c <= 4;
      set(r0 + r, c0 + c, inner && (ring || core) ? 1 : 0);
    }
  };
  finder(0, 0); finder(0, n - 7); finder(n - 7, 0);

  for (let i = 8; i < n - 8; i++) {             // timing
    const v = i % 2 === 0 ? 1 : 0;
    m[6][i] = v; m[i][6] = v;
  }

  for (const r of ALIGN[version]) for (const c of ALIGN[version]) {
    if ((r <= 8 && c <= 8) || (r <= 8 && c >= n - 9) || (r >= n - 9 && c <= 8)) continue;
    for (let dr = -2; dr <= 2; dr++) for (let dc = -2; dc <= 2; dc++)
      set(r + dr, c + dc, (Math.abs(dr) === 2 || Math.abs(dc) === 2 || (dr === 0 && dc === 0)) ? 1 : 0);
  }

  m[n - 8][8] = 1;                              // the always-dark module

  // reserve format areas so data skips them
  for (let i = 0; i < 9; i++) { if (m[8][i] === -1) m[8][i] = 0; if (m[i][8] === -1) m[i][8] = 0; }
  for (let i = 0; i < 8; i++) { if (m[8][n - 1 - i] === -1) m[8][n - 1 - i] = 0; if (m[n - 1 - i][8] === -1) m[n - 1 - i][8] = 0; }
  const reserved = m.map(row => Array.from(row, v => v !== -1));

  if (version >= 7) {
    const vb = VERSION_BITS(version);
    for (let i = 0; i < 18; i++) {
      const bit = (vb >> i) & 1, r = Math.floor(i / 3), c = i % 3;
      m[r][n - 11 + c] = bit; m[n - 11 + c][r] = bit;
      reserved[r][n - 11 + c] = true; reserved[n - 11 + c][r] = true;
    }
  }

  // zigzag, right to left, skipping the vertical timing column
  let bitIdx = 0, upward = true;
  for (let right = n - 1; right > 0; right -= 2) {
    if (right === 6) right = 5;
    for (let step = 0; step < n; step++) {
      const r = upward ? n - 1 - step : step;
      for (const c of [right, right - 1]) {
        if (reserved[r][c]) continue;
        let bit = 0;
        if (bitIdx < codewords.length * 8) {
          bit = (codewords[bitIdx >> 3] >> (7 - (bitIdx & 7))) & 1;
          bitIdx++;
        }
        m[r][c] = MASKS[mask](r, c) ? bit ^ 1 : bit;
      }
    }
    upward = !upward;
  }

  const fb = FORMAT_BITS(level, mask);
  for (let i = 0; i < 15; i++) {
    // MSB first: position i in the placement order carries bit 14-i, so (8,0)
    // and (n-1,8) both hold the most significant bit. Writing it LSB-first
    // lays the whole 15-bit string down backwards -- which still looks like a
    // plausible QR code and decodes as nothing at all.
    const bit = (fb >> (14 - i)) & 1;
    if (i < 6) m[8][i] = bit;
    else if (i === 6) m[8][7] = bit;
    else if (i === 7) m[8][8] = bit;
    else if (i === 8) m[7][8] = bit;
    else m[14 - i][8] = bit;
    // Second copy: bits 0-6 climb the left column from the bottom, bits 7-14
    // run along row 8 to the right edge. Bit 7 must land at column n-8, NOT
    // row n-8 -- that cell is the always-dark module, and writing format data
    // over it shifts every remaining bit by one and the code stops decoding.
    if (i < 7) m[n - 1 - i][8] = bit;
    else m[8][n - 15 + i] = bit;
  }
  return m;
}

function penalty(m) {
  const n = m.length; let score = 0;
  const run = (get) => {
    for (let a = 0; a < n; a++) {
      let last = -1, len = 0;
      for (let b = 0; b < n; b++) {
        const v = get(a, b);
        if (v === last) { len++; if (len === 5) score += 3; else if (len > 5) score += 1; }
        else { last = v; len = 1; }
      }
    }
  };
  run((r, c) => m[r][c]); run((r, c) => m[c][r]);
  for (let r = 0; r < n - 1; r++) for (let c = 0; c < n - 1; c++)
    if (m[r][c] === m[r][c + 1] && m[r][c] === m[r + 1][c] && m[r][c] === m[r + 1][c + 1]) score += 3;
  const PAT = [1,0,1,1,1,0,1,0,0,0,0];
  const hit = (get, a, b) => { for (let i = 0; i < 11; i++) if (get(a, b + i) !== PAT[i]) return false; return true; };
  for (let a = 0; a < n; a++) for (let b = 0; b <= n - 11; b++) {
    if (hit((x, y) => m[x][y], a, b)) score += 40;
    if (hit((x, y) => m[y][x], a, b)) score += 40;
  }
  let dark = 0;
  for (const row of m) for (const v of row) dark += v;
  score += Math.floor(Math.abs(dark * 100 / (n * n) - 50) / 5) * 10;
  return score;
}

/** Encode a string as a QR module matrix (array of arrays of 0/1). */
export function encodeQR(text, level = 0, forceMask = null) {
  const bytes = new TextEncoder().encode(text);
  let version = 0;
  for (let v = 1; v <= 20; v++) {
    const headerBytes = v >= 10 ? 3 : 2;        // mode+len rounded to bytes
    if (capacity(v, level) >= bytes.length + headerBytes) { version = v; break; }
  }
  if (!version) throw new Error(`payload too large for v20: ${bytes.length} bytes`);
  const cw = buildCodewords(bytes, version, level);
  let best = null, bestScore = Infinity;
  for (let mask = forceMask === null ? 0 : forceMask;
       mask < (forceMask === null ? 8 : forceMask + 1); mask++) {
    const m = place(version, level, cw, mask);
    const s = penalty(m);
    if (s < bestScore) { bestScore = s; best = m; }
  }
  return best;
}

/** Render a matrix to an SVG path string sized in modules. */
export function matrixToSVG(m, quiet = 4) {
  const n = m.length, size = n + quiet * 2;
  let d = "";
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++)
    if (m[r][c]) d += `M${c + quiet} ${r + quiet}h1v1h-1z`;
  return { size, path: d };
}
