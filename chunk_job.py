from python.distant_vfx.jobs import chunk_to_new_packages
import sys


# A quick entry point for the chunk_to_new_packages job.
def main():
    chunk_to_new_packages.main(sys.argv[1], sys.argv[2:])


if __name__ == '__main__':
    main()
