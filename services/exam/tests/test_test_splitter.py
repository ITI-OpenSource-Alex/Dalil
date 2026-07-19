from app.ingestion.test_splitter import TestSplitter


def test_test_splitter_ignores_toc_and_answer_keys() -> None:
    """Ensure TestSplitter isolates genuine blocks and ignores non-boundaries."""
    text = """
Some initial text.
Test 1
LISTENING
SECTION 1 Questions 1-10
Blah blah blah...
Test 1
WRITING
WRITING TASK 1
Blah blah blah...
Test 2
LISTENING
SECTION 1 Questions 1-10
Test 2 listening text...
Answer Keys
Test 1
Section 1, Questions 1-10
Test 2
Section 1, Questions 1-10
"""
    splitter = TestSplitter()
    tests = splitter.split(text)

    assert len(tests) == 2

    # Test 1 should contain everything from the real Test 1 start up to Test 2 start
    assert "Test 1\nLISTENING" in tests[1]
    assert "WRITING TASK 1" in tests[1]
    assert "Test 2\nLISTENING" not in tests[1]

    # Test 2 should contain everything from the real Test 2 start to the end of the text
    assert "Test 2\nLISTENING" in tests[2]
    assert "Answer Keys\nTest 1" in tests[2]


def test_test_splitter_exactly_four_tests() -> None:
    """If there are exactly 4 tests, they are parsed correctly."""
    text = """
Test 1
SECTION 1 Questions 1-10
content 1
Test 2
SECTION 1 Questions 1-10
content 2
Test 3
SECTION 1 Questions 1-10
content 3
Test 4
SECTION 1 Questions 1-10
content 4
"""
    splitter = TestSplitter()
    tests = splitter.split(text)
    assert list(tests.keys()) == [1, 2, 3, 4]
    assert "content 1" in tests[1]
    assert "content 2" in tests[2]
    assert "content 3" in tests[3]
    assert "content 4" in tests[4]
