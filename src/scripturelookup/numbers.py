# Python standard libraries
import sys
import importlib

# Third-party libraries
GeezGeezify = importlib.import_module('geezify-python-main.geezify', package='...').Geezify
GeezArabify = importlib.import_module('geezify-python-main.arabify', package='...').Arabify


# Format a positive whole number to a specified language or numeral system
# Either a target_lang, target_format, or target_custom_numerals must be provided
# Supported target formats:
#   --- STANDARD DECIMAL ---
#   decimal-int (ex: 14)
#   decimal-string (ex: '14') – default for most languages
#   --- SIMPLE CONVERSION ---
#   arabic-eastern (ex: ١٤) – default if target_lang is 'ar'
#   arabic-extended (ex: ۱۴) – default if target_lang is 'fa' OR 'ur'
#   devangari (ex: १४) – default if target_lang is 'ne'
#   khmer (ex: ១៤) – default if target_lang is 'km'
#   myanmar (ex: ၁၄) – default if target_lang is 'my'
#   thai (ex: ๑๔) – default if target_lang is 'th'
#   custom – requires numerals 0–9 to be passed in as a list
#   --- COMPLEX CONVERSION ---
#   chinese-simplified (ex: 十四)
#   chinese-traditional (ex: 十四)
#   decimal-fullwidth (ex: '14') – uses full-width numeral only if the number is a single digit
#   geez (ex: ፲፬) – default if target_lang is 'am'
#   roman-upper (ex: 'XIV')
#   roman-lower (ex: 'xiv')
#   alphabet-upper (ex: 'N')
#   alphabet-lower (ex: 'n')
def get_formatted_number(number, target_lang = None, target_format = None, target_custom_numerals = []):
  formatted_number = ''
  
  try:
    int_number = abs(convert_number_to_int(number))
  except:
    # Number can't be formatted (ex: 56-57 OR fac-1)
    return formatted_number
    
  if target_custom_numerals:
    target_format = 'custom'
  if not target_format:
    if target_lang in ('ar',):
      target_format = 'arabic-eastern'
    elif target_lang in ('fa', 'ur',):
      target_format = 'arabic-extended'
    elif target_lang in ('ne',):
      target_format = 'devangari'
    elif target_lang in ('km',):
      target_format = 'khmer'
    elif target_lang in ('my',):
      target_format = 'myanmar'
    elif target_lang in ('th',):
      target_format = 'thai'
    elif target_lang in ('am',):
      target_format = 'geez'
    else:
      target_format = 'decimal-string'
  
  # Numerals 0–9: ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
  simple_numeral_mapping = {
    'arabic-eastern': ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'],
    'arabic-extended': ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'],
    'devangari': ['०', '१', '२', '३', '४', '५', '६', '७', '८', '९'],
    'khmer': ['០', '១', '២', '៣', '៤', '៥', '៦', '៧', '៨', '៩'],
    'myanmar': ['၀', '၁', '၂', '၃', '၄', '၅', '၆', '၇', '၈', '၉'],
    'thai': ['๐', '๑', '๒', '๓', '๔', '๕', '๖', '๗', '๘', '๙'],
    'custom': target_custom_numerals,
  }
  
  if int_number is not None:
    # Standard decimal
    if target_format == 'decimal-int':
      formatted_number = int_number
    elif target_format == 'decimal-string':
      formatted_number = str(int_number)
    
    # Simple conversion
    elif target_format in ('arabic-eastern', 'arabic-extended', 'devangari', 'khmer', 'myanmar', 'thai', 'custom'):
      formatted_number = ''
      for digit in str(int_number):
        formatted_number += simple_numeral_mapping[target_format][int(digit)]
    
    # Complex conversion
    elif target_format == 'chinese-simplified':
      formatted_number = format_number_chinese(int_number, script = 'Hans')
    elif target_format == 'chinese-traditional':
      formatted_number = format_number_chinese(int_number, script = 'Hant')
    elif target_format == 'decimal-fullwidth':
      formatted_number = format_number_fullwidth(int_number, convert_one_digit = True, convert_two_digits = False, convert_more_than_two_digits = False)
    elif target_format == 'geez':
      formatted_number = format_number_geez(int_number)
    elif target_format == 'roman-upper':
      formatted_number = format_number_roman(int_number, uppercase = True)
    elif target_format == 'roman-lower':
      formatted_number = format_number_roman(int_number, uppercase = False)
    elif target_format == 'alphabet-upper':
      formatted_number = format_number_alphabet(int_number, uppercase = True)
    elif target_format == 'alphabet-lower':
      formatted_number = format_number_alphabet(int_number, uppercase = False)
  
  return formatted_number
  

