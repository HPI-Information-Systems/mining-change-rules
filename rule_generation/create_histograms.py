#!/usr/bin/python3

import argparse
import json
import math
import multiprocessing as mp
import os
import queue
from collections import defaultdict
from datetime import datetime
from itertools import product
import random
from time import time


def parse_args():
    min_sup_default = 0.05
    max_sup_default = 0.1
    min_conf_default = 0.9
    thread_default = 10
    bin_default = 11
    partition_default = 200

    ap = argparse.ArgumentParser(description="Discovers change dependencies.")
    ap.add_argument(
        "change_file",
        type=str,
        help="File with occurrences per change (expect Python dict as JSON)",
    )
    ap.add_argument(
        "timepoint_file",
        type=str,
        help="File with list of dates (JSON file)",
    )
    ap.add_argument("output", type=str, help=f"Output file path")
    ap.add_argument(
        "--min_sup",
        type=float,
        help=f"Minimal support. Default {min_sup_default}",
        default=min_sup_default,
    )
    ap.add_argument(
        "--max_sup",
        type=float,
        help=f"Maximal support. Default {max_sup_default}",
        default=max_sup_default,
    )
    ap.add_argument(
        "--min_conf",
        type=float,
        help=f"Minimal Confidence. Default {min_conf_default}",
        default=min_conf_default,
    )
    ap.add_argument(
        "--num_bins",
        type=int,
        help=f"Bin count. Default {bin_default}",
        default=bin_default,
    )
    ap.add_argument(
        "--partition_size",
        "-s",
        type=int,
        help=f"Partition Size. Default {partition_default}",
        default=partition_default,
    )
    ap.add_argument(
        "--threads",
        "-t",
        type=int,
        help=f"Number of threads. Default {thread_default}",
        default=thread_default,
    )
    ap.add_argument(
        "--extensive_log",
        action="store_true",
        help=f"Detailed log messages",
    )
    ap.add_argument(
        "--sample_size",
        type=float,
        help=f"Sample data down to 100*sample_size% of the original",
        default=1.0,
    )
    return vars(ap.parse_args())


class Histogram:
    def __init__(self):
        self._is_setup = False
        self._actual_antecedent = 0
        self._occurrence_count = 0
        self.lift = 0

    def is_setup(self):
        return self._is_setup

    def setup(self, bin_count, occurrences_right):
        if self._is_setup:
            raise RuntimeError(f"{self.__class__.__name__} has already been set up.")
        self._bins = [0 for _ in range(bin_count)]
        self._count_antecedent = occurrences_right
        self._is_setup = True

    def add_occurrence(self, bin):
        if not self._is_setup:
            raise RuntimeError(f"{self.__class__.__name__} needs to be set up first.")
        self._bins[bin] += 1
        self._occurrence_count += 1

    def add_antecedent_occurrence(self):
        self._actual_antecedent += 1

    def antecedent_occurrences(self):
        return self._actual_antecedent

    def bins(self):
        return self._bins

    def confidence(self):
        return self._occurrence_count / self._count_antecedent

    def abs_support(self):
        return self._occurrence_count


class Job:
    def __init__(self, antecedents, consequents):
        self.antecedents = antecedents
        self.consequents = consequents


def log(message, is_debug):
    if is_debug:
        print(f"{datetime.now()} | {message}")


