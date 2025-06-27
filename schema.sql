-- schema.sql

-- Drop tables in reverse order of creation due to foreign keys (if any in future)
DROP TABLE IF EXISTS props;
DROP TABLE IF EXISTS locations;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL
);

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