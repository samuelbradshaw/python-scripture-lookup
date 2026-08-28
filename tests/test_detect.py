# Tests for lookup.detect_references
#
# Run with:
#   python3 -m pytest tests

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'src'))
from scripturelookup import lookup


# (input text, language, expected labels in order)
detection_cases = [
  # Nothing to find
  ('', 'en', []),
  ('Nothing here at all.', 'en', []),

  # A run of related references stays a single detection
  ('See 1 Nephi 3:7, 5:2; Alma 5 for details.', 'en', ['1 Nephi 3:7, 5:2; Alma 5']),
  ('Doctrine and Covenants 45:56-59 | 1 Nephi 22:24-28', 'en', ['Doctrine and Covenants 45:56-59 | 1 Nephi 22:24-28']),
  ('Doctrine & Covenants 45:56 • 1 Nephi 22:24', 'en', ['Doctrine & Covenants 45:56 • 1 Nephi 22:24']),

  # "&" stands in for a spelled-out list conjunction in any language, not just English
  ('Vea Doctrina & Convenios 45:56 aquí.', 'es', ['Doctrina & Convenios 45:56']),
  ('Vea Doctrina y Convenios 45:56 aquí.', 'es', ['Doctrina y Convenios 45:56']),

  # Abbreviations
  ('In 2 Ne. 2:25 we read.', 'en', ['2 Ne. 2:25']),
  ('Compare Matt. 5:3 today.', 'en', ['Matt. 5:3']),

  # A number is required, so ordinary words that are also book names are skipped
  ('He found a job in Job 5.', 'en', ['Job 5']),
  ('Read the Book of Mormon.', 'en', []),

  # Trailing whitespace and unbalanced parentheses are never part of a match
  ('Read Genesis 1-3 (see also Moses 2).', 'en', ['Genesis 1-3', 'Moses 2']),
  ('Gen. 1:3 (3-4) is nice.', 'en', ['Gen. 1:3 (3-4)']),

  # A period is a chapter/verse separator in some languages, but only between digits
  ('Alma 32. 5 people came.', 'en', ['Alma 32']),

  # Chapter words can stand in for a book name; verse words cannot
  ('See chapter 3 and Alma chapter 32 verse 21.', 'en', ['chapter 3', 'Alma chapter 32 verse 21']),
  ('See verses 3-5 below.', 'en', []),

  # Bare chapter:verse with no preceding anchor is not a reference
  ('As in Alma 32. See also 3:7.', 'en', ['Alma 32']),
  ('Meet at 3:15 tomorrow.', 'en', []),

  # Spelled-out lists and ranges
  ('Genesis 12:1, 2, and 3 plus John 2 through 7.', 'en', ['Genesis 12:1, 2, and 3', 'John 2 through 7']),

  # A number that starts the next book name isn't pulled into this reference's verse list
  ('See 1 Nephi 3:7, 5:2; Alma 5 and 2 Ne. 2:25 in chapter 9.', 'en', ['1 Nephi 3:7, 5:2; Alma 5', '2 Ne. 2:25', 'chapter 9']),
  ('Alma 5, 2 Ne. 2:25 today.', 'en', ['Alma 5', '2 Ne. 2:25']),
  ('Read 1 Nephi 3 and 3 John 1:4.', 'en', ['1 Nephi 3', '3 John 1:4']),

  # A conjunction can follow a reference separator
  ('mentioned in Genesis 11:29; 22:23; and 24:15 as well as in Abraham 2:2.', 'en', ['Genesis 11:29; 22:23; and 24:15', 'Abraham 2:2']),

  # A colon may be followed by a space, but a period may not (a period is also a chapter/verse separator)
  ('Mosiah 28: 13-15 is next.', 'en', ['Mosiah 28: 13-15']),
  ('Genesis 1.3 and Abr. 3.22-23 here.', 'en', ['Genesis 1.3', 'Abr. 3.22-23']),
  ('It cost 1.50 today.', 'en', []),

  # Names that aren't in the "structure" book list
  ('See Psalm 23 and Official Declaration 2 and Facsimile 2.', 'en', ['Psalm 23', 'Official Declaration 2', 'Facsimile 2']),

  # Line-wrapped references are found, and the label keeps the original whitespace
  ('Alma\n32:21 was quoted.', 'en', ['Alma\n32:21']),
  ('Alma\r\n32:21 was quoted.', 'en', ['Alma\r\n32:21']),
  ('See Alma\n  32:21, 22 here.', 'en', ['Alma\n  32:21, 22']),

  # Any kind of Unicode whitespace works, not just a regular space
  ('See 1 Samuel 3:1 now.', 'en', ['1 Samuel 3:1']),
  ('See 1\xa0Samuel 3:1 now.', 'en', ['1\xa0Samuel 3:1']),
  ('See Alma　32:21 now.', 'en', ['Alma　32:21']),

  # Reference words are language-specific. German has no seeded word list, so "capítulo 3" isn't a
  # reference there, but "Alma" is spelled the same in German and Spanish and is still detected.
  ('Consulte el capítulo 3 y Alma 32:21 aquí.', 'es', ['capítulo 3', 'Alma 32:21']),
  ('Consulte el capítulo 3 y Alma 32:21 aquí.', 'de', ['Alma 32:21']),

  # Book names are language-specific too
  ('Siehe Alma 32:21 hier.', 'de', ['Alma 32:21']),
  ('Siehe Alma 32:21 hier.', 'ko', []),
]


@pytest.mark.parametrize('text, lang, expected_labels', detection_cases)
def test_detect_references(text, lang, expected_labels):
  detections = lookup.detect_references(text, lang = lang)
  assert [label for label, start, end in detections] == expected_labels


@pytest.mark.parametrize('text, lang, expected_labels', detection_cases)
def test_offsets_match_the_original_string(text, lang, expected_labels):
  for label, start, end in lookup.detect_references(text, lang = lang):
    assert text[start:end] == label


@pytest.mark.parametrize('text, lang, expected_labels', detection_cases)
def test_detections_do_not_overlap(text, lang, expected_labels):
  previous_end = 0
  for label, start, end in lookup.detect_references(text, lang = lang):
    assert start >= previous_end
    assert start < end
    previous_end = end


def test_detected_labels_can_be_parsed_back():
  text = 'See 1 Nephi 3:7 and Mosiah 2:17 for details.'
  labels = [lookup.get_label(label) for label, start, end in lookup.detect_references(text)]
  assert labels == ['1\xa0Nephi\xa03:7', 'Mosiah\xa02:17']


# Parsing (not detection) treats a line break as a separator between references, so whitespace
# normalization there has to leave line breaks alone.
def test_line_breaks_still_separate_references_when_parsing():
  assert lookup.get_label('Alma 5\nMosiah 2:17') == 'Alma\xa05\nMosiah\xa02:17'
  assert lookup.get_label('Alma 5\r\nMosiah 2:17') == 'Alma\xa05\nMosiah\xa02:17'


@pytest.mark.parametrize('space', [' ', '\xa0', ' ', ' '])
def test_book_names_match_any_kind_of_space(space):
  assert lookup.get_label(f'1{space}Samuel 3:1') == '1\xa0Samuel\xa03:1'
