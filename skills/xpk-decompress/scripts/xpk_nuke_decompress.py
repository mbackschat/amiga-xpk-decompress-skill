#!/usr/bin/env python3
"""
XPK/NUKE Decompressor — Amiga XPK packing library decompressor.

Supports NUKE and DUKE (NUKE + delta encoding) sub-packers.

Ported from the C++ reference implementation in temisu/ancient:
  https://github.com/temisu/ancient
  Copyright (C) Teemu Suutari — original C++ code (ISC license)

Usage:
  python xpk_nuke_decompress.py <file_or_directory> [--output DIR] [--dry-run]
"""

import argparse
import os
import struct
import sys
from pathlib import Path


# ── Stream helpers ──────────────────────────────────────────────────────────

class ForwardInputStream:
    """Reads bytes forward through a buffer. Linked to a BackwardInputStream."""

    def __init__(self, data: bytes):
        self._data = data
        self._offset = 0
        self._end = len(data)
        self._linked: "BackwardInputStream | None" = None

    def link(self, backward: "BackwardInputStream"):
        self._linked = backward

    def read_byte(self) -> int:
        if self._offset >= self._end:
            raise DecompressError("forward stream overrun")
        val = self._data[self._offset]
        self._offset += 1
        if self._linked:
            self._linked.set_end(self._offset)
        return val

    def read_be16(self) -> int:
        b1 = self.read_byte()
        b2 = self.read_byte()
        return (b1 << 8) | b2

    def read_be32(self) -> int:
        b1 = self.read_byte()
        b2 = self.read_byte()
        b3 = self.read_byte()
        b4 = self.read_byte()
        return (b1 << 24) | (b2 << 16) | (b3 << 8) | b4

    def set_end(self, offset: int):
        self._end = offset


class BackwardInputStream:
    """Reads bytes backward through a buffer. Linked to a ForwardInputStream."""

    def __init__(self, data: bytes):
        self._data = data
        self._offset = len(data)
        self._end = 0
        self._linked: ForwardInputStream | None = None

    def link(self, forward: ForwardInputStream):
        self._linked = forward

    def read_byte(self) -> int:
        if self._offset <= self._end:
            raise DecompressError("backward stream overrun")
        self._offset -= 1
        val = self._data[self._offset]
        if self._linked:
            self._linked.set_end(self._offset)
        return val

    def set_end(self, offset: int):
        self._end = offset


# ── Bit readers ─────────────────────────────────────────────────────────────

class MSBBitReader:
    """Reads bits MSB-first from a ForwardInputStream."""

    def __init__(self, stream: ForwardInputStream):
        self._stream = stream
        self._buf = 0
        self._bits = 0

    def read_bits_be16(self, count: int) -> int:
        ret = 0
        while count > 0:
            if self._bits == 0:
                self._buf = self._stream.read_be16()
                self._bits = 16
            take = min(count, self._bits)
            self._bits -= take
            ret = (ret << take) | ((self._buf >> self._bits) & ((1 << take) - 1))
            count -= take
        return ret


class LSBBitReader:
    """Reads bits LSB-first from a ForwardInputStream."""

    def __init__(self, stream: ForwardInputStream):
        self._stream = stream
        self._buf = 0
        self._bits = 0

    def read_bits_be32(self, count: int) -> int:
        ret = 0
        pos = 0
        while count > 0:
            if self._bits == 0:
                self._buf = self._stream.read_be32()
                self._bits = 32
            take = min(count, self._bits)
            ret |= (self._buf & ((1 << take) - 1)) << pos
            self._buf >>= take
            self._bits -= take
            count -= take
            pos += take
        return ret


# ── VLC decoder ─────────────────────────────────────────────────────────────