def get_histograms_of_partitions(
    antecedents, daily_antecedents, consequents, daily_consequents, min_sup_abs, min_conf, days, num_bins, do_log
):
    hists = defaultdict(lambda: defaultdict(Histogram))

    # index of changes within num days
    # change -> days since last occurrence
    active_changes = dict()

    # index consequent -> antecedents
    pruned_combinations = defaultdict(set)

    # prohibit self-combinations
    for consequent in consequents:
        pruned_combinations[consequent].add(consequent)

    for date, day_index in zip(days, range(len(days))):
        active_today = dict()
        outdated = set()
        # gather changes of current day, update antecedent counts
        for change in daily_antecedents[date]:
            active_today[change] = 0
            for hist in hists[change].values():
                hist.add_antecedent_occurrence()

        # update time since occurrence for older antecedents
        for change in active_changes:
            active_changes[change] += 1
            if active_changes[change] >= num_bins:
                outdated.add(change)

        # merge, remove too old antecedents
        active_changes.update(active_today)
        for change in outdated:
            del active_changes[change]

        # skip if min support cannot be reached
        can_shortcut_support = len(days) - day_index < num_bins

        antecedent_candidates = set(active_changes.keys())

        # begin with real work:
        for consequent in daily_consequents[date]:
            my_antecedents = antecedent_candidates - pruned_combinations[consequent]
            occurrences_consequent = consequents[consequent]
            ind_today = occurrences_consequent.index(date)
            days_since_last_consequent_occurrence = (
                num_bins if ind_today == 0 else days.index(date) - days.index(occurrences_consequent[ind_today - 1])
            )

            for antecedent in my_antecedents:
                hist = hists[antecedent][consequent]
                occurrences_antecedent = antecedents[antecedent]

                # make sure that consequent has not occurred in between
                days_since_antecedent_occurrence = active_changes[antecedent]
                difference = days_since_antecedent_occurrence - days_since_last_consequent_occurrence
                if difference >= 0:
                    continue

                # check if histogram is already created
                # prune if min confidence or min support cannot be reached
                if not hist.is_setup():
                    maximal_confidence = len(occurrences_consequent) / len(occurrences_antecedent)
                    if can_shortcut_support or maximal_confidence < min_conf:
                        del hists[antecedent][consequent]
                        pruned_combinations[consequent].add(antecedent)
                        continue
                    else:
                        hist.setup(num_bins, len(occurrences_antecedent))

                # prune if antecedent has appeared too often to reach min confidence
                # or too few occurrences are left for reaching min support
                # or max sup is too high
                remaining_antecedent_occurrences = len(occurrences_antecedent) - hist.antecedent_occurrences() + 1
                remaining_consequent_occurrences = len(occurrences_consequent) - occurrences_consequent.index(date)
                possible_occurrences = min(remaining_consequent_occurrences, remaining_antecedent_occurrences)
                can_reach_conf = (hist.abs_support() + possible_occurrences) / len(occurrences_antecedent) >= min_conf
                can_reach_sup = hist.abs_support() + possible_occurrences >= min_sup_abs

                if not (can_reach_conf and can_reach_sup):
                    del hists[antecedent][consequent]
                    pruned_combinations[consequent].add(antecedent)
                    continue

                # actually add value to histogram
                hist.add_occurrence(days_since_antecedent_occurrence)

    del active_changes
    del pruned_combinations

    # remove antecedents without consequents
    # combinations with low min support / confidence may not have been removed previously
    useless_antecedents = set()
    useless_combinations = defaultdict(set)
    for antecedent, my_consequents in hists.items():
        num_useless_combinations = 0
        for consequent, hist in my_consequents.items():
            if hist.abs_support() < min_sup_abs or hist.confidence() < min_conf:
                useless_combinations[antecedent].add(consequent)
                num_useless_combinations += 1
        if len(my_consequents) == num_useless_combinations:
            useless_antecedents.add(antecedent)

    for antecedent in useless_antecedents:
        del hists[antecedent]
        try:
            del useless_combinations[antecedent]
        except KeyError:
            pass

    for antecedent, my_consequents in useless_combinations.items():
        for consequent in my_consequents:
            del hists[antecedent][consequent]

    for antecedent, my_consequents in hists.items():
        ant_support = len(antecedents[antecedent])
        for consequent, hist in my_consequents.items():
            cons_support = len(consequents[consequent])
            hist.lift = hist.abs_support() / (ant_support * cons_support)

    return hists


