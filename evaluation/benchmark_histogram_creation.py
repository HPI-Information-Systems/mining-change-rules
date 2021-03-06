#!/usr/bin/python3

import argparse
import json
import math
import multiprocessing as mp
import os
import random
import re
import sys
from collections import defaultdict
from contextlib import contextmanager
from time import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + f"{os.sep}..")
from rule_generation.create_histograms import create_histograms


def parse_args():
    ap = argparse.ArgumentParser(description="Benchmarks histogram creation")
    ap.add_argument("change_file", type=str, help="File with index change -> occurrences as Python JSON dictionary")
    ap.add_argument("dates_file", type=str, help="File with dates as JSON list")
    ap.add_argument(
        "--experiments",
        "-e",
        nargs="+",
        default=None,
        type=int,
        help="Experiments to run. Default all",
    )
    ap.add_argument("--keep_logs", "-l", help="Keep log files of benchmark runs", action="store_true")
    ap.add_argument(
        "--log_path", "-p", type=str, help="Path for intermediate log files. Default ./benchmark", default="benchmark"
    )
    ap.add_argument(
        "--output", "-o", type=str, help="Output file. Default none, results are printed to console", default=None
    )
    ap.add_argument("--runs", "-r", type=int, help="Number of runs. Default 3", default=3)
    ap.add_argument(
        "--store_separate",
        "-s",
        help="Store a file for each experiment. Only effective if output file is provided",
        action="store_true",
    )
    return vars(ap.parse_args())


@contextmanager
def capture_log(file_name):
    with open(file_name, "w") as log_file:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = log_file
        sys.stderr = log_file
        try:
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


class ExperimentConfig(dict):
    @classmethod
    def default_values(cls):
        return {
            "change_file": "data/table_changes_aggregated_grouped.json",
            "timepoint_file": "data/actual_days.json",
            "output": "histogram.csv",
            "min_sup": 0.0,
            "max_sup": 1.0,
            "min_conf": 0.9,
            "threads": 10,
            "partition_size": 200,
            "num_bins": 11,
            "extensive_log": False,
            "whitelist": None,
        }

    def __init__(self, init_values=dict()):
        # set default values
        for key, value in self.__class__.default_values().items():
            self[key] = value
        # set user parameters
        for key, value in init_values.items():
            self[key] = value


class BenchmarkResult:
    def __init__(self, num_rules, runtime, input_size):
        self.num_rules = num_rules
        self.runtime = runtime
        self.input_size = input_size

    def __str__(self):
        return f"BenchmarkResult({self.num_rules} rules, runtime {self.runtime} s, {self.input_size} changes)"


