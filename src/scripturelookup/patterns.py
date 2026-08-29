# Regex patterns used for parsing and detecting scripture references.
#
# Patterns ending in "_pattern" are strings, since they get interpolated into larger patterns.
# Everything else is compiled once here, rather than being rebuilt every time a reference is parsed.

# Python standard libraries
import re

# Internal imports
from . import data


# Separators and parentheses, gathered from the punctuation used across all languages
reference_separators_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['referenceSeparator']] + [re.escape(';'), re.escape('|'), re.escape('•'), re.escape('\n')])
chapter_verse_separators_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['chapterVerseSeparator']] + [re.escape(':'), re.escape('.')])
verse_group_separators_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['verseGroupSeparator']] + [re.escape(',')])
# The dashes here cover the ones typesetting substitutes for a plain hyphen, which look identical in print but aren't the same character: U+2010 hyphen, U+2011 non-breaking hyphen (common in engraved music, so a range never wraps), U+2012 figure dash, and U+2212 minus sign. An em dash is left out, since it separates clauses in ordinary prose.
verse_range_separators_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['verseRangeSeparator']] + [re.escape(s) for s in ('-', '–', '〜', '~', '‐', '‑', '‒', '−',)])
# Chapter/verse separators that can have whitespace around them, as in the French "D&A 110 :11-16". A period is left out: it's also an abbreviation mark and a sentence ending, so "Alma 32. 5 people came" would otherwise read as "Alma 32:5". The other separators are unambiguous.
chapter_verse_separators_allowing_space_pattern = r'|'.join([s for s in chapter_verse_separators_pattern.split(r'|') if s != re.escape('.')])

opening_parenthesis_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['openingParenthesis']] + [re.escape('(')])
closing_parenthesis_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['closingParenthesis']] + [re.escape(')')])

# A reference can't start in the middle of a word, or after a hyphen. Used in front of a book name.
reference_start_boundary_pattern = r'(?<![-\w])'
# A name can't be followed by another letter, or a short abbreviation would match inside a longer word – "Al" (Alma) inside "Alliances". A word boundary won't do, since many abbreviations end in a period ("Gen."), where "\b" behaves backwards.
not_followed_by_letter_pattern = r'(?![^\W\d_])'

# Any Unicode whitespace character – newlines, tabs, non-breaking spaces, ideographic spaces, and so on
whitespace = re.compile(r'\s')
# The same, except line breaks, which separate one reference from the next
whitespace_except_line_breaks = re.compile(r'[^\S\n]')

# Separators between references, chapters, verses, and verse groups
reference_separators = re.compile(reference_separators_pattern)
chapter_verse_separators = re.compile(chapter_verse_separators_pattern)
verse_group_separators = re.compile(verse_group_separators_pattern)
verse_range_separators = re.compile(verse_range_separators_pattern)
verse_group_separators_repeated = re.compile(rf'(?:{verse_group_separators_pattern})+')
opening_parenthesis = re.compile(opening_parenthesis_pattern)
closing_parenthesis = re.compile(closing_parenthesis_pattern)

# Whitespace around a separator that sits between two numbers, which is where it's safe to remove: a separator between two digits is always part of the reference, so nothing else can be meant by it. Examples: "110 :11-16" –> "110:11-16"; "Genesis 1 – 3" –> "Genesis 1–3". Line breaks are left alone, since they separate one reference from the next.
separator_whitespace_between_digits = re.compile(rf'(?<=\d)[^\S\n]*({chapter_verse_separators_allowing_space_pattern}|{verse_range_separators_pattern}|{verse_group_separators_pattern})[^\S\n]*(?=\d)')

# A chapter/verse separator, with whitespace allowed around the ones that can take it, so the French "110 :11-16" reads the same as "110:11-16". Shared with the detection pattern's number separator, so the rule about which separators allow a space lives in one place.
chapter_verse_separator_pattern = rf'\s*(?:{chapter_verse_separators_allowing_space_pattern})\s*|(?:{chapter_verse_separators_pattern})'

# The same, required to sit between two digits, so the period in an abbreviation like "Gen." isn't mistaken for one
chapter_verse_separator_between_digits = re.compile(rf'(?<=\d)(?:{chapter_verse_separator_pattern})(?=\d)')
# A range of chapters. Example: "1–5"
chapter_range = re.compile(rf'\d+(?:{verse_range_separators_pattern})\d+')

