from typing import Tuple

from pyaraucaria.coordinates import ra_to_decimal, dec_to_decimal


def split_radec(combined: str) -> Tuple[str, str]:
    """Split a combined "RA Dec" string into its RA and Dec substrings.

    Accepts comma-separated pairs, single space-separated pairs, and
    space-separated sexagesimal with internal spaces (e.g. "10 45 03.6 -59 41 04"),
    splitting the latter at the first token starting with a sign, falling back
    to an even 50/50 token split when no sign token is present.
    """
    s = combined.strip()
    if ',' in s:
        ra_str, dec_str = s.split(',', 1)
        return ra_str.strip(), dec_str.strip()

    tokens = s.split()
    if len(tokens) == 2:
        return tokens[0], tokens[1]

    for i in range(1, len(tokens)):
        if tokens[i][0] in '+-':
            return ' '.join(tokens[:i]), ' '.join(tokens[i:])

    if len(tokens) >= 2 and len(tokens) % 2 == 0:
        half = len(tokens) // 2
        return ' '.join(tokens[:half]), ' '.join(tokens[half:])

    raise ValueError(f"Could not split '{combined}' into RA and Dec parts")


def parse_radec(combined: str) -> Tuple[float, float]:
    """Parse a combined "RA Dec" string into (ra_deg, dec_deg) decimal degrees."""
    ra_str, dec_str = split_radec(combined)
    return ra_to_decimal(ra_str), dec_to_decimal(dec_str)
