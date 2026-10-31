import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--timeout", type=int)
parser.add_argument("--retries", type=int, default=3)

CACHE_TTL = 300
