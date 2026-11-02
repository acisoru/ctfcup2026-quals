require "sqlite3"

db_path = ENV.fetch("POKEBOX_DB", "/data/pokebox.db")
db = SQLite3::Database.new(db_path)

db.execute_batch(<<~SQL)
  CREATE TABLE IF NOT EXISTS users (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    pw       TEXT NOT NULL,
    bio      TEXT DEFAULT ''
  );
  CREATE TABLE IF NOT EXISTS boxes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    trainer_name TEXT,
    trainer_id   INTEGER,
    gender       TEXT,
    play_h       INTEGER,
    play_m       INTEGER,
    play_s       INTEGER,
    title        TEXT DEFAULT '',
    description  TEXT DEFAULT '',
    party_json   TEXT,
    chant        TEXT,
    shared       INTEGER DEFAULT 0,
    created_at   TEXT
  );
  CREATE TABLE IF NOT EXISTS comments (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    box_id  INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    body    TEXT
  );
SQL

puts "db initialized at #{db_path}"
