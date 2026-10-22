"""Load the build-time SQLite seed into an empty PostgreSQL database."""
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import psycopg
from psycopg import sql

from backend.db import init_db
from backend.services.customers import password_hash


def import_seed():
    database_url = os.getenv('DATABASE_URL', '')
    password = os.getenv('SEED_PASSWORD', '')
    if not database_url.startswith(('postgres://', 'postgresql://')):
        raise RuntimeError('DATABASE_URL debe apuntar a PostgreSQL.')
    if len(password) < 14:
        raise RuntimeError('SEED_PASSWORD debe tener al menos 14 caracteres.')
    seed_path = ROOT / 'data' / 'store.db'
    if not seed_path.is_file():
        raise RuntimeError('Falta data/store.db; genera el catálogo durante la compilación.')

    init_db()
    with sqlite3.connect(seed_path) as source, psycopg.connect(database_url) as target:
        source.row_factory = sqlite3.Row
        with target.cursor() as cursor:
            cursor.execute('SELECT count(*) FROM products')
            if cursor.fetchone()[0]:
                print('Neon ya contiene el catálogo; se conserva sin cambios.')
                return
            cursor.execute('SELECT count(*) FROM users')
            if cursor.fetchone()[0]:
                raise RuntimeError('Neon tiene usuarios pero no catálogo; revisar antes de importar.')

            cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema()")
            target_tables = {row[0] for row in cursor.fetchall()}
            source_tables = {row[0] for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            pending = source_tables & target_tables
            dependencies = {}
            for table in pending:
                dependencies[table] = {
                    row[2] for row in source.execute(f'PRAGMA foreign_key_list("{table}")')
                    if row[2] in pending and row[2] != table
                }
            ordered = []
            while dependencies:
                ready = sorted(table for table, refs in dependencies.items() if not refs)
                if not ready:
                    raise RuntimeError('Dependencias circulares entre tablas de la base inicial.')
                ordered.extend(ready)
                for table in ready:
                    del dependencies[table]
                for refs in dependencies.values():
                    refs.difference_update(ready)

            total = 0
            for table in ordered:
                columns = [row[1] for row in source.execute(f'PRAGMA table_info("{table}")')]
                cursor.execute(
                    'SELECT column_name FROM information_schema.columns '
                    'WHERE table_schema=current_schema() AND table_name=%s', (table,))
                available = {row[0] for row in cursor.fetchall()}
                columns = [column for column in columns if column in available]
                if not columns:
                    continue
                count = source.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
                if not count:
                    continue
                statement = sql.SQL('COPY {} ({}) FROM STDIN').format(
                    sql.Identifier(table), sql.SQL(', ').join(map(sql.Identifier, columns)))
                fields = ', '.join(f'"{column}"' for column in columns)
                with cursor.copy(statement) as copy:
                    for row in source.execute(f'SELECT {fields} FROM "{table}" ORDER BY rowid'):
                        copy.write_row(tuple(row))
                if 'id' in columns:
                    cursor.execute('SELECT pg_get_serial_sequence(%s, %s)', (table, 'id'))
                    sequence = cursor.fetchone()[0]
                    if sequence:
                        cursor.execute(sql.SQL('SELECT max(id) FROM {}').format(sql.Identifier(table)))
                        cursor.execute('SELECT setval(%s, %s, true)', (sequence, cursor.fetchone()[0]))
                total += count
                print(f'{table}: {count} filas importadas.', flush=True)

            # The temporary SQLite build must never define the deployed accounts' password.
            cursor.execute('UPDATE users SET password_hash=%s', (password_hash(password),))
            print(f'Importación terminada: {total} filas. Contraseña inicial definida en Render.', flush=True)


if __name__ == '__main__':
    import_seed()