class Benchmark:
    def __init__(self, num_runs, output_path, log_path, keep_logs, dates_file, store_all):
        self.num_runs = num_runs
        self.benchmarks = list()
        self.output_path = output_path
        self.output = dict()
        self.log_path = log_path
        self.keep_logs = keep_logs
        self.dates_file = dates_file
        self.experiments_to_run = list()
        self.store_all = store_all

    def add_experiment(self, variable, variable_values, fixed_values):
        self.benchmarks.append((variable, variable_values, fixed_values))

    def run(self):
        start = time()
        self.output["num_runs"] = self.num_runs
        self.output["experiments"] = list()
        if self.output_path:
            output_base_path = self.output_path.split(".")[0]
        print(f"- Run {len(self.experiments_to_run)} benchmarks")
        for benchmark_id in self.experiments_to_run:
            if benchmark_id < 1 or benchmark_id > len(self.benchmarks):
                self.__warn(f"Skipping invalid Experiment number {benchmark_id}")
                continue
            benchmark = self.benchmarks[benchmark_id - 1]
            result = self.__run_experiment(benchmark_id, benchmark[0], benchmark[1], benchmark[2])
            run_summary = {
                value: {
                    "rules": runs[0].num_rules,
                    "runs": [r.runtime for r in runs],
                    "filtered_input": runs[0].input_size,
                }
                for value, runs in result.items()
            }

            fixed_values = ExperimentConfig(benchmark[2])
            del fixed_values[benchmark[0]]
            del fixed_values["output"]
            del fixed_values["extensive_log"]
            del fixed_values["timepoint_file"]

            result_entry = {
                "parameter": benchmark[0],
                "fixed_values": fixed_values,
                "results": run_summary,
            }
            self.output["experiments"].append(result_entry)

            if self.output_path and self.store_all:
                experiment_output = {"num_runs": self.num_runs, "experiments": list()}
                experiment_output["experiments"].append(result_entry)
                experiment_output_path = f"{output_base_path}_experiment-{benchmark_id}.json"
                with open(experiment_output_path, "w") as f:
                    json.dump(experiment_output, f, indent=2)

        end = time()
        print(f"\n- Ran {len(self.experiments_to_run)} experiments in {round(end - start)} s")

        if self.output_path:
            with open(self.output_path, "w") as f:
                json.dump(self.output, f, indent=2)

        if not self.keep_logs:
            for file_name in os.listdir(self.log_path):
                os.remove(os.path.join(self.log_path, file_name))
            os.rmdir(self.log_path)

    def __run_experiment(self, benchmark_index, variable_key, variable_values, fixed_values):
        results = defaultdict(list)
        config = ExperimentConfig(fixed_values)
        config["output"] = os.path.join(self.log_path, "histogram.csv")
        config["timepoint_file"] = self.dates_file
        filtered_input_pattern = re.compile(r"(?<=input:\s)\d+(?=\schanges)")
        time_stamp = time()
        print(f"\nExperiment {benchmark_index}: {variable_key}")

        for value in variable_values:
            config[variable_key] = value
            print(f"{self.__indent(1)}{variable_key} = {value}")
            item_start = time()
            for run in range(1, self.num_runs + 1):
                item_run_start = time()
                p = mp.Process(target=create_histograms, args=[config])
                log_name_value = value if variable_key != "change_file" else value.split(os.sep)[-1]
                log_file = f"log_{time_stamp}_{variable_key}_{log_name_value}_run-{run}.txt"
                log_path = os.path.join(self.log_path, log_file)
                item_run_start = time()
                with capture_log(log_path):
                    p.start()
                    p.join()
                    item_run_end = time()
                runtime = item_run_end - item_run_start
                num_rules = None
                input_size = None

                if p.exitcode == 0:
                    try:
                        with open(config["output"]) as f:
                            num_rules = len(f.readlines())
                        os.remove(config["output"])
                    except FileNotFoundError:
                        self.__warn("Could not open output file.")
                else:
                    self.__warn(f"An error occurred while running the item. See {log_path} for details.")
                    self.keep_logs = True
                try:
                    with open(log_path) as f:
                        for line in f:
                            if line.startswith("input:"):
                                input_size = int(filtered_input_pattern.search(line).group(0))
                except FileNotFoundError:
                    self.__warn(f"Could not open log file {log_path}.")
                except IndexError:
                    self.__warn(f"Malformed log file {log_file}. Could not find filtered input size.")
                    self.keep_logs = True
                results[value].append(BenchmarkResult(num_rules, runtime, input_size))

            item_end = time()
            item_runtime = round(item_end - item_start, 3)
            item_results = results[value]
            mean_runtime = sum([r.runtime for r in item_results]) / self.num_runs
            summary = (
                f"{self.__indent(2)}--> executed {self.num_runs} time(s) "
                + f"in {item_runtime} s"
                + f" ({round(mean_runtime, 3)} s/iter), "
                + f"{item_results[0].num_rules} rules, "
                + f"filtered input: {item_results[0].input_size} changes"
            )
            print(summary)
        return results

    def __indent(self, level):
        return " " * 4 * level

    def __warn(self, message):
        print(f"{self.__indent(2)}[WARNING] {message}\n{self.__indent(3)}Results are not accurate.")


def reduce_changes(change_occurrences, shuffled_changes, num_changes):
    changes_to_keep = set(shuffled_changes[:num_changes])
    keep_occurrences = {
        change: occurrences for change, occurrences in change_occurrences.items() if change in changes_to_keep
    }
    return keep_occurrences


def save_reduced_changes(change_occurrences, shuffled_changes, num_changes, path):
    reduced_changes = reduce_changes(change_occurrences, shuffled_changes, num_changes)
    file_name = os.path.join(path, f"{num_changes}_changes.json")
    with open(file_name, "w") as f:
        json.dump(reduced_changes, f)
    return file_name


def save_reduced_days(change_occurrences, days, num_steps, path):
    indexes = [min(round(i * len(days) / num_steps), len(days) - 1) for i in range(1, num_steps + 1)]
    file_names = list()
    num_changes = len(change_occurrences)

    for index in indexes:
        max_date = days[index]
        num_days = index + 1
        reduced_days = {
            change: [date for date in occurrences if date <= max_date]
            for change, occurrences in change_occurrences.items()
        }
        file_name = os.path.join(path, f"{num_days}_days_{num_changes}_changes.json")
        with open(file_name, "w") as f:
            json.dump(reduced_days, f)
        file_names.append(file_name)

    return file_names


