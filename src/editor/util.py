from collections import defaultdict, Counter
import time
import itertools


class BasicProfile():
    def __init__(self):
        self.stats = defaultdict(list)
        self.totals = Counter()
        self.totals_counts = Counter()
        self.current = {}
    def start(self, name):
        self.current[name] = time.time()
    def end(self, name):
        duration = time.time() - self.current[name]
        self.stats[name].append(duration)
        self.totals[name] += duration
        self.totals_counts[name] += 1

        del self.current[name]
    def __repr__(self):
        avgs = {(k,v/self.totals_counts[k]) for k,v in self.totals.items()}
        return str({"cum": self.totals, "avg" : avgs})


PROFILE = BasicProfile()


def flatten_list(lst_of_lst):
    return list(itertools.chain(*lst_of_lst))


def clone_multiply_list(lst, count):
    return flatten_list([l.clone() for l in lst] for _ in range(count))


def first(lst, func):
    for elm in lst:
        if func(elm):
            return elm
