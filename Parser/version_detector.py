"""Cross-platform V8 code-cache (.jsc) version detector.

Replaces the Windows-only VersionDetector.exe, which cannot run on Linux and
only knows the legacy version-hash algorithm.

V8 stores a version hash in the header of serialized code caches. Two
generations of the algorithm exist:

* Legacy (up to ~V8 13.x): ``Version::Hash()`` used the variadic
  ``base::hash_combine(major, minor, build, patch)`` which folds its
  arguments right-to-left and hashes ints with Thomas Wang's 32-bit mix.
* Modern (V8 14.x transition window): ``base::Hasher`` folds left-to-right;
  later revisions also append the embedder string (e.g. "-electron.0").

The header starts with the magic number ``0xC0DE0000 ^ kSize`` where kSize is
the ExternalReferenceTable size of the producing build - a useful hint when
the exact version was edited by the embedder.
"""

import struct

MASK32 = 0xFFFFFFFF
MASK64 = 0xFFFFFFFFFFFFFFFF
M = 0xC6A4A7935BD1E995

# (major, minor, build, patch) search space.
RANGES = range(4, 17), range(0, 16), range(0, 430), range(0, 70)
# When hashing includes an embedder string, the pinned V8 versions used by
# node/electron live in a much narrower space.
EMBEDDER_RANGES = range(9, 17), range(0, 10), range(100, 330), range(0, 40)
EMBEDDERS = ("", "-electron.0", "-electron", "-node")


def _tw32(v):
    # Thomas Wang 32-bit integer mix.
    v = (~v + (v << 15)) & MASK32
    v ^= v >> 12
    v = (v + (v << 2)) & MASK32
    v ^= v >> 4
    v = (v * 2057) & MASK32
    v ^= v >> 16
    return v


def _hc(seed, value):
    # v8::base::hash_combine(seed, hash) - 64-bit host variant (MurmurHash).
    value = (value * M) & MASK64
    value ^= value >> 47
    value = (value * M) & MASK64
    seed ^= value
    return (seed * M) & MASK64


def legacy_hash(major, minor, build, patch):
    """Version::Hash() up to ~V8 13.x (right-to-left fold, no embedder)."""
    seed = _hc(0, _tw32(patch))
    seed = _hc(seed, _tw32(build))
    seed = _hc(seed, _tw32(minor))
    seed = _hc(seed, _tw32(major))
    return seed & MASK32


def modern_hash(major, minor, build, patch, embedder=""):
    """base::Hasher-based Version::Hash() (left-to-right fold)."""
    seed = 0
    seed = _hc(seed, _tw32(major))
    seed = _hc(seed, _tw32(minor))
    seed = _hc(seed, _tw32(build))
    seed = _hc(seed, _tw32(patch))
    for ch in embedder.encode("latin-1"):
        seed = _hc(seed, ch)
    return seed & MASK32


def _brute_legacy(target, ranges):
    """Legacy fold order: patch, build, minor, major."""
    majors, minors, builds, patches = ranges
    for patch in patches:
        s1 = _hc(0, _tw32(patch))
        for build in builds:
            s2 = _hc(s1, _tw32(build))
            for minor in minors:
                s3 = _hc(s2, _tw32(minor))
                for major in majors:
                    if _hc(s3, _tw32(major)) & MASK32 == target:
                        return (major, minor, build, patch), ""
    return None, None


def _brute_modern(target, ranges, embedders=("",)):
    """Modern fold order: major, minor, build, patch, then embedder chars."""
    majors, minors, builds, patches = ranges
    for major in majors:
        s1 = _hc(0, _tw32(major))
        for minor in minors:
            s2 = _hc(s1, _tw32(minor))
            for build in builds:
                s3 = _hc(s2, _tw32(build))
                for patch in patches:
                    s4 = _hc(s3, _tw32(patch))
                    if s4 & MASK32 == target:
                        return (major, minor, build, patch), ""
                    for embedder in embedders:
                        s = s4
                        for ch in embedder.encode("latin-1"):
                            s = _hc(s, ch)
                        if s & MASK32 == target:
                            return (major, minor, build, patch), embedder
    return None, None


def hash_to_version(target_hash):
    """Brute-force a version string for a version hash, or None."""
    version, _ = _brute_legacy(target_hash, RANGES)
    if version is not None:
        return ".".join(map(str, version))
    version, embedder = _brute_modern(target_hash, RANGES)
    if version is not None:
        return ".".join(map(str, version)) + embedder
    version, embedder = _brute_modern(
        target_hash, EMBEDDER_RANGES,
        embedders=tuple(e for e in EMBEDDERS if e))
    if version is not None:
        return ".".join(map(str, version)) + embedder
    return None


def read_header(file_name):
    with open(file_name, "rb") as f:
        header = f.read(8)
    if len(header) < 8:
        raise ValueError(f"{file_name} is too small to be a V8 code cache.")
    magic, version_hash = struct.unpack("<II", header)
    if (magic & 0xFFFF0000) != 0xC0DE0000:
        raise ValueError(
            f"{file_name} has bad magic 0x{magic:08X} - not a V8 code cache.")
    return magic, version_hash


def detect_file_version(file_name):
    """Return the V8 version string for a .jsc file (e.g. '15.0.245.31')."""
    magic, version_hash = read_header(file_name)
    ksize = magic ^ 0xC0DE0000
    print(f"Version hash: 0x{version_hash:08X}, external reference count: {ksize}.")
    version = hash_to_version(version_hash)
    if version is None:
        raise RuntimeError(
            f"Could not brute-force version for hash 0x{version_hash:08X}. "
            "The V8 build was probably customized; pick the closest version.")
    return version


if __name__ == "__main__":
    import sys
    print(detect_file_version(sys.argv[1]))
