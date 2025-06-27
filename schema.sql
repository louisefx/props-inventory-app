-- This schema safely creates tables without deleting existing data.

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS props (
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
