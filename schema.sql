-- schema.sql

DROP TABLE IF EXISTS props;
DROP TABLE IF EXISTS locations;

CREATE TABLE locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE props (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    Location TEXT,
    Storage_id TEXT NOT NULL,
    Description TEXT,
    Keywords TEXT,
    Category TEXT,
    Status TEXT,
    Quantity INTEGER DEFAULT 1,
    file TEXT,
    timestamp TEXT
);