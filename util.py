import pandas as pd
import sys
from collections import defaultdict
from enum import Enum, auto, unique


def date_range(start, end):
    timestamps = pd.date_range(start, end).tolist()
    return [timestamp.date().isoformat() for timestamp in timestamps]


def file_extension():
    return ".json?"


def read_rule(line):
    parts = line.strip().split(";")
    antecedent = parts[0]
    consequent = parts[1]
    support = int(parts[2])
    confidence = float(parts[3])
    lift = float(parts[4])
    hist_str = parts[5][2:-2]
    hist_parts = hist_str.split(",")
    hist = [int(x) for x in hist_parts]
    return antecedent, consequent, [support, confidence, lift, hist]


def read_rules(file_name):
    result = defaultdict(dict)
    with open(file_name) as f:
        for line in f:
            antecedent, consequent, hist = read_rule(line)
            result[antecedent][consequent] = hist
    return result


@unique
class Entity(Enum):
    Table = auto()
    Column = auto()
    Row = auto()
    Field = auto()

    @classmethod
    def string_representations(cls):
        return [entity.to_str() for entity in Entity]

    def to_str(self):
        return self.name.lower()


class Field:
    table: str
    column: str
    row: str  # allows row number or primary key

    def __init__(self, table, column, row):
        self.table = table
        self.column = column
        self.row = row

    def __eq__(self, other):
        return self.table == other.table and self.column == other.column and self.row == other.row

    def __hash__(self):
        return hash((self.table, self.column, self.row))

    @classmethod
    def get_with_level(cls, level, table, column, row):
        if level == Entity.Table:
            return cls(table, None, None)
        if level == Entity.Column:
            return cls(table, column, None)
        if level == Entity.Row:
            return cls(table, None, row)
        return cls(table, column, row)

    @classmethod
    def get_csv_header(cls, level: Entity) -> str:
        if level == Entity.Table:
            return "table"
        if level == Entity.Column:
            return "table;column"
        if level == Entity.Row:
            return "table;row"
        if level == Entity.Field:
            return "table;column;row"
        raise ValueError("Unsupported entity.")

    def get_csv(self, level: Entity) -> str:
        if level == Entity.Table:
            return self.table
        if level == Entity.Column:
            return ";".join([self.table, self.column])
        if level == Entity.Row:
            return ";".join([self.table, self.row])
        if level == Entity.Field:
            return ";".join([self.table, self.column, self.row])
        raise ValueError("Unsupported entity.")
