# Python standard libraries
import argparse

# Internal imports
from . import data, numbers, lookup

def main_cli():
  parser = argparse.ArgumentParser(description='Scripture lookup')
  parser.add_argument('command', help='Command to run. Required.')
  parser.add_argument('input', help='Input text to parse (one or more references).')
  parser.add_argument('--lang', help='Output language. Default: "en".')
  parser.add_argument('--separator', help='Separator when there are multiple results. Default: "\n".')
  parser.add_argument('--sort-by', help='Sort the returned references ("none", "traditional", or "label"). Default: "none".')
  parser.add_argument('--source', help='Content source ("python-scripture-scraper" or "ChurchofJesusChrist.org"). Default: "python-scripture-scraper".')
  parser.add_argument('--link_class', help='Link "class" attribute.')
  parser.add_argument('--link_target', help='Link "target" attribute.')
  parser.add_argument('--use_query_parameters', action='store_true', help='Use "id" and "context" parameters in URIs.')
  parser.add_argument('--skip_lang', action='store_true', help='Skip "lang" parameter in URLs.')
  parser.add_argument('--skip_fragment', action='store_true', help='Skip #frament in URLs.')
  parser.add_argument('--skip_book_name', action='store_true', help='Skip scripture book name in labels.')
  parser.add_argument('--abbreviated', action='store_true', help='Prefer abbreviated scripture book name in labels.')
  
  args = parser.parse_args()
  
  command = getattr(lookup, args.command)
  result = command(
    args.input,
    lang = args.lang or 'en',
    separator = args.separator or '\n',
    sort_by = args.sort_by,
    source = args.source or 'python-scripture-scraper',
    link_class = args.link_class,
    link_target = args.link_target,
    use_query_parameters = args.use_query_parameters,
    skip_lang = args.skip_lang,
    skip_fragment = args.skip_fragment,
    skip_book_name = args.skip_book_name,
    abbreviated = args.abbreviated,
  )
  
  print(result)