def main(change_file, dates_file, runs, output, log_path, keep_logs, experiments, store_all):
    benchmark = Benchmark(runs, output, log_path, keep_logs, dates_file, store_all)

    if not os.path.isdir(log_path):
        os.makedirs(log_path)

    if output:
        out_path_list = output.split(os.sep)[:-1]
        out_path = os.path.join(*out_path_list)
        if not os.path.isdir(out_path):
            os.makedirs(out_path)
        print(f"- Output is {output}")
        if store_all:
            print(f"- Each experiment is stored separately")
    print(f"- Perform {runs} run(s) per item")
    print(f"- Logs are stored at {log_path}")
    print(f"- Logs will{' not ' if keep_logs else ' '}be deleted after benchmarking")
    random.seed(42)

    with open(change_file) as f:
        all_change_occurrences = json.load(f)
    all_changes = list(all_change_occurrences.keys())
    print(f"- Done reading base dataset {change_file} with {len(all_changes)} changes")
    random.shuffle(all_changes)

    with open(dates_file) as f:
        days = json.load(f)

    partition_sizes = [100, 500, 1000, 1750, 2500, 3750, 5000, 10000, 20000, 50000]
    input_sizes = [1000, 2500, 5000, 7500, 10000, 15000, 20000, 30000, 50000, 100000, 200000]
    sized_inputs = [save_reduced_changes(all_change_occurrences, all_changes, num, log_path) for num in input_sizes]
    base_input = sized_inputs[0]
    changes_1000 = reduce_changes(all_change_occurrences, all_changes, 1000)
    date_differing_inputs = save_reduced_days(changes_1000, days, 10, log_path)
    print(f"- Generated {len(input_sizes) + len(date_differing_inputs)} partial datasets")
    del all_changes
    del all_change_occurrences

    # 1 min confidence [0, 0.05, 0.1, ... 1.0]
    fixed_values = {"change_file": base_input, "threads": 1}
    benchmark.add_experiment("min_conf", [x / 100 for x in range(0, 105, 5)], fixed_values)

    # 2 min support [0, 0.05, 0.1, ..., 1]
    benchmark.add_experiment("min_sup", [x / 100 for x in range(0, 105, 5)], fixed_values)

    # 3 max support [0, 0.05, 0.1, ..., 1]
    benchmark.add_experiment("max_sup", [x / 100 for x in range(0, 105, 5)], fixed_values)

    # 4 1 to 11 bins
    benchmark.add_experiment("num_bins", list(range(1, 12)), fixed_values)

    # 5 number of days [36, 72, ... 359]
    fixed_values = {"threads": 1}
    benchmark.add_experiment("change_file", date_differing_inputs, fixed_values)

    # 6 1 to 15 threads, 1000 changes
    fixed_values = {"change_file": base_input}
    benchmark.add_experiment("threads", list(range(1, 16)), fixed_values)

    # 7 1 to 15 threads, 5000 changes
    fixed_values = {"change_file": sized_inputs[2]}
    benchmark.add_experiment("threads", list(range(1, 16)), fixed_values)

    # 8 partition size, 1000 changes
    input_size = 1000
    fixed_values = {"change_file": sized_inputs[input_sizes.index(input_size)]}
    benchmark.add_experiment("partition_size", partition_sizes, fixed_values)

    # 9 partition size, 5000 changes
    input_size = 5000
    fixed_values = {"change_file": sized_inputs[input_sizes.index(input_size)]}
    benchmark.add_experiment("partition_size", partition_sizes, fixed_values)

    # 10 partition size, 10000 changes
    input_size = 10000
    fixed_values = {"change_file": sized_inputs[input_sizes.index(input_size)]}
    benchmark.add_experiment("partition_size", partition_sizes, fixed_values)

    # 11 partition size, 20000 changes
    input_size = 20000
    fixed_values = {"change_file": sized_inputs[input_sizes.index(input_size)]}
    benchmark.add_experiment("partition_size", partition_sizes, fixed_values)

    # 12 partition size, 30000 changes
    input_size = 30000
    fixed_values = {"change_file": sized_inputs[input_sizes.index(input_size)]}
    benchmark.add_experiment("partition_size", partition_sizes, fixed_values)

    # 13 partition size, 50000 changes
    input_size = 50000
    fixed_values = {"change_file": sized_inputs[input_sizes.index(input_size)]}
    benchmark.add_experiment("partition_size", partition_sizes, fixed_values)

    # 14 partition size, 100000 changes
    input_size = 100000
    fixed_values = {"change_file": sized_inputs[input_sizes.index(input_size)]}
    benchmark.add_experiment("partition_size", partition_sizes, fixed_values)

    # 15 partition size, 200000 changes
    input_size = 200000
    fixed_values = {"change_file": sized_inputs[input_sizes.index(input_size)]}
    benchmark.add_experiment("partition_size", partition_sizes, fixed_values)

    # 16 input sizes
    fixed_values = {}
    benchmark.add_experiment("change_file", sized_inputs, fixed_values)

    if experiments:
        benchmark.experiments_to_run = experiments
    else:
        benchmark.experiments_to_run = list(range(1, len(benchmark.benchmarks) + 1))

    benchmark.run()

    if os.path.isdir(log_path):
        input_files = [file_name for file_name in os.listdir(log_path) if file_name.endswith("_changes.json")]
        for file_name in input_files:
            os.remove(os.path.join(log_path, file_name))


if __name__ == "__main__":
    args = parse_args()
    main(
        args["change_file"],
        args["dates_file"],
        args["runs"],
        args["output"],
        args["log_path"],
        args["keep_logs"],
        args["experiments"],
        args["store_separate"],
    )
