"""Edit a single raw FM2 pattern or sequence SysEx; never sends MIDI."""
from pathlib import Path
import argparse
import json
from probability_format import (read_sequence_file,write_sequence_file,
                                get_profile,set_profile,clear_profile)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('output',nargs='?',type=Path)
    parser.add_argument('--set',dest='assignments',action='append',default=[],metavar='STEP=PERCENT')
    parser.add_argument('--profile',type=Path,help='JSON array of 16 percentages')
    parser.add_argument('--clear',action='store_true')
    args = parser.parse_args(argv)
    if args.clear and (args.assignments or args.profile):
        parser.error('--clear cannot be combined with --set/--profile')
    pattern,prefix,suffix = read_sequence_file(args.input.read_bytes())
    values,enabled = get_profile(pattern)
    if args.profile:
        values = json.loads(args.profile.read_text())
    for text in args.assignments:
        try:
            step,pct = map(int,text.split('='))
        except ValueError:
            parser.error('Use --set STEP=PERCENT, for example --set 2=50')
        if not 1 <= step <= 16 or not 0 <= pct <= 100:
            parser.error('STEP must be 1..16 and PERCENT 0..100')
        values[step-1] = pct
    editing = bool(args.clear or args.profile or args.assignments)
    if editing:
        if args.output is None:
            parser.error('An output path is required for edits')
        if args.input.resolve() == args.output.resolve():
            parser.error('Choose a separate output file to preserve the input')
        updated = clear_profile(pattern) if args.clear else set_profile(pattern,values)
        args.output.write_bytes(write_sequence_file(updated,prefix,suffix))
        values,enabled = get_profile(updated)
        print('Written:',args.output)
    elif args.output is not None:
        parser.error('Specify an edit or omit the output path')
    print(json.dumps({'extension_valid':enabled,'step_percentages':values},indent=2))


if __name__ == '__main__':
    main()