def create_histograms(args):
    start = datetime.now()
    print("start program:", start)
    min_sup = args["min_sup"]
    max_sup = args["max_sup"]
    sampling_rate = args["sample_size"]
    temp_dir = "change_partitions"
    partition_size = args["partition_size"]

    # get time points of changes for support
    with open(args["timepoint_file"]) as f:
        actual_days = json.load(f)
    min_support_threshold = math.ceil(min_sup * len(actual_days))
    max_support_threshold = math.floor(max_sup * len(actual_days))

    # get index change -> dates
    with open(args["change_file"]) as f:
        all_changes = json.load(f)
        keysSorted = sorted(all_changes.keys())
        toSample = int(sampling_rate * len(keysSorted))
        keysSorted = random.sample(keysSorted, toSample)
        all_changes = {k: all_changes[k] for k in keysSorted}

    whitelist = None
    if "whitelist" in args and args["whitelist"]:
        with open(args["whitelist"]) as f:
            whitelist = set(json.load(f))

    # build index date -> changes
    # remove change if min support to low
    daily_changes = defaultdict(set)
    too_infrequent_changes = set()
    blacklist_changes = set()
    for change, occurrences in all_changes.items():
        if whitelist and (not change.split("_")[0] in whitelist):
            blacklist_changes.add(change)
            continue
        if len(occurrences) < min_support_threshold or len(occurrences) > max_support_threshold:
            too_infrequent_changes.add(change)
            continue
        for date in occurrences:
            daily_changes[date].add(change)
    for change in too_infrequent_changes:
        del all_changes[change]
    for change in blacklist_changes:
        del all_changes[change]

    changes = list(all_changes.keys())
    if whitelist:
        print(f"ignoring changes not within {whitelist}")
    print(f"input: {len(changes)} changes with {min_sup} <= sup(X) <= {max_sup}")

    # partition change index
    partition_buckets = [
        min(partition_size * i, len(changes)) for i in range(math.ceil(len(changes) / partition_size) + 1)
    ]
    if not os.path.isdir(temp_dir):
        os.makedirs(temp_dir)
    time_stamp = time()
    partition_files = []
    for i in range(len(partition_buckets)):
        partition_start = 0 if i == 0 else partition_buckets[i - 1]
        partition_end = partition_buckets[i]
        partition_keys = set(changes[partition_start:partition_end])
        partition = {k: v for k, v in all_changes.items() if k in partition_keys}
        file_name = os.path.join(temp_dir, f"{time_stamp}_partition_{i}.json")
        partition_files.append(file_name)
        with open(file_name, "w") as f:
            json.dump(partition, f)
    num_combinations = len(partition_files) ** 2
    num_threads = args["threads"]
    if num_combinations < num_threads:
        print(
            "[INFO] Number of threads exceeds partition combinations.",
            f"{num_threads - num_combinations} core(s) will not be used.",
        )

    # initialize parallel setup
    with mp.Manager() as manager:
        job_queue = manager.Queue()
        mutex = mp.Lock()
        workers = [
            mp.Process(
                target=task_main,
                args=(
                    f"{n}".rjust(2),
                    job_queue,
                    min_support_threshold,
                    args["min_conf"],
                    args["num_bins"],
                    args["output"],
                    actual_days,
                    mutex,
                    args["extensive_log"],
                ),
            )
            for n in range(num_threads)
        ]

        for a, d in product(partition_files, repeat=2):
            job_queue.put(Job(a, d))

        # start histogram creation
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()

    # cleanup
    for file_name in partition_files:
        os.remove(file_name)
    end = datetime.now()
    print("end program:", end)
    print("duration:", end - start)


def task_main(my_id, jobs, min_support_threshold, min_conf, num_bins, result_file, all_days, mutex, do_log):
    log(f"[Start Worker {my_id}]", True)
    while True:
        try:
            job = jobs.get_nowait()
        except queue.Empty:
            log(f"[Exit Worker {my_id}]", True)
            return

        antecedent_file = job.antecedents
        consequent_file = job.consequents

        log(f"Worker {my_id}: {antecedent_file} - {consequent_file}", do_log)

        # get indexes change -> dates
        with open(antecedent_file) as f:
            antecedents = json.load(f)
        with open(consequent_file) as f:
            consequents = json.load(f)

        # build indexes date -> changes
        daily_antecedents = defaultdict(set)
        for change, occurrences in antecedents.items():
            for date in occurrences:
                daily_antecedents[date].add(change)

        daily_consequents = defaultdict(set)
        for change, occurrences in consequents.items():
            for date in occurrences:
                daily_consequents[date].add(change)

        result = get_histograms_of_partitions(
            antecedents,
            daily_antecedents,
            consequents,
            daily_consequents,
            min_support_threshold,
            min_conf,
            all_days,
            num_bins,
            do_log,
        )

        del antecedents
        del consequents
        del daily_antecedents
        del daily_consequents

        with mutex:
            write_rules(result, result_file)
        del result


def write_rules(rules, result_file):
    with open(result_file, "a") as f:
        for antecedent, consequents in rules.items():
            for consequent, hist in consequents.items():
                hist_string = f"\"[{', '.join([str(x) for x in hist.bins()])}]\""
                f.write(
                    f"{antecedent};{consequent};{hist.abs_support()};{hist.confidence()};{hist.lift};{hist_string}\n"
                )


if __name__ == "__main__":
    create_histograms(parse_args())