class VariableLengthCodeDecoder:
    """Variable-length code decoder, ported from ancient's template class."""

    def __init__(self, *args: int):
        self._bit_lengths: list[int] = []
        self._offsets: list[int] = []
        length = 0
        for a in args:
            if a < 0:
                self._bit_lengths.append(-a)
                self._offsets.append(0)
                length = 1 << (-a)
            else:
                self._bit_lengths.append(a)
                self._offsets.append(length)
                length += 1 << a

    def decode(self, bit_reader, base: int) -> int:
        if base >= len(self._bit_lengths):
            raise DecompressError(f"VLC base {base} out of range")
        return self._offsets[base] + bit_reader(self._bit_lengths[base])


# ── Output stream ───────────────────────────────────────────────────────────

class ForwardOutputStream:
    """Collects decompressed output with LZ77 back-reference copy support."""

    def __init__(self, size: int):
        self._buf = bytearray(size)
        self._offset = 0
        self._size = size

    def eof(self) -> bool:
        return self._offset >= self._size

    def write_byte(self, val: int):
        if self._offset >= self._size:
            raise DecompressError("output overflow")
        self._buf[self._offset] = val & 0xFF
        self._offset += 1

    def copy(self, distance: int, count: int):
        if distance < 1 or distance > self._offset:
            raise DecompressError(
                f"invalid copy distance={distance} at offset={self._offset}"
            )
        src = self._offset - distance
        for _ in range(count):
            if self._offset >= self._size:
                raise DecompressError("output overflow during copy")
            self._buf[self._offset] = self._buf[src]
            self._offset += 1
            src += 1

    def get_data(self) -> bytes:
        return bytes(self._buf)


# ── Exceptions ──────────────────────────────────────────────────────────────

class DecompressError(Exception):
    pass


class InvalidFormatError(Exception):
    pass


# ── NUKE chunk decompressor ────────────────────────────────────────────────

def decompress_nuke_chunk(packed_data: bytes, raw_size: int) -> bytes:
    """Decompress a single NUKE-compressed chunk."""
    fwd = ForwardInputStream(packed_data)
    bwd = BackwardInputStream(packed_data)
    fwd.link(bwd)
    bwd.link(fwd)

    bit1 = MSBBitReader(fwd)
    bit2 = MSBBitReader(fwd)
    bit4 = LSBBitReader(fwd)
    bitx = MSBBitReader(fwd)

    read_bit = lambda: bit1.read_bits_be16(1)
    read_2bits = lambda: bit2.read_bits_be16(2)
    read_4bits = lambda: bit4.read_bits_be32(4)
    read_bits = lambda count: bitx.read_bits_be16(count)
    read_byte = lambda: bwd.read_byte()

    out = ForwardOutputStream(raw_size)

    vlc = VariableLengthCodeDecoder(
        4, 6, 8, 9,
        -4, 7, 9, 11, 13, 14,
        -5, 7, 9, 11, 13, 14,
    )

    while True:
        if not read_bit():
            if read_bit():
                count = 1
            else:
                count = 0
                while True:
                    tmp = read_2bits()
                    if tmp:
                        count += 5 - tmp
                    else:
                        count += 3
                    if tmp:
                        break
            for _ in range(count):
                out.write_byte(read_byte())

        if out.eof():
            break

        distance_index = read_4bits()
        distance = vlc.decode(read_bits, distance_index)

        if distance_index < 4:
            count = 2
        elif distance_index < 10:
            count = 3
        else:
            count = read_2bits()
            if count == 0:
                count = 6
                while True:
                    tmp = read_4bits()
                    if tmp:
                        count += 16 - tmp
                    else:
                        count += 15
                    if tmp:
                        break
            else:
                count = 7 - count
        out.copy(distance, count)

    return out.get_data()


# ── DUKE delta decode ───────────────────────────────────────────────────────

def delta_decode(data: bytes) -> bytes:
    buf = bytearray(data)
    for i in range(1, len(buf)):
        buf[i] = (buf[i] + buf[i - 1]) & 0xFF
    return bytes(buf)


# ── XPK file-level decompressor ────────────────────────────────────────────

