"""
LDR calibration and value-to-distance conversion utilities.
"""

from typing import List, Optional

# Fixed mapping of indices 0..9 to distances in cm (now 3..30)
DISTANCES: List[int] = [3 * (i + 1) for i in range(10)]  # 3,6,...,30


class LDRCalibration:
    """
    Holds 10 calibration values, each corresponding to distances 3, 6, ..., 30 cm
    at indices 0..9 respectively. Provides fast value-to-distance conversion using
    binary search with linear interpolation.

        Assumptions (can be adapted):
        - Closer light source -> LOWER raw LDR reading (your note). That typically
            means values are NON-DECREASING as distance increases 5→50 cm. If your
            hardware is reversed, we detect and handle decreasing sequences too.
    """

    def __init__(self):
        self.values: List[Optional[int]] = [None] * 10
        self._count: int = 0
        # Cached, filled when calibration completes
        self._vals: Optional[List[int]] = None  # length-10 list of ints
        self._inc: Optional[bool] = None        # True if increasing with distance

    def add(self, idx: int, value: int) -> None:
        if 0 <= idx < 10:
            self.values[idx] = value
            self._count = sum(v is not None for v in self.values)
            if self._count == 10:
                self._finalize()

    def is_complete(self) -> bool:
        return self._count == 10

    def _finalize(self) -> None:
        """Cache integer list and monotonic direction for fast lookups."""
        # All None should be filled now
        self._vals = [int(v) for v in self.values]  # type: ignore
        # Determine monotonic direction by comparing endpoints
        try:
            self._inc = self._vals[9] >= self._vals[0]
        except Exception:
            self._inc = None

    def value_to_distance(self, ldr_value: int) -> Optional[float]:
        """
    Given a raw LDR value, return the interpolated distance in cm (4..40), or None if out of range
        or calibration incomplete.
        Complexity: O(log N) for search (N=10 here) without per-call sorting/allocations.
        """
        if not self.is_complete() or self._vals is None or self._inc is None:
            return None
        vals = self._vals
        inc = self._inc

        # Bounds check (out-of-range returns None to match previous behavior)
        if inc:
            if ldr_value < vals[0] or ldr_value > vals[9]:
                return None
        else:
            if ldr_value > vals[0] or ldr_value < vals[9]:
                return None

        # Binary search to find bracketing indices (i, j) such that vals[i] <= x <= vals[j] for increasing,
        # or vals[i] >= x >= vals[j] for decreasing. If exact match, i==j.
        lo, hi = 0, 9
        while lo <= hi:
            mid = (lo + hi) // 2
            vm = vals[mid]
            if vm == ldr_value:
                # Exact match
                return float(DISTANCES[mid])
            if inc:
                if vm < ldr_value:
                    lo = mid + 1
                else:
                    hi = mid - 1
            else:
                if vm > ldr_value:
                    lo = mid + 1
                else:
                    hi = mid - 1

        # Now hi < lo; hi is the lower index (or left), lo is the upper (or right) index in the sequence.
        i = hi
        j = lo
        # Guard rails (shouldn’t happen due to range check, but keep safe)
        if i < 0 or j > 9:
            return None

        v1, d1 = vals[i], DISTANCES[i]
        v2, d2 = vals[j], DISTANCES[j]
        if v1 == v2:
            return float(d1)

        # Linear interpolation between (v1,d1) and (v2,d2)
        return d1 + (d2 - d1) * (ldr_value - v1) / (v2 - v1)
