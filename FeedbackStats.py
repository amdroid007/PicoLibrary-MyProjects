"""
# FeedbackStats.py
# Tracks customer feedback (happy and unhappy counts) and computes
# satisfaction percentage and light display levels.
# Author: Jit Sengupta
"""

from Log import *

class FeedbackStats:
    """
    **FeedbackStats** keeps track of user feedback for a service or store.
    It records counts for both happy and unhappy responses, calculates overall
    satisfaction percentage, maps the percentage to a light level (e.g. for a NeoPixel
    or LED strip), and allows resetting the counters.

    Parameters:
    ----------
    max_levels : int, optional
        The maximum number of levels/LEDs for the light display (default: 16)

    Examples:
    ---------
    1. Basic feedback recording and percentage calculation:
       ```python
       stats = FeedbackStats()
       stats.add_happy()
       stats.add_happy()
       stats.add_unhappy()
       print(stats.calculate_percentage())  # 66.67
       print(stats.get_light_level())       # 11
       ```
    2. Resetting statistics:
       ```python
       stats.reset()
       print(stats.get_total_count())       # 0
       ```
    """

    def __init__(self, max_levels=16):
        """
        Constructor to initialize feedback counts to zero.

        Parameters:
        ----------
        max_levels : int, optional
            The maximum number of levels (default: 16)
        """
        self._happy_count = 0
        self._unhappy_count = 0
        self._max_levels = max_levels
        Log.i(f"FeedbackStats initialized (max_levels={max_levels})")

    @property
    def happy_count(self) -> int:
        """ Returns the current count of happy responses. """
        return self._happy_count

    @property
    def unhappy_count(self) -> int:
        """ Returns the current count of unhappy responses. """
        return self._unhappy_count

    def add_happy(self):
        """
        Record a happy feedback response and increment the happy count.

        Examples:
        ---------
        1. stats.add_happy()
        """
        self._happy_count += 1
        Log.i(f"FeedbackStats: Happy feedback added. Total happy: {self._happy_count}, unhappy: {self._unhappy_count}")

    def add_unhappy(self):
        """
        Record an unhappy feedback response and increment the unhappy count.

        Examples:
        ---------
        1. stats.add_unhappy()
        """
        self._unhappy_count += 1
        Log.i(f"FeedbackStats: Unhappy feedback added. Total happy: {self._happy_count}, unhappy: {self._unhappy_count}")

    def get_total_count(self) -> int:
        """
        Calculate and return the total number of feedback responses received.

        Returns:
        -------
        int
            Sum of happy and unhappy feedback responses.

        Examples:
        ---------
        1. total = stats.get_total_count()
        """
        total = self._happy_count + self._unhappy_count
        Log.d(f"FeedbackStats: Total count is {total}")
        return total

    def calculate_percentage(self) -> float:
        """
        Calculate and return the percentage of happy feedback out of total feedback.
        Returns 0.0 if no feedback has been recorded yet.

        Returns:
        -------
        float
            Percentage of happy feedback (0.0 to 100.0).

        Examples:
        ---------
        1. pct = stats.calculate_percentage()
        """
        total = self.get_total_count()
        if total == 0:
            return 0.0
        pct = round((self._happy_count / total) * 100.0, 2)
        Log.d(f"FeedbackStats: Calculated percentage is {pct}%")
        return pct

    def get_light_level(self, max_levels=None) -> int:
        """
        Compute the number of LEDs or levels to illuminate based on the
        current happy feedback percentage.

        Parameters:
        ----------
        max_levels : int, optional
            The maximum number of levels/LEDs to scale to. If None, uses the
            default max_levels configured during initialization.

        Returns:
        -------
        int
            Calculated light level (from 0 up to max_levels).

        Examples:
        ---------
        1. level = stats.get_light_level()
        2. level_8 = stats.get_light_level(max_levels=8)
        """
        levels = self._max_levels if max_levels is None else max_levels
        total = self.get_total_count()
        if total == 0:
            return 0

        pct = self.calculate_percentage()
        level = int(round((pct / 100.0) * levels))
        level = max(0, min(levels, level))
        Log.i(f"FeedbackStats: Light level is {level}/{levels} ({pct}%)")
        return level

    def reset(self):
        """
        Reset both happy and unhappy counts back to zero.

        Examples:
        ---------
        1. stats.reset()
        """
        self._happy_count = 0
        self._unhappy_count = 0
        Log.i("FeedbackStats: Counts have been reset to 0")


if __name__ == "__main__":
    Log.i("Starting FeedbackStats self-test...")

    stats = FeedbackStats(max_levels=16)

    # Initial state checks
    assert stats.get_total_count() == 0, "Initial total should be 0"
    assert stats.calculate_percentage() == 0.0, "Initial percentage should be 0.0"
    assert stats.get_light_level() == 0, "Initial light level should be 0"

    # Test adding happy feedback
    stats.add_happy()
    assert stats.happy_count == 1
    assert stats.unhappy_count == 0
    assert stats.get_total_count() == 1
    assert stats.calculate_percentage() == 100.0
    assert stats.get_light_level() == 16

    # Test adding unhappy feedback
    stats.add_unhappy()
    assert stats.happy_count == 1
    assert stats.unhappy_count == 1
    assert stats.get_total_count() == 2
    assert stats.calculate_percentage() == 50.0
    assert stats.get_light_level() == 8
    assert stats.get_light_level(max_levels=8) == 4

    # Test another happy feedback (2 happy, 1 unhappy = 66.67%)
    stats.add_happy()
    assert stats.happy_count == 2
    assert stats.unhappy_count == 1
    assert stats.get_total_count() == 3
    assert stats.calculate_percentage() == 66.67
    assert stats.get_light_level() == 11

    # Test reset
    stats.reset()
    assert stats.happy_count == 0
    assert stats.unhappy_count == 0
    assert stats.get_total_count() == 0
    assert stats.calculate_percentage() == 0.0
    assert stats.get_light_level() == 0

    Log.i("Testing complete - all checks passed")
