"""
tests/test_ocr_normalizer.py
------------------------------
Unit tests for the OCR normalization pipeline.
Each pipeline function is tested independently.
"""


from app.ingestion.ocr_normalizer import (
    OCRNormalizer,
    DEFAULT_NORMALIZER,
    normalize_unicode,
    normalize_dashes,
    normalize_quotes,
    normalize_ellipsis,
    remove_page_footers,
    remove_publisher_headers,
    remove_copyright,
    remove_page_numbers,
    normalize_bullets,
    normalize_whitespace,
    collapse_blank_lines,
)


class TestNormalizeUnicode:
    def test_nfc_normalization(self):
        text = "café"
        result = normalize_unicode(text)
        assert result == "café"

    def test_nbsp_to_space(self):
        text = "hello world"
        result = normalize_unicode(text)
        assert result == "hello world"

    def test_bom_removed(self):
        text = "﻿hello"
        result = normalize_unicode(text)
        assert result == "hello"

    def test_zero_width_space_removed(self):
        text = "hel​lo"
        result = normalize_unicode(text)
        assert result == "hello"

    def test_zero_width_non_joiner_removed(self):
        text = "hel‌lo"
        result = normalize_unicode(text)
        assert result == "hello"

    def test_zero_width_joiner_removed(self):
        text = "hel‍lo"
        result = normalize_unicode(text)
        assert result == "hello"

    def test_plain_text_unchanged(self):
        text = "normal text 123"
        assert normalize_unicode(text) == text


class TestNormalizeDashes:
    def test_em_dash(self):
        assert normalize_dashes("word—word") == "word-word"

    def test_en_dash(self):
        assert normalize_dashes("14–28") == "14-28"

    def test_minus_sign(self):
        assert normalize_dashes("14−28") == "14-28"

    def test_regular_hyphen_unchanged(self):
        assert normalize_dashes("14-28") == "14-28"

    def test_mixed(self):
        text = "Questions 14–28 and 27—40"
        assert normalize_dashes(text) == "Questions 14-28 and 27-40"


class TestNormalizeQuotes:
    def test_left_single(self):
        assert normalize_quotes("‘hello") == "'hello"

    def test_right_single(self):
        assert normalize_quotes("it’s") == "it's"

    def test_left_double(self):
        assert normalize_quotes("“hello") == '"hello'

    def test_right_double(self):
        assert normalize_quotes("world”") == 'world"'

    def test_straight_quotes_unchanged(self):
        text = 'it\'s "fine"'
        assert normalize_quotes(text) == text


class TestNormalizeEllipsis:
    def test_ellipsis_char(self):
        assert normalize_ellipsis("wait…") == "wait..."

    def test_three_dots_unchanged(self):
        assert normalize_ellipsis("wait...") == "wait..."

    def test_multiple_ellipsis(self):
        assert normalize_ellipsis("a…b…c") == "a...b...c"


class TestRemovePageFooters:
    def test_removes_footer_with_page_ref(self):
        text = "content line\n> [Q p. 123 p. 107]\nnext line"
        result = remove_page_footers(text)
        assert "> [Q p." not in result
        assert "content line" in result
        assert "next line" in result

    def test_removes_footer_with_bracket(self):
        text = "line1\n  [S p. 45]\nline2"
        result = remove_page_footers(text)
        assert "[S p." not in result

    def test_preserves_normal_lines(self):
        text = "This is a paragraph.\nAnother line."
        assert remove_page_footers(text) == text

    def test_preserves_questions_with_p(self):
        text = "Questions p. 107 are about the passage"
        result = remove_page_footers(text)
        assert "Questions" in result


class TestRemovePublisherHeaders:
    def test_removes_cambridge_ielts(self):
        text = "content\nCambridge IELTS 14\nmore content"
        result = remove_publisher_headers(text)
        assert "Cambridge IELTS" not in result
        assert "content" in result

    def test_removes_cambridge_university_press(self):
        text = "line\nCambridge University Press 2020\nline"
        result = remove_publisher_headers(text)
        assert "Cambridge University Press" not in result

    def test_case_insensitive(self):
        text = "  cambridge ielts 16"
        result = remove_publisher_headers(text)
        assert result == ""

    def test_preserves_cambridge_in_prose(self):
        text = "He studied at Cambridge for three years."
        assert remove_publisher_headers(text) == text


class TestRemoveCopyright:
    def test_removes_copyright_symbol(self):
        text = "content\n© Cambridge 2019\nmore"
        result = remove_copyright(text)
        assert "©" not in result
        assert "content" in result

    def test_removes_copyright_word(self):
        text = "line\nCopyright 2019 All rights reserved\nline"
        result = remove_copyright(text)
        assert "Copyright" not in result

    def test_preserves_normal_lines(self):
        text = "This has no special markers."
        assert remove_copyright(text) == text


