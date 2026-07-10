from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.sql"
DB_PATH = BASE_DIR / "garbage_rules.db"


def initialize_database(db_path: Path = DB_PATH, schema_path: Path = SCHEMA_PATH) -> list[str]:
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    schema_sql = schema_path.read_text(encoding="utf-8")

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.executescript(schema_sql)
        connection.commit()
        return get_table_names(connection)


def get_table_names(connection: sqlite3.Connection) -> list[str]:
    cursor = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name;
        """
    )
    return [row[0] for row in cursor.fetchall()]


def main() -> None:
    table_names = initialize_database()
    print(f"Database initialized: {DB_PATH}")
    print(f"Tables created: {len(table_names)}")
    for table_name in table_names:
        print(f"- {table_name}")


if __name__ == "__main__":
    main()
