// keccak256, for EIP-55 address checksums.
//
// Needed because eth.py refuses an address whose checksum does not match its
// capitalisation, and a dApp hands out lowercase addresses. Vendored for the
// same reason as qr.js: an MV3 extension cannot pull a hash function off a CDN.
//
// Lanes are kept as 32-bit halves rather than BigInt -- correctness is easier
// to see and it is roughly an order of magnitude faster.

const RC = [
  [0x00000001,0x00000000],[0x00008082,0x00000000],[0x0000808a,0x80000000],
  [0x80008000,0x80000000],[0x0000808b,0x00000000],[0x80000001,0x00000000],
  [0x80008081,0x80000000],[0x00008009,0x80000000],[0x0000008a,0x00000000],
  [0x00000088,0x00000000],[0x80008009,0x00000000],[0x8000000a,0x00000000],
  [0x8000808b,0x00000000],[0x0000008b,0x80000000],[0x00008089,0x80000000],
  [0x00008003,0x80000000],[0x00008002,0x80000000],[0x00000080,0x80000000],
  [0x0000800a,0x00000000],[0x8000000a,0x80000000],[0x80008081,0x80000000],
  [0x00008080,0x80000000],[0x80000001,0x00000000],[0x80008008,0x80000000],
];
const R = [0,1,62,28,27,36,44,6,55,20,3,10,43,25,39,41,45,15,21,8,18,2,61,56,14];

function keccakF(s) {                       // s: Int32Array(50), lo,hi pairs
  const C = new Int32Array(10), D = new Int32Array(10);
  for (let round = 0; round < 24; round++) {
    for (let x = 0; x < 5; x++) {
      C[x*2] = s[x*2] ^ s[(x+5)*2] ^ s[(x+10)*2] ^ s[(x+15)*2] ^ s[(x+20)*2];
      C[x*2+1] = s[x*2+1] ^ s[(x+5)*2+1] ^ s[(x+10)*2+1] ^ s[(x+15)*2+1] ^ s[(x+20)*2+1];
    }
    for (let x = 0; x < 5; x++) {
      const a = (x+4)%5, b = (x+1)%5;
      const lo = C[b*2], hi = C[b*2+1];
      D[x*2]   = C[a*2]   ^ ((lo << 1) | (hi >>> 31));
      D[x*2+1] = C[a*2+1] ^ ((hi << 1) | (lo >>> 31));
    }
    for (let x = 0; x < 5; x++) for (let y = 0; y < 5; y++) {
      s[(x+5*y)*2]   ^= D[x*2];
      s[(x+5*y)*2+1] ^= D[x*2+1];
    }
    // rho + pi
    const B = new Int32Array(50);
    for (let x = 0; x < 5; x++) for (let y = 0; y < 5; y++) {
      const i = x + 5*y, j = y + 5*((2*x + 3*y) % 5), n = R[i];
      let lo = s[i*2], hi = s[i*2+1];
      if (n) {
        if (n < 32) { const t = lo; lo = (lo << n) | (hi >>> (32-n)); hi = (hi << n) | (t >>> (32-n)); }
        else if (n === 32) { const t = lo; lo = hi; hi = t; }
        else { const m = n - 32, t = lo; lo = (hi << m) | (lo >>> (64-n)); hi = (t << m) | (hi >>> (64-n)); }
      }
      B[j*2] = lo; B[j*2+1] = hi;
    }
    // chi
    for (let y = 0; y < 5; y++) for (let x = 0; x < 5; x++) {
      const i = (x + 5*y)*2, n1 = ((x+1)%5 + 5*y)*2, n2 = ((x+2)%5 + 5*y)*2;
      s[i]   = B[i]   ^ (~B[n1]   & B[n2]);
      s[i+1] = B[i+1] ^ (~B[n1+1] & B[n2+1]);
    }
    s[0] ^= RC[round][0];
    s[1] ^= RC[round][1];
  }
}

/** keccak256 of a byte array -> Uint8Array(32). */
export function keccak256(bytes) {
  const RATE = 136;                          // 1088 bits
  const s = new Int32Array(50);
  const padded = new Uint8Array(Math.ceil((bytes.length + 1) / RATE) * RATE);
  padded.set(bytes);
  padded[bytes.length] = 0x01;               // keccak padding, NOT SHA3's 0x06
  padded[padded.length - 1] |= 0x80;
  for (let off = 0; off < padded.length; off += RATE) {
    for (let i = 0; i < RATE / 8; i++) {
      const b = off + i * 8;
      s[i*2]   ^= padded[b] | (padded[b+1]<<8) | (padded[b+2]<<16) | (padded[b+3]<<24);
      s[i*2+1] ^= padded[b+4] | (padded[b+5]<<8) | (padded[b+6]<<16) | (padded[b+7]<<24);
    }
    keccakF(s);
  }
  const out = new Uint8Array(32);
  for (let i = 0; i < 4; i++) {
    for (let k = 0; k < 4; k++) {
      out[i*8+k]   = (s[i*2]   >>> (8*k)) & 0xff;
      out[i*8+4+k] = (s[i*2+1] >>> (8*k)) & 0xff;
    }
  }
  return out;
}

export const keccakHex = (bytes) =>
  [...keccak256(bytes)].map(b => b.toString(16).padStart(2, "0")).join("");

/** EIP-55: capitalise a hex digit when the matching hash nibble is >= 8. */
export function toChecksumAddress(addr) {
  const a = addr.toLowerCase().replace(/^0x/, "");
  if (!/^[0-9a-f]{40}$/.test(a)) throw new Error(`not an address: ${addr}`);
  const h = keccakHex(new TextEncoder().encode(a));
  let out = "0x";
  for (let i = 0; i < 40; i++)
    out += parseInt(h[i], 16) >= 8 ? a[i].toUpperCase() : a[i];
  return out;
}
