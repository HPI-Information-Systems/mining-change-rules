# Discovering Change Dependencies

This is the central code repository of the [_Discovering Change Dependencies_](https://hpi.de/naumann/teaching/master-projects/discovering-change-dependencies.html) master's project at the [chair of Prof. Naumann](https://hpi.de/naumann/home.html) at [HPI](https://hpi.de/).

"Everything changes and nothing stands still." - Heraclitus

Changes in databases occur permanently.
The aim of this project is to discover dependencies within these changes.
We base our research on infobox modifications from [Wikipedia](https://en.wikipedia.org/wiki/Main_Page) and open-government data provided by [Socrata](https://www.tylertech.com/products/socrata).
For the Wikipedia data, changes of infoboxes have been extracted [previously](https://hpi.de/naumann/projects/data-profiling-and-analytics/change-exploration/structured-object-matching-across-web-page-revisions.html).

For Socrata, all public datasets have been received before on a daily basis during one year as part of the [IANVS project](https://hpi.de/naumann/projects/data-profiling-and-analytics/change-exploration.html).
Pre-processing has been done to identify columns and rows, thus, our data basis consists of completely re-constructed relational tables as JSON files.
Whenever such a table is being changed, there is a file in our dataset containing the whole table, corresponding to the time point of the change.
Out of these files, we extract the changes, transform them, and generate rules for change dependencies.


## Citation
When referencing the CR-Miner algorithm, please use the following bibtex entry:
<details><summary>(click to expand)</summary>

```bibtex
@inproceedings{DBLP:conf/edbt/LindnerSABBN22,
  author       = {Daniel Lindner and
                  Franziska Schumann and
                  Nicolas Alder and
                  Tobias Bleifu{\ss} and
                  Leon Bornemann and
                  Felix Naumann},
  editor       = {Julia Stoyanovich and
                  Jens Teubner and
                  Paolo Guagliardo and
                  Milos Nikolic and
                  Andreas Pieris and
                  Jan M{\"{u}}hlig and
                  Fatma {\"{O}}zcan and
                  Sebastian Schelter and
                  H. V. Jagadish and
                  Meihui Zhang},
  title        = {Mining Change Rules},
  booktitle    = {Proceedings of the 25th International Conference on Extending Database
                  Technology, {EDBT} 2022, Edinburgh, UK, March 29 - April 1, 2022},
  pages        = {2:91--2:103},
  publisher    = {OpenProceedings.org},
  year         = {2022},
  url          = {https://doi.org/10.48786/edbt.2022.01},
  doi          = {10.48786/edbt.2022.01},
  timestamp    = {Tue, 11 Oct 2022 14:23:40 +0200},
  biburl       = {https://dblp.org/rec/conf/edbt/LindnerSABBN22.bib},
  bibsource    = {dblp computer science bibliography, https://dblp.org}
}
```
</details>

## exploration
Scripts to get in touch with the data.

`find_nulls.py` is used to get an overview of the usage of common representations of `NULL`.

`count_changes.py` aggregates extracted change data s.t. we get an overview on how often changes occcur.

`aggregated_change_counts.py` summarizes the number of aggregated changes per entity level and change type.

`wiki_infoboxes.py` extracts how often specific Wikipedia infobox templates exist in the data.

`wiki_pages_per_template.py` counts infobox templates.

`template_keys_to_pageID.py` matches template keys and page IDs, so that we can easily match the page name later.

## preprocessing
Scripts to transform the given data into the format our proposed algorithm accepts.

`find_changes.py` scans all JSON files of tables within a time period to identify changes.
These changes are stored on a field level.
Note that we do only track the _type_ of a change (update, insert, delete).
Changes to a `NULL` value are deletions, whereas changes from a `NULL` value are insertions.

`aggregate_changes.py` combines these changes to the desired granularity (table, column, row).
Note that this means that the insertion of a field results as an insertiion _within_ a column, row, or table, and so on.
We create seperate files for each entity level (table, column, row).

`filter_support.py` merges the aggregated changes into one file, multiple entity levels are supported.
If a change's occurrences are below a minimum support or over a maximum support, the change is discarded.
The output is an index of changes to their occurrences.

`preprocess_changes.py` uses this index and groups changes that always occur together.
If desired, changes that happen regularly are filtered out.

`exptract_wiki_changes.py` extracts changes to Wikipedia infoboxes of given categories from the provided 7z files and formats them for us.

`filter_wiki_support.py` filters these changes by support thresholds.

`limit_wiki_changes.py` filters these changes by year.

## rule_generation
Scripts to find and score change dependencies.

`create_histograms.py` mines rules out of an index of changes to their occurrences.

`create_histograms_yearwise.py` orchestrates the Wikipedia mining for given years and infobox categories.

`map_domains.py` is specific to our dataset.
Multiple agencies publish data in the socrata data lake, and we want to ensure that the discovered rules share the same _domain_.
This file creates an index of a table to its domain.

`filter_domains.py` uses this mapping to filter the discovered rules to have the same domain for antecedent and consequent.

## interestingness
Scripts to score change dependencies.

`histogram2pdf.py` transforms rules from histograms to probability distributions and assigns the interestingness score.


## evaluation
Scripts to measure the rule generation.

`benchmark_histogram_creation.py` runs different experiments with changing parameters to evaluate the performance of the rule mining step.

`analyze_benchmarks.py` generates plots based on the benchmark results.

`change_occurrence_distribution.py` generates a histogram of the number of occurrences per change.

`merge_rules.py` aggregates change dependencies for given categories and clusters them if requested.

## results

Contains results for both datasets.

