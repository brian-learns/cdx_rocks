return to [`cdx-rocks` database definition](./database_definition)

# struct_format

The `struct_format` key holds a Python [`struct`](https://docs.python.org/3/library/struct.html) format string. It is passed directly to `struct.pack()` and `struct.unpack()`.

## Format string structure

```
[byte_order][type][type][type]
```

Exactly **three** type characters, prefixed by one byte-order specifier. No spaces, no repeat counts, no other characters.

### Valid examples

| Format  | Meaning                                    | Packed size |
|---------|---------------------------------------------|-------------|
| `!IQI`  | Network order: unsigned int, unsigned long long, unsigned int | 16 bytes |
| `<BHI`  | Little-endian: unsigned char, unsigned short, unsigned int | 7 bytes |
| `>LQI`  | Big-endian: unsigned long, unsigned long long, unsigned int | 16 bytes |
| `@III`  | Native order (explicit): three unsigned ints | 12 bytes |

## Byte order prefix

| Prefix | Meaning                | Notes                                          |
|--------|------------------------|-------------------------------------------------|
| *(none)* | Native order          | Platform-dependent byte order and alignment     |
| `@`    | Native order           | Explicit native; same as no prefix              |
| `=`    | Native (standard size) | No padding, standard sizes                      |
| `<`    | Little-endian          | Smallest byte first                             |
| `>`    | Big-endian             | Largest byte first                              |
| `!`    | Network order          | Equivalent to `>` (big-endian, standard sizes)  |

## Type characters (unsigned integers only)

| Type | C Type         | Python Type | Size (bytes) | Value Range          |
|------|----------------|-------------|-------------|----------------------|
| `B`  | unsigned char  | int         | 1           | 0 – 255              |
| `H`  | unsigned short | int         | 2           | 0 – 65,535           |
| `I`  | unsigned int   | int         | 4           | 0 – 4,294,967,295    |
| `L`  | unsigned long  | int         | 4           | 0 – 4,294,967,295    |
| `Q`  | unsigned long long | int     | 8           | 0 – 18,446,744,073,709,551,615 |

## Disallowed

These are explicitly rejected by `validate_struct_format()`:

- **Signed types**: `b`, `h`, `i`, `l`, `q`
- **Floating point**: `f`, `d`
- **Strings**: `s` (can allocate arbitrary memory — security risk)
- **Padding**: `x`
- **Spaces**: `!I QI` is invalid
- **Repeat counts**: `3I` is invalid
- **Wrong count**: must be exactly 3 type characters
- **Missing prefix**: omitting prefix will be rejected

## Validation

Use `validate_struct_format()` before passing the format string to `struct.pack()`:

```python
from validate_struct_format import validate_struct_format, safe_pack

if validate_struct_format(fmt):
    data = safe_pack(fmt, v1, v2, v3)
```

## Common combinations

| Format  | Use case                           | Size  |
|---------|-------------------------------------|-------|
| `!IQI`  | 32-bit ID, 64-bit timestamp, 32-bit flags | 16 B |
| `<BHI`  | Version byte, port, IP address      | 7 B   |
| `>LQI`  | Counter, 64-bit sequence, checksum  | 16 B  |
| `!IIQ`  | Two 32-bit IDs, 64-bit size         | 16 B  |
| `@BHH`  | Three small fields (native order)   | 5 B   |

```python
"""Validate struct format strings: exactly 3 unsigned integer types, required byte-order prefix, no spaces."""

import struct

ALLOWED = set("BHILQ")
VALID_PREFIX = {"@", "=", "<", ">", "!"}

def validate_struct_format(fmt: str) -> bool:
    """Return True if fmt is exactly [prefix][type][type][type].

    Prefix is one of @, =, <, >, ! and is **required**. Each type is B/H/I/L/Q.
    Rejects spaces, repeat counts, other types, wrong length, missing prefix.
    """
    if not isinstance(fmt, str) or len(fmt) != 4:
        return False

    prefix = fmt[0]
    if prefix not in VALID_PREFIX:
        return False

    types = fmt[1:]

    if not all(c in ALLOWED for c in types):
        return False

    try:
        struct.calcsize(fmt)
    except struct.error:
        return False

    return True

def safe_pack(fmt: str, v1, v2, v3) -> bytes:
    """Pack 3 values with validated format. Raises ValueError if unsafe."""
    if not validate_struct_format(fmt):
        raise ValueError(f"Unsafe struct format: {fmt!r}")
    return struct.pack(fmt, v1, v2, v3)
```