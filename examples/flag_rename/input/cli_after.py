import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--deadline", type=int)
parser.add_argument("--retries", type=int, default=5)

CACHE_TTL = 900