class TestRemovePageNumbers:
    def test_removes_standalone_number(self):
        text = "content\n42\nmore content"
        result = remove_page_numbers(text)
        assert result == "content\nmore content"

    def test_removes_padded_number(self):
        text = "content\n  7  \nmore"
        result = remove_page_numbers(text)
        assert "  7  " not in result

    def test_preserves_numbers_in_text(self):
        text = "42 questions in total"
        assert remove_page_numbers(text) == text

    def test_preserves_large_numbers(self):
        text = "1234"
        assert remove_page_numbers(text) == text

    def test_removes_three_digit(self):
        text = "line\n123\nline"
        result = remove_page_numbers(text)
        assert result == "line\nline"


class TestNormalizeBullets:
    def test_asterisk(self):
        assert normalize_bullets("* item") == "• item"

    def test_middle_dot(self):
        assert normalize_bullets("· item") == "• item"

    def test_bullet_char_unchanged(self):
        assert normalize_bullets("• item") == "• item"

    def test_triangle(self):
        assert normalize_bullets("► item") == "• item"

    def test_plus(self):
        assert normalize_bullets("+ item") == "• item"

    def test_bracket(self):
        assert normalize_bullets("[ item") == "• item"

    def test_preserves_non_bullet_lines(self):
        text = "normal line"
        assert normalize_bullets(text) == text

    def test_preserves_asterisk_midline(self):
        text = "5 * 3 = 15"
        assert normalize_bullets(text) == text


class TestNormalizeWhitespace:
    def test_collapse_multiple_spaces(self):
        assert normalize_whitespace("hello   world") == "hello world"

    def test_collapse_tabs(self):
        assert normalize_whitespace("hello\t\tworld") == "hello world"

    def test_strip_trailing(self):
        assert normalize_whitespace("hello   ") == "hello"

    def test_preserve_leading_space(self):
        assert normalize_whitespace("  hello") == " hello"

    def test_mixed(self):
        assert normalize_whitespace("  a  b\t c  ") == " a b c"


class TestCollapseBlankLines:
    def test_three_blanks_collapsed(self):
        text = "a\n\n\n\nb"
        result = collapse_blank_lines(text)
        assert result == "a\n\nb"

    def test_five_blanks_collapsed(self):
        text = "a\n\n\n\n\n\nb"
        result = collapse_blank_lines(text)
        assert result == "a\n\nb"

    def test_two_blanks_unchanged(self):
        text = "a\n\n\nb"
        result = collapse_blank_lines(text)
        assert result == "a\n\nb"

    def test_single_blank_unchanged(self):
        text = "a\n\nb"
        assert collapse_blank_lines(text) == text

    def test_whitespace_only_blank_lines(self):
        text = "a\n \n\n\t\nb"
        result = collapse_blank_lines(text)
        assert result == "a\n\nb"


class TestOCRNormalizerClass:
    def test_normalize_runs_full_pipeline(self):
        text = (
            "﻿"
            "café\n"
            "14–28\n"
            "“hello”\n"
            "wait…\n"
            "> [Q p. 123]\n"
            "Cambridge IELTS 14\n"
            "© 2019\n"
            "42\n"
            "* bullet\n"
            "a  b\t\tc  \n"
            "\n\n\n\n\n"
            "end"
        )
        result = DEFAULT_NORMALIZER.normalize(text)

        assert "café" in result
        assert "14-28" in result
        assert '"hello"' in result
        assert "wait..." in result
        assert "> [Q p." not in result
        assert "Cambridge IELTS" not in result
        assert "©" not in result
        assert "\n42\n" not in result
        assert "• bullet" in result
        assert "a b c" in result
        assert "\n\n\n\n" not in result
        assert "end" in result

    def test_idempotent(self):
        text = "Hello world—test\n> [Q p. 99]\n* item\n\n\n\n\n\ndone"
        first = DEFAULT_NORMALIZER.normalize(text)
        second = DEFAULT_NORMALIZER.normalize(first)
        third = DEFAULT_NORMALIZER.normalize(second)
        assert first == second == third

    def test_class_and_singleton_equivalent(self):
        normalizer = OCRNormalizer()
        text = "Hello—world ‘test’\n© line\n42\nend"
        assert normalizer.normalize(text) == DEFAULT_NORMALIZER.normalize(text)

    def test_empty_string(self):
        assert DEFAULT_NORMALIZER.normalize("") == ""

    def test_plain_text_unchanged(self):
        text = "This is plain text.\nWith two lines."
        assert DEFAULT_NORMALIZER.normalize(text) == text
