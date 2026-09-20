# Tests for lookup.detect_references
#
# Run with:
#   python3 -m pytest tests

import os
import sys
import unicodedata

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

  # A chapter or verse is never more than three digits, so years and page numbers aren't references.
  # The whole number is rejected rather than being truncated to its first three digits.
  ('Psalm 119:176 is the last verse.', 'en', ['Psalm 119:176']),
  ('D&C 124:123-45 was given.', 'en', ['D&C 124:123-45']),
  ('Alma 1978 was a year.', 'en', []),
  ('Alma 12345 xyz', 'en', []),
  ('Alma 32:21 was quoted in 1978.', 'en', ['Alma 32:21']),

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

  # A colon may be surrounded by spaces, as French typography does, but a period may not (a period is
  # also an abbreviation mark and a sentence ending)
  ('Mosiah 28: 13-15 is next.', 'en', ['Mosiah 28: 13-15']),
  ('Doctrine et Alliances 110 :11-16', 'fr', ['Doctrine et Alliances 110 :11-16']),
  ('Voir D&A 110 : 11 - 16 ici', 'fr', ['D&A 110 : 11 - 16']),
  ('Genesis 1.3 and Abr. 3.22-23 here.', 'en', ['Genesis 1.3', 'Abr. 3.22-23']),
  ('It cost 1.50 today.', 'en', []),
  ('Alma 32 . 5 people came.', 'en', ['Alma 32']),
  ('Meet at 3 : 15 tomorrow.', 'en', []),

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

  # A short abbreviation doesn't match inside a longer name – "Al" (Alma) must not split "Alliances"
  ('Doctrine et Alliances 4:1', 'fr', ['Doctrine et Alliances 4:1']),

  # A missing diacritic still matches, in either direction. The character classes are built from each
  # language's own names, so English – whose names carry no diacritics – has none to fold.
  ('Voir 2 Nephi 3 ici.', 'fr', ['2 Nephi 3']),
  ('Voir 2 Néphi 3 ici.', 'fr', ['2 Néphi 3']),
  ('See 2 Nephi 3 here.', 'en', ['2 Nephi 3']),

  # A plural "s" is optional on any one word of a multi-word name, since languages don't pluralize the same
  # word. A single-word name is left alone, so an ordinary French "acte 2" isn't read as the book "Actes".
  ('Doctrine et Alliance 4:1-7 | Luc 2:10-11 | 2 Nephi 3', 'fr', ['Doctrine et Alliance 4:1-7 | Luc 2:10-11 | 2 Nephi 3']),
  ('Article de foi 1:3', 'fr', ['Article de foi 1:3']),
  ('Artículo de Fe 1:1 | Moisés 1:39', 'es', ['Artículo de Fe 1:1 | Moisés 1:39']),
  ('Article of Faith 1:13', 'en', ['Article of Faith 1:13']),
  ('un acte 2 de la pièce', 'fr', []),

  # "De" is the French abbreviation for Deuteronomy, and must not break up ordinary text that follows a
  # reference-shaped name
  ('Perle de Grand Prix', 'fr', []),

  # Typesetting substitutes look-alike dashes for a plain hyphen in a verse range
  ('Luc 12:6-7', 'fr', ['Luc 12:6-7']),
  ('Luc 12:6‐ 7', 'fr', ['Luc 12:6‐ 7']),
  ('Luc 12:6‑7', 'fr', ['Luc 12:6‑7']),
  ('Luc 12:6‒7', 'fr', ['Luc 12:6‒7']),
  ('Luc 12:6−7', 'fr', ['Luc 12:6−7']),

  # Capitalization never matters
  ('luc 2:10-11', 'fr', ['luc 2:10-11']),
  ('LUC 2:10-11', 'fr', ['LUC 2:10-11']),

  # A bare number that starts an unrecognized book name belongs to that name, not to the reference before it
  ('Luc 2:10-11 | 2 Nefi 3', 'fr', ['Luc 2:10-11', '2 Nefi 3']),
  ('Genesis 1:1; 2 Kings 3:4', 'en', ['Genesis 1:1; 2 Kings 3:4']),
  # The trailing reference can reach past the end of the match it came from, and a chapter word inside it
  # would otherwise be detected a second time on its own
  ('Luc 2:10-11 | 2 Nefi chapitre 3', 'fr', ['Luc 2:10-11', '2 Nefi chapitre 3']),
  # The number is still given back when what follows has no chapter, since it was never Luke's either
  ('Luc 2:10-11 | 2 Nefi', 'fr', ['Luc 2:10-11']),

  # ...but a number that continues the reference is kept, even when ordinary words follow it
  ('See Alma 5; 7 for more context.', 'en', ['Alma 5; 7']),
  ('D&C 76; 84 says something.', 'en', ['D&C 76; 84']),
  ('Read 1 Nephi 3:7; 5 and rejoice.', 'en', ['1 Nephi 3:7; 5']),

  # An accented character can be spelled decomposed ("e" plus a combining acute accent), and the offsets
  # reported for it still line up with the original string
  (unicodedata.normalize('NFD', 'Voir 2 Néphi 3 et Luc 2:10 ici'), 'fr', [unicodedata.normalize('NFD', '2 Néphi 3'), 'Luc 2:10']),

  # A numbered book can have its number written out or abbreviated
  ('1st John 3:2', 'en', ['1st John 3:2']),
  ('III John 1:4', 'en', ['III John 1:4']),
  ('First Nephi 3:7', 'en', ['First Nephi 3:7']),
  ('II Corinthians 5:17', 'en', ['II Corinthians 5:17']),
  ('IV Nephi 1:34', 'en', ['IV Nephi 1:34']),
  ('Premier Néphi 3:7', 'fr', ['Premier Néphi 3:7']),
  ('1er Néphi 3:7', 'fr', ['1er Néphi 3:7']),
  ('Primer Nefi 3:7', 'es', ['Primer Nefi 3:7']),

  # A book name has to follow the number, so ordinary text isn't swallowed
  ('I saw Alma 32:21 today', 'en', ['Alma 32:21']),
  ('I am reading Alma 32', 'en', ['Alma 32']),
  # Punctuation after the number breaks the phrase, since only whitespace joins it to the name
  ('first, John 2', 'en', ['John 2']),
  ('first: John 2', 'en', ['John 2']),
  # Each number only goes with the books that exist for it – there is no 4 John, and Alma isn't numbered
  ('4th John 1:1', 'en', ['John 1:1']),
  ('1st Alma 32:21', 'en', ['Alma 32:21']),
  ('5th Nephi 1:1', 'en', []),

  # An article of faith can be cited by position, with no digit anywhere in the text
  ('Premier article de foi | Moïse 1:39', 'fr', ['Premier article de foi | Moïse 1:39']),
  ('First Article of Faith', 'en', ['First Article of Faith']),
  ('13th Article of Faith', 'en', ['13th Article of Faith']),
  ('1er article de foi', 'fr', ['1er article de foi']),
  ('Primer Artículo de Fe', 'es', ['Primer Artículo de Fe']),
  ('Primeira regra de fé', 'pt', ['Primeira regra de fé']),
  # Ordinals can be listed or given as a range
  ('First and Third Articles of Faith', 'en', ['First and Third Articles of Faith']),
  ('First, Second and Third Articles of Faith', 'en', ['First, Second and Third Articles of Faith']),
  ('First through Third Articles of Faith', 'en', ['First through Third Articles of Faith']),
  ('Premier et troisième articles de foi', 'fr', ['Premier et troisième articles de foi']),
  # "and" isn't a reference separator, so this is two detections rather than one run
  ('13th Article of Faith and Alma 32:21', 'en', ['13th Article of Faith', 'Alma 32:21']),

  # An ordinal on its own is ordinary text, and a language with no ordinals seeded is unaffected
  ('first among equals', 'en', []),
  ('Read the first book you find.', 'en', []),
  ('the first article', 'en', []),
  ('Erster Glaubensartikel', 'de', []),
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