# Convert a formatted number to an integer
def convert_number_to_int(number, advanced_conversion_types = ['chinese', 'geez']):
  int_number = None
  
  if isinstance(number, int) or isinstance(number, float):
    int_number = int(number)
  
  elif isinstance(number, str) and len(number) > 0:
    number = number.strip()
    try:
      int_number = int(number)
    except:
      if 'chinese' in advanced_conversion_types and all(char in ['〇', '零', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '百', '千', '万', '萬', '亿', '億'] for char in number):
        int_number = chinese_numerals_to_int(number)
      elif 'geez' in advanced_conversion_types and all(char in ['፲', '፳', '፴', '፵', '፶', '፷', '፸', '፹', '፺', '፻'] for char in number):
        int_number = geez_numerals_to_int(number)
      elif 'roman' in advanced_conversion_types and all(char in ['I', 'V', 'X', 'L', 'C', 'D', 'M', 'i', 'v', 'x', 'l', 'c', 'd', 'm'] for char in number):
        int_number = roman_numerals_to_int(number)
      elif 'alphabet' in advanced_conversion_types and all(char in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z'] for char in number):
        int_number = alphabet_numerals_to_int(number)
      else:
        int_number = number
  
  return int_number or None


# Convert a formatted number (Chinese numerals) to an integer
def chinese_numerals_to_int(number):
  # TODO: Not yet implemented
  sys.stdout.write('Warning: Conversion from Chinese numerals to an integer is not yet implemented.\n')
  pass


# Convert a formatted number (Geʽez numerals) to an integer
def geez_numerals_to_int(number):
  return GeezArabify.arabify(number)


# Convert a formatted number (Roman numerals) to an integer
# Algorithm adapted from:
#   https://stackoverflow.com/a/48557664
#   License: CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/)
def roman_numerals_to_int(number):
  number = number.upper()
  int_number = 0
  
  roman_numeral_values = { 'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000 }
  for i, c in enumerate(number):
    if (i + 1) == len(number) or roman_numeral_values[c] >= roman_numeral_values[number[i + 1]]:
      int_number += roman_numeral_values[c]
    else:
      int_number -= roman_numeral_values[c]
  
  return int_number


# Convert a formatted number (alphabet numerals) to an integer
def alphabet_numerals_to_int(number):
  number = number.upper()
  
  # Algorithm adapted from:
  #   https://stackoverflow.com/a/63013258
  #   License: CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/)
  def recursive_letters_to_number(s):
    n = ord(s[-1]) - 64
    if s[:-1]:
      return 26 * (recursive_letters_to_number(s[:-1])) + n
    else:
      return n
  
  return recursive_letters_to_number(number)


# Convert an integer to Chinese numerals
def format_number_chinese(int_number, script = 'Hans'):
  int_number = int(int_number)
  # TODO: Not yet implemented
  sys.stdout.write('Warning: Conversion from an integer to Chinese numerals is not yet implemented.\n')
  return str(int_number)


# Convert an integer to fullwidth numerals
def format_number_fullwidth(int_number, convert_one_digit = True, convert_two_digits = False, convert_more_than_two_digits = False):
  num_digits = len(str(int_number))
  fullwidth_numerals = ['０', '１', '２',	'３',	'４',	'５',	'６',	'７',	'８',	'９']
  
  if (num_digits == 1 and convert_one_digit) or (num_digits == 2 and convert_two_digits) or (num_digits > 2 and convert_more_than_two_digits):
    formatted_number = ''
    for digit in str(int_number):
      formatted_number += fullwidth_numerals[int(digit)]
  else:
    formatted_number = str(int_number)
  
  return formatted_number


# Convert an integer to Geʽez numerals
def format_number_geez(int_number):
  int_number = int(int_number)
  return GeezGeezify.geezify(int_number)


# Convert an integer to Roman numerals
# Corresponds to /r or /R number style in PDF specification (/PageLabels)
# Algorithm adapted from:
#   https://stackoverflow.com/a/35728954
#   License: CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/)
def format_number_roman(int_number, uppercase = True):
  int_number = int(int_number)
  formatted_number = ''
  
  if int_number < 1:
    return formatted_number
  
  while int_number >= 1000:
    formatted_number += 'm'
    int_number -= 1000
  
  diffs = [900, 500, 400, 300, 200, 100, 90, 50, 40, 30, 20, 10, 9, 5, 4, 3, 2, 1]
  digits = ['cm', 'd', 'cd', 'ccc', 'cc', 'c', 'xc', 'l', 'xl', 'xxx', 'xx', 'x', 'ix', 'v', 'iv', 'iii', 'ii', 'i']
  
  for i in range(len(diffs)):
    if int_number >= diffs[i]:
      formatted_number += digits[i]
      int_number -= diffs[i]
  
  if uppercase:
    formatted_number = formatted_number.upper()
  
  return formatted_number


# Convert an integer to alphabet numerals (A, B, … Z, AA, AB, … AZ, etc.)
# Corresponds to /a or /A number style in PDF specification (/PageLabels)
# Also corresponds to how columns are numbered in a spreadsheet
def format_number_alphabet(int_number, uppercase = True):
  int_number = int(int_number)
  formatted_number = ''
  
  if int_number < 1:
    return formatted_number
  
  # Algorithm adapted from:
  #   https://stackoverflow.com/a/63013258
  #   License: CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/)
  def recursive_number_to_letters(n):
    letters = list('abcdefghijklmnopqrstuvwxyz')
    n, remainder = divmod(n - 1, 26)
    char = letters[remainder]
    if n:
      return recursive_number_to_letters(n) + char
    else:
      return char

  formatted_number = recursive_number_to_letters(int_number)
  
  if uppercase:
    formatted_number = formatted_number.upper()
  
  return formatted_number

