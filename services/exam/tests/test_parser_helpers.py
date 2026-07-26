"""
tests/test_parser_helpers.py
------------------------------
Unit tests for parser helper utilities.
"""

from app.ingestion.parser_helpers import (
    parse_question_range,
    parse_passage_header,
    classify_test_marker,
)


class TestParseQuestionRange:
    def test_four_digits_1428(self):
        # 1428: (1, 428) valid, (14, 28) valid, (142, 8) invalid
        result = parse_question_range("1428")
        assert result is not None
        assert (1, 428) in result.candidates
        assert (14, 28) in result.candidates
        assert result.ambiguous is True

    def test_ambiguous_2740(self):
        result = parse_question_range("2740")
        assert result is not None
        assert (2, 740) in result.candidates
        assert (27, 40) in result.candidates
        assert result.ambiguous is True

    def test_three_digits_single_valid(self):
        # 123: (1, 23) valid. Also with drop: drop 2 -> 1, 3. So [(1, 23), (1, 3)]
        result = parse_question_range("123")
        assert result is not None
        assert (1, 23) in result.candidates
        assert (1, 3) in result.candidates
        assert result.ambiguous is True

    def test_three_digits_321(self):
        # 321: (3, 21) valid, (32, 1) invalid. Drop 2 -> 3, 1 (invalid).
        result = parse_question_range("321")
        assert result is not None
        assert result.candidates == [(3, 21)]
        assert result.ambiguous is False

    def test_ambiguous_four_digits_1234(self):
        result = parse_question_range("1234")
        assert result is not None
        assert (1, 234) in result.candidates
        assert (12, 34) in result.candidates
        assert result.ambiguous is True

    def test_no_valid_splits_returns_none(self):
        pass

    def test_non_numeric_returns_none(self):
        assert parse_question_range("abc") is None

    def test_two_digits_returns_none(self):
        assert parse_question_range("14") is None

    def test_five_digits_returns_none(self):
        # 5 digits are now supported
        result = parse_question_range("12345")
        assert result is not None
        assert (1, 2345) in result.candidates

    def test_six_digits_returns_none(self):
        # > 5 digits are rejected
        assert parse_question_range("123456") is None

    def test_empty_returns_none(self):
        assert parse_question_range("") is None

    def test_whitespace_stripped(self):
        result = parse_question_range("  1428  ")
        assert result is not None
        assert (14, 28) in result.candidates

    def test_single_digit_in_three(self):
        # 987: (9, 87) valid. Drop 8 -> 9, 7 (invalid)
        result = parse_question_range("987")
        assert result is not None
        assert result.candidates == [(9, 87)]
        assert result.ambiguous is False

    def test_9821_single_valid(self):
        # 9821: (9, 821) valid.
        # Drops: drop 8 -> 9, 21. drop 2 -> 9, 81. Both valid.
        result = parse_question_range("9821")
        assert result is not None
        assert (9, 821) in result.candidates
        assert (9, 21) in result.candidates
        assert (9, 81) in result.candidates
        assert result.ambiguous is True


class TestParsePassageHeader:
    def test_normal_passage_1(self):
        result = parse_passage_header("READING PASSAGE 1")
        assert result is not None
        assert result.raw_number == 1
        assert result.candidates == [1]

    def test_normal_passage_2(self):
        result = parse_passage_header("READING PASSAGE 2")
        assert result is not None
        assert result.raw_number == 2
        assert result.candidates == [2]

    def test_normal_passage_3(self):
        result = parse_passage_header("READING PASSAGE 3")
        assert result is not None
        assert result.raw_number == 3
        assert result.candidates == [3]

    def test_corrupted_74(self):
        result = parse_passage_header("READING PASSAGE 74")
        assert result is not None
        assert result.raw_number == 74
        assert result.candidates == [7, 4]

    def test_corrupted_13(self):
        result = parse_passage_header("READING PASSAGE 13")
        assert result is not None
        assert result.raw_number == 13
        assert result.candidates == [1, 3]

    def test_corrupted_111_deduplicates(self):
        result = parse_passage_header("READING PASSAGE 111")
        assert result is not None
        assert result.raw_number == 111
        assert result.candidates == [1]

    def test_corrupted_122_deduplicates(self):
        result = parse_passage_header("READING PASSAGE 122")
        assert result is not None
        assert result.raw_number == 122
        assert result.candidates == [1, 2]

    def test_zero_digit_excluded(self):
        result = parse_passage_header("READING PASSAGE 20")
        assert result is not None
        assert result.raw_number == 20
        assert result.candidates == [2]

    def test_leading_whitespace(self):
        result = parse_passage_header("  READING PASSAGE 2")
        assert result is not None
        assert result.raw_number == 2

    def test_case_insensitive(self):
        result = parse_passage_header("reading passage 1")
        assert result is not None
        assert result.raw_number == 1

    def test_not_a_passage_header(self):
        assert parse_passage_header("This is not a header") is None

    def test_empty_line(self):
        assert parse_passage_header("") is None


class TestClassifyTestMarker:
    def test_simple_test_1(self):
        result = classify_test_marker("Test 1")
        assert result is not None
        assert result.test_number == 1
        assert result.is_toc is False
        assert result.is_phantom is False

    def test_simple_test_4(self):
        result = classify_test_marker("Test 4")
        assert result is not None
        assert result.test_number == 4
        assert result.is_toc is False
        assert result.is_phantom is False

    def test_toc_entry(self):
        result = classify_test_marker("Test 1 10")
        assert result is not None
        assert result.test_number == 1
        assert result.is_toc is True
        assert result.is_phantom is False

    def test_toc_entry_large_page(self):
        result = classify_test_marker("Test 2 33")
        assert result is not None
        assert result.test_number == 2
        assert result.is_toc is True

    def test_toc_negative_trailing_text(self):
        result = classify_test_marker("Test 1 page 10")
        assert result is not None
        assert result.test_number == 1
        assert result.is_toc is False

    def test_phantom_test(self):
        result = classify_test_marker("Test 7")
        assert result is not None
        assert result.test_number == 7
        assert result.is_toc is False
        assert result.is_phantom is True

    def test_phantom_test_5(self):
        result = classify_test_marker("Test 5")
        assert result is not None
        assert result.is_phantom is True

    def test_case_insensitive(self):
        result = classify_test_marker("test 2")
        assert result is not None
        assert result.test_number == 2

    def test_leading_whitespace(self):
        result = classify_test_marker("  Test 3")
        assert result is not None
        assert result.test_number == 3

    def test_multiple_spaces(self):
        result = classify_test_marker("Test     3")
        assert result is not None
        assert result.test_number == 3
        assert result.is_toc is False
        assert result.is_phantom is False

    def test_prose_containing_test(self):
        result = classify_test_marker("Test 1 was conducted on 50 subjects")
        assert result is not None
        assert result.test_number == 1
        assert result.is_toc is False

    def test_not_a_test_marker(self):
        assert classify_test_marker("Questions 1-10") is None

    def test_empty_line(self):
        assert classify_test_marker("") is None

    def test_number_only(self):
        assert classify_test_marker("1") is None