def validate_xpk_header(data: bytes) -> dict:
    """
    Validate and parse an XPK file header.
    Returns a dict with parsed fields, or raises InvalidFormatError.
    """
    if len(data) < 44:
        raise InvalidFormatError("file too small for XPK header")

    magic = data[0:4]
    if magic != b"XPKF":
        raise InvalidFormatError(f"not an XPK file (magic: {magic!r})")

    packed_size = struct.unpack(">I", data[4:8])[0]
    packer_type = data[8:12]
    raw_size = struct.unpack(">I", data[12:16])[0]
    preview = data[16:32]
    flags = data[32]
    long_headers = bool(flags & 1)
    has_password = bool(flags & 2)
    has_extra = bool(flags & 4)

    if packer_type not in (b"NUKE", b"DUKE"):
        raise InvalidFormatError(
            f"unsupported packer: {packer_type.decode('ascii', errors='replace')!r} "
            f"(only NUKE and DUKE are supported)"
        )

    if has_password:
        raise InvalidFormatError("password-protected XPK files are not supported")

    if packed_size + 8 > len(data):
        raise InvalidFormatError(
            f"file truncated: header says {packed_size + 8} bytes, got {len(data)}"
        )

    # Header checksum: XOR of bytes 0..35 must be 0
    xor_check = 0
    for i in range(36):
        xor_check ^= data[i]
    if xor_check != 0:
        raise InvalidFormatError(f"header checksum failed (XOR={xor_check:#04x})")

    header_size = 36
    if has_extra:
        header_size = 38 + struct.unpack(">H", data[36:38])[0]

    return {
        "packed_size": packed_size,
        "packer_type": packer_type,
        "raw_size": raw_size,
        "preview": preview,
        "long_headers": long_headers,
        "has_password": has_password,
        "header_size": header_size,
        "is_duke": packer_type == b"DUKE",
    }


def iter_chunks(data: bytes, info: dict):
    """Yield (chunk_type, chunk_data, raw_chunk_size) for each XPK chunk."""
    packed_size = info["packed_size"]
    long_headers = info["long_headers"]
    header_size = info["header_size"]
    chunk_hdr_len = 12 if long_headers else 8

    current = header_size
    file_end = packed_size + 8

    while current < file_end:
        if current + chunk_hdr_len > len(data):
            raise DecompressError("chunk header extends past end of file")

        chunk_type = data[current]

        if long_headers:
            cpacked = struct.unpack(">I", data[current + 4 : current + 8])[0]
            craw = struct.unpack(">I", data[current + 8 : current + 12])[0]
        else:
            cpacked = struct.unpack(">H", data[current + 4 : current + 6])[0]
            craw = struct.unpack(">H", data[current + 6 : current + 8])[0]

        chunk_data = data[current + chunk_hdr_len : current + chunk_hdr_len + cpacked]

        yield chunk_type, chunk_data, craw

        if chunk_type == 15:
            return

        # Advance: header + packed data padded to 4 bytes
        current += chunk_hdr_len + ((cpacked + 3) & ~3)

    raise DecompressError("no end-of-stream chunk (type 15) found")


def decompress_xpk(data: bytes) -> bytes:
    """Decompress an XPK/NUKE or XPK/DUKE file. Returns the raw data."""
    info = validate_xpk_header(data)
    raw_size = info["raw_size"]
    output = bytearray()

    for chunk_type, chunk_data, raw_chunk_size in iter_chunks(data, info):
        if chunk_type == 0:
            # Stored (raw)
            if len(chunk_data) != raw_chunk_size:
                raise DecompressError("raw chunk size mismatch")
            output.extend(chunk_data)
        elif chunk_type == 1:
            # Compressed
            decompressed = decompress_nuke_chunk(chunk_data, raw_chunk_size)
            output.extend(decompressed)
        elif chunk_type == 15:
            # End marker
            break
        else:
            raise DecompressError(f"unknown chunk type {chunk_type}")

    if len(output) != raw_size:
        raise DecompressError(
            f"output size mismatch: got {len(output)}, expected {raw_size}"
        )

    # Verify preview (first 16 bytes must match header preview field)
    preview_len = min(raw_size, 16)
    if output[:preview_len] != info["preview"][:preview_len]:
        raise DecompressError("preview verification failed")

    if info["is_duke"]:
        output = bytearray(delta_decode(bytes(output)))

    return bytes(output)


