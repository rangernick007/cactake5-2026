import sqlite3
from flask import Flask, render_template

app = Flask(__name__)

# Helper function to connect to SQLite whenever a route needs data
def get_db_connection():
    conn = sqlite3.connect('project.db')
    conn.row_factory = sqlite3.Row  # Returns query results as dictionary-like objects
    return conn

@app.route("/")
def home():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