# A separator between two numbers can be spaced out, whichever kind of separator it is
@pytest.mark.parametrize('text, lang, expected_uri', [
  ('Doctrine et Alliances 110 :11-16', 'fr', '/scriptures/dc-testament/dc/110.11-16'),
  ('Doctrine et Alliances 110 : 11 - 16', 'fr', '/scriptures/dc-testament/dc/110.11-16'),
  ('Alma 32:1 , 3', 'en', '/scriptures/bofm/alma/32.1,3'),
  ('Alma 32:1 - 3', 'en', '/scriptures/bofm/alma/32.1-3'),
  # A spaced-out chapter range has to close up too, or the chapter never resolves to a number
  ('Genesis 1 – 3', 'en', '/scriptures/ot/gen/1'),
])
def test_separators_between_numbers_may_be_spaced_out(text, lang, expected_uri):
  assert lookup.parse_references_string(text, lang = lang)[0].church_uri() == expected_uri


# The spacing above must not be mistaken for trailing text and thrown away
def test_spaced_out_verses_are_not_stripped_as_trailing_text():
  assert lookup.get_label('Doctrine and Covenants 110 :11-16') == 'Doctrine and Covenants\xa0110:11–16'
  # ...while text that really does trail the reference still goes
  assert lookup.get_label('1 John 3:2 2') == '1\xa0John\xa03:2'


