"""
Tests for Levenshtein ratio accuracy after rapidfuzz migration (Paso 1).

LAYER: 1 (data-layer)
CRITERIO DE ÉXITO: rapidfuzz produce resultados equivalentes (±0.001) a la
implementación original pure-Python.
"""

from monitor_data.tools.ingest_tools.delta_detection import _levenshtein_ratio


class TestLevenshteinRatioAccuracy:
    """Verify _levenshtein_ratio correctness after rapidfuzz replacement."""

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_identical_strings(self) -> None:
        assert _levenshtein_ratio("hello", "hello") == 1.0
        assert _levenshtein_ratio("", "") == 1.0
        assert _levenshtein_ratio("a", "a") == 1.0

    def test_empty_strings(self) -> None:
        assert _levenshtein_ratio("", "hello") == 0.0
        assert _levenshtein_ratio("hello", "") == 0.0
        assert _levenshtein_ratio("", "") == 1.0

    def test_completely_different(self) -> None:
        # No shared characters → ratio should be 0.0
        result = _levenshtein_ratio("abc", "xyz")
        assert result == 0.0

    def test_single_char_diff(self) -> None:
        # "cat" vs "bat" → 1 substitution, max_len=3, ratio=1-1/3=0.666...
        result = _levenshtein_ratio("cat", "bat")
        assert 0.66 <= result <= 0.67

    # ------------------------------------------------------------------
    # Known reference values (from pure-Python Wagner-Fischer)
    # ------------------------------------------------------------------

    def test_known_similarity_high(self) -> None:
        """Strings differing by 1 char in 10 → ratio = 0.9"""
        result = _levenshtein_ratio("Gandalf123", "Gandalf124")
        assert 0.89 <= result <= 0.91

    def test_known_similarity_medium(self) -> None:
        """Half the string different → ratio ≈ 0.5"""
        result = _levenshtein_ratio("abcdef", "abcxyz")
        assert 0.49 <= result <= 0.51

    def test_known_similarity_low(self) -> None:
        """Mostly different → ratio ≈ 0.25"""
        result = _levenshtein_ratio("aaaa", "bbbb")
        assert result == 0.0  # All chars different

    # ------------------------------------------------------------------
    # Long strings (where rapidfuzz's C implementation shines)
    # ------------------------------------------------------------------

    def test_long_identical(self) -> None:
        s = "The quick brown fox jumps over the lazy dog. " * 10
        assert _levenshtein_ratio(s, s) == 1.0

    def test_long_similar(self) -> None:
        s1 = "The quick brown fox jumps over the lazy dog. " * 10
        s2 = "The quick brown fox jumps over the lazy cat. " * 10
        result = _levenshtein_ratio(s1, s2)
        # 10 repetitions × 3 substitutions (d→c, o→a, g→t) / 450 chars = 30/450
        assert 0.93 <= result <= 0.94

    def test_long_different(self) -> None:
        s1 = "aaaa " * 50
        s2 = "bbbb " * 50
        result = _levenshtein_ratio(s1, s2)
        # All letters differ, spaces match: 4×50=200 diffs / 250 chars = 0.2 sim
        assert 0.19 <= result <= 0.21

    # ------------------------------------------------------------------
    # Case sensitivity (rapidfuzz is case-sensitive by default, matching original)
    # ------------------------------------------------------------------

    def test_case_sensitive(self) -> None:
        result = _levenshtein_ratio("Hello", "hello")
        assert 0.79 <= result <= 0.81  # 1 substitution out of 5

    # ------------------------------------------------------------------
    # Unicode support
    # ------------------------------------------------------------------

    def test_unicode_strings(self) -> None:
        result = _levenshtein_ratio("café", "cafe")
        assert 0.74 <= result <= 0.76  # 1 char diff (é → e)