# Anything that can follow the first digit of a chapter or verse: another digit, whitespace, or any separator
number_continuation_pattern = rf'\d|\s|{chapter_verse_separators_pattern}|{verse_range_separators_pattern}|{verse_group_separators_pattern}'
# A string made up entirely of numbers and separators. Example: "3, 5–7"
numbers_and_separators = re.compile(rf'^\d(?:{number_continuation_pattern})*$')
# The chapter and verses at the end of a reference, so the book name can be split off the front
trailing_chapter = re.compile(rf'^.*?(\d(?:{number_continuation_pattern})*)$')
# Text after the end of a reference. Example: "1 John 3:2 2" –> " 2"
trailing_text = re.compile(rf'^.*?\d((?:\:|{closing_parenthesis_pattern})?\s+[^{opening_parenthesis_pattern}|\s]+)$')
# A parenthetical at the end of a reference, which holds context verses. Example: "Gen. 1:3 (3–4)"
trailing_parenthetical = re.compile(rf'^(.*?)\s*(?:{opening_parenthesis_pattern})([^)）]*)(?:{closing_parenthesis_pattern})$')

# The number a book name starts with, split from the rest of the name. Example: "1 Nephi" –> "1", "Nephi"
leading_book_number = re.compile(rf'^([1-{data.highest_book_number}])\s(.+)$')

# A single digit. Every reference needs a chapter number, so text with no digits anywhere can't contain one.
any_digit = re.compile(r'\d')

# A detection that ends on a reference separator followed by a bare number, which may belong to a book name that follows rather than to the reference. Example: "Luc 2:10-11 | 2" in "Luc 2:10-11 | 2 Nephi 3"
trailing_bare_number = re.compile(rf'(?:{reference_separators_pattern})\s*(\d{{1,3}})\s*$')
# A word following the end of a detection. There's no "^" or "\A" here – .match() already anchors at its starting position, and neither of those would match there.
following_word = re.compile(r'[^\W\d_]\S*')


# Build a regex alternation that matches any of the given words, sharing common prefixes so the regex
# engine doesn't retry every word at every position. Example: ["Genesis", "Genes"] –> "Gene(?:sis|s)".
# Shared prefixes make this several times faster than a flat "Genesis|Genes" alternation, which the
# engine has to walk one branch at a time. Longer words still win over shorter ones that they start
# with, because the trailing group is greedy.
#
# Each character can be given its own sub-pattern, for names where a character shouldn't be matched
# literally – see character_patterns in build_book_names_pattern.
def build_trie_pattern(words, character_patterns = None, case_insensitive = True):
  character_patterns = character_patterns or {}

  # Characters that differ only by case have to share a trie node, since the pattern is meant to be
  # compiled with re.IGNORECASE. Without this, "OP" and "Opisyal" would sit in sibling branches, and
  # "OP" would win on the input "Opisyal" – a flat alternation avoids that by sorting longest first.
  def trie_key(character):
    lowercased = character.lower()
    return lowercased if case_insensitive and len(lowercased) == 1 else character

  trie = {}
  for word in words:
    node = trie
    for character in word:
      node = node.setdefault(trie_key(character), {})
    node[''] = {}

  def build_branch(node):
    # A node with nothing but an end marker is the end of a word
    if '' in node and len(node) == 1:
      return None

    branches = []
    word_ends_here = False
    for character, child_node in sorted(node.items()):
      if character == '':
        word_ends_here = True
        continue
      remainder = build_branch(child_node)
      character_pattern = character_patterns.get(character) or re.escape(character)
      branches.append(character_pattern + (f'(?:{remainder})' if remainder and len(remainder) > 1 else (remainder or '')))

    branch_pattern = r'|'.join(branches)
    return f'(?:{branch_pattern})?' if word_ends_here else branch_pattern

  return build_branch(trie)


# Get compiled regexes for normalizing the words that can appear in a reference in a given language
normalization_pattern_cache = {}
def get_normalization_patterns(lang):
  if lang not in normalization_pattern_cache:
    words = data.get_reference_words(lang)

    # A conjunction sits between two numbers, so it needs whitespace on both sides. A verse or chapter word can also start the string.
    conjunction_template = r'\s+(?:{words})\s+(\d+)'
    reference_word_template = r'(?:^|\s)(?:{words})\s+(\d+)'
    templates = {
      'list_conjunctions': conjunction_template,
      'range_conjunctions': conjunction_template,
      'verse_words': reference_word_template,
      'chapter_words': reference_word_template,
    }

    normalization_patterns = {}
    for key in data.reference_word_keys:
      template = templates[key]
      normalization_patterns[key] = re.compile(template.format(words = words[key]), flags=re.IGNORECASE) if words[key] else None
    normalization_pattern_cache[lang] = normalization_patterns
  return normalization_pattern_cache[lang]