# ── File-level helpers ──────────────────────────────────────────────────────

def is_xpk_nuke_file(filepath: str) -> bool:
    """Quick header check: is this an XPKF file with NUKE or DUKE packer?"""
    try:
        with open(filepath, "rb") as f:
            hdr = f.read(12)
        if len(hdr) < 12:
            return False
        return hdr[0:4] == b"XPKF" and hdr[8:12] in (b"NUKE", b"DUKE")
    except OSError:
        return False


def decompress_file(src: str, dst: str, dry_run: bool = False) -> bool:
    """
    Decompress a single XPK/NUKE file.
    Returns True on success, False if the file is not XPK/NUKE.
    Raises on decompression errors.
    """
    if not is_xpk_nuke_file(src):
        return False

    with open(src, "rb") as f:
        data = f.read()

    info = validate_xpk_header(data)
    packer = info["packer_type"].decode("ascii")
    raw_size = info["raw_size"]
    packed_size = len(data)
    ratio = (packed_size / raw_size * 100) if raw_size else 0

    if dry_run:
        print(f"  [DRY-RUN] {src}")
        print(f"    Packer: {packer}, packed: {packed_size}, "
              f"unpacked: {raw_size} ({ratio:.1f}%)")
        return True

    result = decompress_xpk(data)

    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    with open(dst, "wb") as f:
        f.write(result)

    print(f"  OK {src} -> {dst}")
    print(f"     {packer}: {packed_size} -> {raw_size} bytes ({ratio:.1f}%)")
    return True


def process_path(
    src_path: str,
    output_dir: str | None = None,
    dry_run: bool = False,
    recursive: bool = True,
) -> tuple[int, int, int]:
    """
    Process a file or directory. Returns (found, decompressed, errors).
    """
    found = 0
    decompressed = 0
    errors = 0
    src = Path(src_path)

    if src.is_file():
        files = [src]
    elif src.is_dir():
        if recursive:
            files = sorted(src.rglob("*"))
        else:
            files = sorted(src.glob("*"))
        files = [f for f in files if f.is_file()]
    else:
        print(f"Error: {src_path} is not a file or directory", file=sys.stderr)
        return 0, 0, 1

    for filepath in files:
        if not is_xpk_nuke_file(str(filepath)):
            continue
        found += 1

        if output_dir:
            if src.is_dir():
                rel = filepath.relative_to(src)
            else:
                rel = filepath.name
            dst = str(Path(output_dir) / rel)
        else:
            # Decompress in place (overwrite original)
            dst = str(filepath)

        try:
            ok = decompress_file(str(filepath), dst, dry_run=dry_run)
            if ok:
                decompressed += 1
        except (DecompressError, InvalidFormatError) as e:
            print(f"  FAIL {filepath}: {e}", file=sys.stderr)
            errors += 1

    return found, decompressed, errors


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Decompress Amiga XPK/NUKE (and DUKE) compressed files."
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Files or directories to decompress",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output directory (default: decompress in place)",
    )
    parser.add_argument(
        "-n", "--dry-run",
        action="store_true",
        help="Show what would be decompressed without writing",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Don't recurse into subdirectories",
    )
    args = parser.parse_args()

    total_found = 0
    total_ok = 0
    total_err = 0

    for path in args.paths:
        f, d, e = process_path(
            path,
            output_dir=args.output,
            dry_run=args.dry_run,
            recursive=not args.no_recursive,
        )
        total_found += f
        total_ok += d
        total_err += e

    print(f"\nDone: {total_found} XPK/NUKE files found, "
          f"{total_ok} decompressed, {total_err} errors.")
    sys.exit(1 if total_err else 0)


if __name__ == "__main__":
    main()
