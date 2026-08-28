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
verse_range_separators_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['verseRangeSeparator']] + [re.escape('-'), re.escape('–'), re.escape('〜'), re.escape('~')])
opening_parenthesis_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['openingParenthesis']] + [re.escape('(')])
closing_parenthesis_pattern = r'|'.join([re.escape(s.strip()) for s in data.scriptures['summary']['punctuation']['closingParenthesis']] + [re.escape(')')])

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

# A chapter/verse separator that sits between two digits, so the period in an abbreviation like "Gen." isn't mistaken for one
chapter_verse_separator_between_digits = re.compile(rf'(?<=\d)(?:{chapter_verse_separators_pattern})(?=\d)')
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

# English roman numeral prefixes, paired with the number they stand for. Example: "II Corinthians" –> "2 Corinthians"
roman_numerals = [
  (re.compile(r'\bi\s', flags=re.IGNORECASE), '1'),
  (re.compile(r'\bii\s', flags=re.IGNORECASE), '2'),
  (re.compile(r'\biii\s', flags=re.IGNORECASE), '3'),
  (re.compile(r'\biv\s', flags=re.IGNORECASE), '4'),
]
# Matches any of the prefixes above, so a string with no roman numeral at all – which is most of them – can skip the substitutions entirely
any_roman_numeral = re.compile(r'\b(?:i|ii|iii|iv)\s', flags=re.IGNORECASE)

# A single digit. Every reference needs a chapter number, so text with no digits anywhere can't contain one.
any_digit = re.compile(r'\d')


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
