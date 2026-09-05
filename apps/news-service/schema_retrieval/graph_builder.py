from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from .objects import ColumnSchema, SchemaGraph, SchemaHit, TableRelation, TableSchema


def build_schema_graph(
    hits: List[SchemaHit],
    tables: Dict[str, TableSchema],
    all_columns: List[ColumnSchema],
    relations: List[TableRelation],
    include_join_columns: bool = True,
) -> SchemaGraph:
    """
    根据检索命中的字段构建 Schema 子图。

    输入：
    - hits: 检索命中的字段。
    - tables: 全量表 Schema。
    - all_columns: 全量字段 Schema。
    - relations: 全量表关系。

    输出：
    - 仅包含相关表、相关字段、相关关联关系的 SchemaGraph。
    """

    selected_tables = {hit.column.table_name for hit in hits}

    selected_columns = defaultdict(dict)

    for hit in hits:
        col = hit.column
        selected_columns[col.table_name][col.column_name] = col

    selected_relations: List[TableRelation] = []

    for relation in relations:
        source_selected = relation.source_table in selected_tables
        target_selected = relation.target_table in selected_tables

        if source_selected and target_selected:
            selected_relations.append(relation)

            if include_join_columns:
                source_col = _find_column(
                    all_columns,
                    relation.source_table,
                    relation.source_column,
                )
                target_col = _find_column(
                    all_columns,
                    relation.target_table,
                    relation.target_column,
                )

                if source_col:
                    selected_columns[relation.source_table][relation.source_column] = source_col

                if target_col:
                    selected_columns[relation.target_table][relation.target_column] = target_col

    graph_tables = {
        table_name: tables[table_name]
        for table_name in selected_tables
        if table_name in tables
    }

    graph_columns = {
        table_name: list(column_map.values())
        for table_name, column_map in selected_columns.items()
    }

    database = ""
    if graph_tables:
        database = next(iter(graph_tables.values())).database

    return SchemaGraph(
        database=database,
        tables=graph_tables,
        columns=graph_columns,
        relations=selected_relations,
    )


def _find_column(
    columns: List[ColumnSchema],
    table_name: str,
    column_name: str,
) -> ColumnSchema | None:
    for column in columns:
        if column.table_name == table_name and column.column_name == column_name:
            return column

    return None