# Words inside a parenthetical aren't context verses, even when a second reference splits the parenthetical apart
def test_words_in_a_parenthetical_are_not_context_verses():
  text = 'Matthew 7:1–2 (see JST Matthew 7:1–2)'
  assert lookup.get_church_uri(text) == '/scriptures/nt/matt/7.1-2\n/scriptures/jst/jst-matt/7.1-2'
  assert lookup.get_church_uri(text, use_query_parameters = True) == '/scriptures/nt/matt/7?id=p1-p2\n/scriptures/jst/jst-matt/7?id=p1-p2'
  # ...while numbers still are
  assert lookup.get_church_uri('Gen. 1:3 (3–4)') == '/scriptures/ot/gen/1.3(3-4)'


# A footnote letter after a verse marks a study note, so it's dropped rather than taking the verse with it
@pytest.mark.parametrize('text, expected_uri', [
  ('Genesis 6:7a', '/scriptures/ot/gen/6.7'),
  ('Genesis 6:7a, 13', '/scriptures/ot/gen/6.7,13'),
  ('Alma 32:21a–23b', '/scriptures/bofm/alma/32.21-23'),
  ('Gen. 1:3a (3–4)', '/scriptures/ot/gen/1.3(3-4)'),
])
def test_verse_footnote_letters_are_dropped(text, expected_uri):
  assert lookup.get_church_uri(text) == expected_uri


# A footnote letter is citation syntax rather than sloppy input, so it goes even when cleanup is skipped
def test_verse_footnote_letters_are_dropped_even_when_cleanup_is_skipped():
  assert lookup.get_church_uri('Genesis 6:7a', skip_cleanup = True) == '/scriptures/ot/gen/6.7'


# A book with only one chapter takes a bare number as its verse – there is no Jude 3
@pytest.mark.parametrize('text, expected_uris', [
  ('Jude 3', ['/scriptures/nt/jude/1.3']),
  ('Jude verse 3', ['/scriptures/nt/jude/1.3']),
  ('Jude verses 3-5', ['/scriptures/nt/jude/1.3-5']),
  ('Jude 3; 5', ['/scriptures/nt/jude/1.3', '/scriptures/nt/jude/1.5']),
  ('4 Nephi 34', ['/scriptures/bofm/4-ne/1.34']),
  ('Enos 1; Jarom 2', ['/scriptures/bofm/enos/1.1', '/scriptures/bofm/jarom/1.2']),
  ('Articles of Faith 1 and 3', ['/scriptures/pgp/a-of-f/1.1', '/scriptures/pgp/a-of-f/1.3']),
  # An explicit chapter and verse is left alone, and the bare name still means the whole book
  ('Obadiah 1:3', ['/scriptures/ot/obad/1.3']),
  ('Jude', ['/scriptures/nt/jude']),
  # A book with more than one chapter is untouched
  ('Alma 32', ['/scriptures/bofm/alma/32']),
  ('Alma 32 verse 21', ['/scriptures/bofm/alma/32.21']),
])
def test_single_chapter_books_read_a_bare_number_as_the_verse(text, expected_uris):
  assert [reference.church_uri() for reference in lookup.parse_references_string(text)] == expected_uris


# It's a fact about the book rather than a cleanup of sloppy input, so it applies either way
def test_single_chapter_rule_applies_even_when_cleanup_is_skipped():
  assert lookup.get_church_uri('Jude 3', skip_cleanup = True) == '/scriptures/nt/jude/1.3'


