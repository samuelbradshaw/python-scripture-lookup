# Python standard libraries
import argparse
import inspect

# Internal imports
from . import lookup

def main_cli():
  parser = argparse.ArgumentParser(description='Scripture lookup')
  parser.add_argument('command', help='Command to run. Required.')
  parser.add_argument('input', nargs='?', default='', help='Input text to parse (one or more references). Not needed for commands that don’t take input, such as refresh_metadata.')
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
  parser.add_argument('--skip_cleanup', action='store_true', help='Skip cleanup of the input string for faster parsing.')
  parser.add_argument('--range_split_limit', type=int, help='Threshold where a range of sequential verses will be split into separate verse groups. Default: 1.')
  
  args = parser.parse_args()
  
  command = getattr(lookup, args.command, None)
  if not callable(command) or args.command.startswith('_'):
    parser.error(f'Unknown command: “{args.command}”. See README.md for the list of commands.')

  # Some commands (refresh_metadata, get_langs, get_punctuation, get_numerals) don't take input text
  command_takes_input = 'input_string' in inspect.signature(command).parameters
  if command_takes_input and not args.input:
    parser.error(f'The “{args.command}” command needs input text.')

  options = dict(
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
    skip_cleanup = args.skip_cleanup,
    range_split_limit = args.range_split_limit or 1,
  )
  result = command(args.input, **options) if command_takes_input else command(**options)

  print(result)
