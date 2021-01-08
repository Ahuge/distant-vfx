import argparse
from python.distant_vfx.jobs import new_vendor_package


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument('vendor_codes',
                        nargs='+',
                        type=str,
                        action='store',
                        help='Specify one or more vendor codes to create new packages.')

    parser.add_argument('--multi',
                        type=int,
                        action='store',
                        help='Specify the number of new packages to be created per provided vendor code.')

    args = parser.parse_args()
    if args.multi:
        new_vendor_package.main(vendor_codes=args.vendor_codes,
                                num_packages=args.multi)
    else:
        new_vendor_package.main(vendor_codes=args.vendor_codes)


if __name__ == '__main__':
    main()