# A written-out or abbreviated book number resolves to the same reference as the digit
@pytest.mark.parametrize('text, lang, expected_uri', [
  ('1st John 3:2', 'en', '/scriptures/nt/1-jn/3.2'),
  ('III John 1:4', 'en', '/scriptures/nt/3-jn/1.4'),
  ('First Nephi 3:7', 'en', '/scriptures/bofm/1-ne/3.7'),
  ('Second Nephi 2:25', 'en', '/scriptures/bofm/2-ne/2.25'),
  ('II Corinthians 5:17', 'en', '/scriptures/nt/2-cor/5.17'),
  ('IV Nephi 1:34', 'en', '/scriptures/bofm/4-ne/1.34'),
  ('Premier Néphi 3:7', 'fr', '/scriptures/bofm/1-ne/3.7'),
  ('1er Néphi 3:7', 'fr', '/scriptures/bofm/1-ne/3.7'),
  ('Primer Nefi 3:7', 'es', '/scriptures/bofm/1-ne/3.7'),
  ('1o Nefi 3:7', 'es', '/scriptures/bofm/1-ne/3.7'),
  ('3a Nefi 11', 'es', '/scriptures/bofm/3-ne/11'),
  ('2o Néfi 2:25', 'pt', '/scriptures/bofm/2-ne/2.25'),
])
def test_book_numbers_may_be_written_out(text, lang, expected_uri):
  assert lookup.get_church_uri(text, lang = lang) == expected_uri


# "1o" and "1a" stand in for "1º" and "1ª", but a verse with a footnote letter is never read as an ordinal
def test_verse_letters_are_not_ordinals():
  assert lookup.detect_references('Ver Génesis 6:7a Nefi 3:7.', lang = 'es') == [['Génesis 6:7', 4, 15]]
  assert lookup.detect_references('Ver Alma 32:21a y 3a Nefi 11.', lang = 'es') == [['Alma 32:21', 4, 14], ['3a Nefi 11', 18, 28]]


# An article of faith cited by position is that article, since the book is a single chapter
@pytest.mark.parametrize('text, lang, expected_uris', [
  ('First Article of Faith', 'en', ['/scriptures/pgp/a-of-f/1.1']),
  ('13th Article of Faith', 'en', ['/scriptures/pgp/a-of-f/1.13']),
  ('Premier article de foi', 'fr', ['/scriptures/pgp/a-of-f/1.1']),
  ('1er article de foi', 'fr', ['/scriptures/pgp/a-of-f/1.1']),
  ('Primer Artículo de Fe', 'es', ['/scriptures/pgp/a-of-f/1.1']),
  ('Primeira regra de fé', 'pt', ['/scriptures/pgp/a-of-f/1.1']),
  ('1o artículo de fe', 'es', ['/scriptures/pgp/a-of-f/1.1']),
  ('1a regra de fé', 'pt', ['/scriptures/pgp/a-of-f/1.1']),
  ('First and Third Articles of Faith', 'en', ['/scriptures/pgp/a-of-f/1.1', '/scriptures/pgp/a-of-f/1.3']),
  ('First through Third Articles of Faith', 'en', ['/scriptures/pgp/a-of-f/1.1-3']),
  ('Premier et troisième articles de foi', 'fr', ['/scriptures/pgp/a-of-f/1.1', '/scriptures/pgp/a-of-f/1.3']),
])
def test_articles_of_faith_cited_by_ordinal(text, lang, expected_uris):
  assert [reference.church_uri() for reference in lookup.parse_references_string(text, lang = lang)] == expected_uris


# Spanish has two accepted systems for 11 and 12, and each ordinal has masculine, feminine and apocopated
# spellings. Every one resolves, whether or not the gender agrees with the name being cited.
@pytest.mark.parametrize('text, expected_number', [
  ('Undécimo Artículo de Fe', 11), ('Undécima Artículo de Fe', 11),
  ('Decimoprimero Artículo de Fe', 11), ('Decimoprimera Artículo de Fe', 11),
  ('Decimoprimer Artículo de Fe', 11), ('Décimo primero Artículo de Fe', 11),
  ('Décima primera Artículo de Fe', 11), ('Décimo primer Artículo de Fe', 11),
  ('Duodécimo Artículo de Fe', 12), ('Decimosegunda Artículo de Fe', 12),
  ('Décimo segundo Artículo de Fe', 12),
  ('Decimotercer Artículo de Fe', 13), ('Décimo tercer Artículo de Fe', 13),
  ('Décima tercera Artículo de Fe', 13),
  # A two-word ordinal shares its first word with a shorter one, so the longer spelling has to win
  ('Décimo Artículo de Fe', 10), ('Décima Artículo de Fe', 10),
])
def test_spanish_ordinal_spellings(text, expected_number):
  assert lookup.get_church_uri(text, lang = 'es') == f'/scriptures/pgp/a-of-f/1.{expected_number}'


