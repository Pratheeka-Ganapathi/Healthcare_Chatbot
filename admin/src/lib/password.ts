// No look-alike characters (0/O, 1/l/I) so the password can be read out or copied by hand.
const ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";

export function generatePassword(length = 12): string {
  const bytes = new Uint32Array(length);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (n) => ALPHABET.charAt(n % ALPHABET.length)).join("");
}

export const MIN_PASSWORD_LENGTH = 8;