# Portuguese cites "Regras de Fé", so the feminine forms are the ones that occur, but the masculine and the
# classical single-word spellings resolve too
@pytest.mark.parametrize('text, expected_number', [
  ('Primeira regra de fé', 1), ('Primeiro regra de fé', 1),
  ('Décima primeira regra de fé', 11), ('Undécima regra de fé', 11), ('Undécimo regra de fé', 11),
  ('Duodécima regra de fé', 12), ('Décimo segundo regra de fé', 12),
  ('Décima regra de fé', 10),
])
def test_portuguese_ordinal_spellings(text, expected_number):
  assert lookup.get_church_uri(text, lang = 'pt') == f'/scriptures/pgp/a-of-f/1.{expected_number}'


# Abbreviated ordinals used as a book number
@pytest.mark.parametrize('text, lang, expected_uri', [
  ('2d Néphi 3:7', 'fr', '/scriptures/bofm/2-ne/3.7'),
  ('2de Néphi 3:7', 'fr', '/scriptures/bofm/2-ne/3.7'),
  ('Second Néphi 3:7', 'fr', '/scriptures/bofm/2-ne/3.7'),
  ('3er Nefi 3:7', 'es', '/scriptures/bofm/3-ne/3.7'),
])
def test_abbreviated_ordinals_as_book_numbers(text, lang, expected_uri):
  assert lookup.get_church_uri(text, lang = lang) == expected_uri


# An ordinal matched with its accent left out resolves to the same number, since the character classes in the
# pattern accept spellings that aren't listed as forms
@pytest.mark.parametrize('text, lang, expected_uri', [
  ('Decimo articulo de fe', 'es', '/scriptures/pgp/a-of-f/1.10'),
  ('decimo primer articulo de fe', 'es', '/scriptures/pgp/a-of-f/1.11'),
  ('Deuxieme article de foi', 'fr', '/scriptures/pgp/a-of-f/1.2'),
  ('Premier Nephi 3:7', 'fr', '/scriptures/bofm/1-ne/3.7'),
])
def test_ordinals_resolve_without_their_accents(text, lang, expected_uri):
  assert lookup.get_church_uri(text, lang = lang) == expected_uri


# Rewriting an ordinal or a written-out book number is cleanup, so skip_cleanup skips it
def test_skip_cleanup_leaves_written_out_numbers_alone():
  assert lookup.get_church_uri('Premier article de foi', lang = 'fr', skip_cleanup = True) == ''
  assert lookup.get_church_uri('1st John 3:2', skip_cleanup = True) != '/scriptures/nt/1-jn/3.2'


# Parsing resolves a book name that's off by one character, which detection can't see on its own
@pytest.mark.parametrize('text, lang, expected_label', [
  ('Genesus 1:1', 'en', 'Genesis\xa01:1'),
  ('Helamen 5:12', 'en', 'Helaman\xa05:12'),
  ('Doctrine and Covenant 4:1', 'en', 'Doctrine and Covenants\xa04:1'),
  ('Doctrine et Alliance 4:1', 'fr', 'Doctrine et Alliances 4:1'),
  # Diacritics are folded before the comparison, so an accent is never what's off – in either direction,
  # and whichever language was asked for
  ('2 Nephi 3', 'fr', '2\xa0Néphi 3'),
  ('2 Néphi 3', 'en', '2\xa0Nephi\xa03'),
  (unicodedata.normalize('NFD', '2 Néphi 3'), 'fr', '2\xa0Néphi 3'),
])
def test_book_names_off_by_one_character_are_resolved(text, lang, expected_label):
  assert lookup.get_label(text, lang = lang) == expected_label


# A name too short to spare a character is left alone, or "Alma" would match far too much ordinary text
def test_short_book_names_are_not_matched_loosely():
  assert lookup.get_label('Alm 5', lang = 'en') == '5'


# A digit is which book is meant, not something that can be mistyped into another book. "4th Nephi" is a
# real name one substitution away from "5th Nephi", and must not be matched.
@pytest.mark.parametrize('text', ['5th Nephi 1:1', '9th Nephi 1:1'])
def test_loose_matching_never_changes_a_digit(text):
  assert lookup.get_church_uri(text) == ''


# skip_cleanup promises consistently formatted input, so it skips the loose comparison too
def test_skip_cleanup_does_not_resolve_misspelled_book_names():
  assert lookup.get_label('Genesus 1:1', lang = 'en', skip_cleanup = True) == '1:1'
  assert lookup.get_label('Genesis 1:1', lang = 'en', skip_cleanup = True) == 'Genesis\xa01:1'
